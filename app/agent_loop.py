import json
import os
import time
from typing import Any

from dotenv import load_dotenv
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from app.prompts import SYSTEM_PROMPT
from app.tools import get_langchain_tools, score_seat_candidates


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

MAX_ITERATIONS = 6
MAX_EXECUTION_TIME = 30
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
UNAVAILABLE_GEMINI_MODELS = {"gemini-2.0-flash", "models/gemini-2.0-flash"}


def _get_gemini_model() -> str:
    configured_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    if configured_model in UNAVAILABLE_GEMINI_MODELS:
        return DEFAULT_GEMINI_MODEL
    return configured_model


def _infer_intent(message: str) -> str:
    text = message.lower()
    if any(keyword in text for keyword in ["자리", "좌석", "응원석", "그늘", "시야"]):
        return "seat_recommendation"
    if any(keyword in text for keyword in ["예매", "티켓", "티켓팅", "오픈"]):
        return "ticketing"
    if any(keyword in text for keyword in ["원정", "동선", "막차", "교통", "ktx", "버스", "복귀"]):
        return "logistics"
    if any(keyword in text for keyword in ["경기", "일정", "보러", "직관", "주말", "다음주"]):
        return "schedule_lookup"
    return "general"


def _metadata(
    *,
    intent: str,
    start_time: float,
    tools_used: list[str] | None = None,
    observations: list[dict[str, Any]] | None = None,
    stop_reason: str = "final_answer",
    fallback_used: bool = False,
) -> dict[str, Any]:
    return {
        "intent": intent,
        "agent_mode": "langchain_agent_executor",
        "model": {
            "chat": _get_gemini_model(),
            "embedding": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        },
        "tools_used": tools_used or [],
        "observations": observations or [],
        "stop_reason": stop_reason,
        "iterations": len(observations or []),
        "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
        "fallback_used": fallback_used,
    }


def _parse_observation_result(observation: Any) -> dict[str, Any]:
    if isinstance(observation, dict):
        return {
            "ok": observation.get("ok"),
            "status": observation.get("status"),
            "error": observation.get("error"),
        }

    if isinstance(observation, str):
        try:
            parsed = json.loads(observation)
        except json.JSONDecodeError:
            return {"ok": None, "status": "raw_observation", "error": None}

        if isinstance(parsed, dict):
            return {
                "ok": parsed.get("ok"),
                "status": parsed.get("status"),
                "error": parsed.get("error"),
            }

    return {"ok": None, "status": type(observation).__name__, "error": None}


def _observation_as_dict(observation: Any) -> dict[str, Any]:
    if isinstance(observation, dict):
        return observation
    if isinstance(observation, str):
        try:
            parsed = json.loads(observation)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts).strip() or str(value)
    return str(value)


def _format_intermediate_steps(intermediate_steps: list[tuple[Any, Any]]) -> list[dict[str, Any]]:
    observations = []
    for step, (action, observation) in enumerate(intermediate_steps, start=1):
        observations.append(
            {
                "step": step,
                "tool": getattr(action, "tool", "unknown"),
                "arguments": getattr(action, "tool_input", {}) or {},
                "result": _parse_observation_result(observation),
            }
        )
    return observations


def _renumber_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index, observation in enumerate(observations, start=1):
        observation["step"] = index
    return observations


def _latest_tool_payload(intermediate_steps: list[tuple[Any, Any]], tool_name: str) -> dict[str, Any]:
    for action, observation in reversed(intermediate_steps):
        if getattr(action, "tool", None) != tool_name:
            continue
        payload = _observation_as_dict(observation)
        if payload:
            return payload
    return {}


def _seat_answer_from_scoring(score_result: dict[str, Any]) -> str:
    if not score_result.get("ok"):
        return "좌석 후보를 점수화하지 못했습니다. 경기와 구장 정보는 확인됐지만 좌석 RAG 문서가 부족합니다."

    data = score_result.get("data") or {}
    game = data.get("game") or {}
    recommendations = data.get("recommendations") or []
    if not recommendations:
        return "좌석 후보를 찾지 못했습니다. 구장 좌석 데이터가 인덱싱되어 있는지 확인해 주세요."

    header = (
        f"{game.get('date')} {game.get('time')} "
        f"{game.get('away_team')} vs {game.get('home_team')} "
        f"{game.get('stadium_name')} 기준 좌석 추천입니다."
    ).strip()
    lines = [header, ""]
    for index, item in enumerate(recommendations, start=1):
        price = item.get("price_hint_krw")
        price_text = f" / 최저가 힌트 {price:,}원" if isinstance(price, int) else ""
        reasons = ", ".join(item.get("reasons") or ["RAG 검색 후보"])
        lines.append(f"{index}. {item.get('seat_name')} - 점수 {item.get('score')}{price_text}: {reasons}")

    limitations = data.get("limitations") or []
    if limitations:
        lines.extend(["", f"주의: {', '.join(limitations)}"])
    return "\n".join(lines)


def _apply_seat_scoring_fallback(
    *,
    intent: str,
    user_context: dict[str, Any] | None,
    intermediate_steps: list[tuple[Any, Any]],
    observations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    tools_used = [observation["tool"] for observation in observations]
    if intent != "seat_recommendation" or "score_seat_candidates" in tools_used:
        return observations, None

    search_payload = _latest_tool_payload(intermediate_steps, "search_baseball_knowledge")
    weather_payload = _latest_tool_payload(intermediate_steps, "get_weather_context")
    seat_documents = ((search_payload.get("data") or {}).get("documents") or [])
    weather_context = (weather_payload.get("data") or {})
    context = user_context or {}
    selected_game = context.get("selected_game") or {}
    if not seat_documents or not selected_game:
        return observations, None

    score_result = score_seat_candidates(
        game=selected_game,
        weather_context=weather_context,
        seat_documents=seat_documents,
        preferences=context.get("preferences") or [],
        budget=context.get("budget"),
        cheering_team=context.get("favorite_team") or selected_game.get("away_team"),
    )
    observations.append(
        {
            "step": 0,
            "tool": "score_seat_candidates",
            "arguments": {
                "game_id": selected_game.get("game_id"),
                "seat_document_count": len(seat_documents),
                "fallback": "server_enforced",
            },
            "result": _parse_observation_result(score_result),
        }
    )
    return observations, _seat_answer_from_scoring(score_result)


def _create_agent_executor() -> AgentExecutor:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 환경변수가 필요합니다.")

    tools = get_langchain_tools()
    llm = ChatGoogleGenerativeAI(
        model=_get_gemini_model(),
        api_key=SecretStr(api_key),
        temperature=0.2,
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            (
                "human",
                "사용자 요청: {input}\n\n사용자 컨텍스트(JSON): {user_context}",
            ),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        return_intermediate_steps=True,
        max_iterations=MAX_ITERATIONS,
        max_execution_time=MAX_EXECUTION_TIME,
        handle_parsing_errors=True,
        early_stopping_method="generate",
    )


def run_agent(
    message: str,
    user_context: dict[str, Any] | None = None,
    *,
    original_message: str | None = None,
    pre_observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    start_time = time.perf_counter()
    intent = _infer_intent(original_message or message)

    if not message.strip():
        return {
            "answer": "요청이 비어 있습니다. 경기 날짜, 팀, 원하는 도움을 함께 알려주세요.",
            "metadata": _metadata(
                intent=intent,
                start_time=start_time,
                stop_reason="missing_required_input",
                fallback_used=True,
            ),
        }

    try:
        executor = _create_agent_executor()
        result = executor.invoke(
            {
                "input": message,
                "user_context": json.dumps(user_context or {}, ensure_ascii=False),
            }
        )
    except Exception as exc:
        return {
            "answer": (
                "Agent 실행 중 문제가 발생했습니다. "
                "현재는 날짜, 팀, 구장 정보를 더 구체적으로 입력한 뒤 다시 시도해 주세요."
            ),
            "metadata": _metadata(
                intent=intent,
                start_time=start_time,
                observations=[
                    {
                        "step": 1,
                        "tool": "agent_executor",
                        "arguments": {},
                        "result": {
                            "ok": False,
                            "status": "agent_failed",
                            "error": {
                                "code": "AGENT_EXECUTION_FAILED",
                                "message": str(exc),
                            },
                        },
                    }
                ],
                stop_reason="tool_failure_limit_exceeded",
                fallback_used=True,
            ),
        }

    intermediate_steps = result.get("intermediate_steps") or []
    observations = [*(pre_observations or []), *_format_intermediate_steps(intermediate_steps)]
    observations, fallback_answer = _apply_seat_scoring_fallback(
        intent=intent,
        user_context=user_context,
        intermediate_steps=intermediate_steps,
        observations=observations,
    )
    observations = _renumber_observations(observations)
    tools_used = [observation["tool"] for observation in observations]
    stop_reason = "final_answer"
    if len(intermediate_steps) >= MAX_ITERATIONS:
        stop_reason = "max_iterations_exceeded"
    answer = _extract_text(result.get("output"))
    if fallback_answer and (not answer or "답변을 생성하지 못했습니다" in answer):
        answer = fallback_answer

    return {
        "answer": answer or "답변을 생성하지 못했습니다.",
        "metadata": _metadata(
            intent=intent,
            start_time=start_time,
            tools_used=tools_used,
            observations=observations,
            stop_reason=stop_reason,
            fallback_used=False,
        ),
    }
