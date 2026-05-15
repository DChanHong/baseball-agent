import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from app.prompts import SYSTEM_PROMPT
from app.tools import get_langchain_tools


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

MAX_ITERATIONS = 6
MAX_EXECUTION_TIME = 30
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
UNAVAILABLE_GEMINI_MODELS = {"gemini-2.0-flash", "models/gemini-2.0-flash"}
PROMPT_VERSION = "kbo-game-day-agent-v1"


def _get_gemini_model() -> str:
    configured_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    if configured_model in UNAVAILABLE_GEMINI_MODELS:
        return DEFAULT_GEMINI_MODEL
    return configured_model


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _langsmith_enabled() -> bool:
    return _env_flag("LANGSMITH_TRACING") or _env_flag("LANGCHAIN_TRACING_V2")


def _langsmith_run_config(
    *,
    trace_id: str,
    session_id: str | None,
    original_message: str,
    processed_message: str,
    user_context: dict[str, Any] | None,
) -> dict[str, Any]:
    context = user_context or {}
    selected_game = context.get("selected_game") or {}
    candidate_games = context.get("candidate_games") or []
    return {
        "run_name": "kbo_game_day_agent",
        "tags": [
            "kbo-agent",
            "week8-observability",
            f"prompt:{PROMPT_VERSION}",
        ],
        "metadata": {
            "trace_id": trace_id,
            "session_id": session_id,
            "agent_mode": "langchain_agent_executor",
            "prompt_version": PROMPT_VERSION,
            "original_message": original_message,
            "processed_message": processed_message,
            "selected_game_id": selected_game.get("game_id"),
            "selected_stadium_id": selected_game.get("stadium_id"),
            "candidate_game_count": len(candidate_games),
            "chat_model": _get_gemini_model(),
            "embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        },
    }


def _metadata(
    *,
    trace_id: str,
    session_id: str | None,
    start_time: float,
    started_at: str,
    tools_used: list[str] | None = None,
    primary_intent: str = "general",
    resolved_intents: list[str] | None = None,
    observations: list[dict[str, Any]] | None = None,
    stop_reason: str = "final_answer",
    fallback_used: bool = False,
    session_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "session_id": session_id,
        "started_at": started_at,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "intent": primary_intent,
        "primary_intent": primary_intent,
        "resolved_intents": resolved_intents or [primary_intent],
        "agent_mode": "langchain_agent_executor",
        "observability": {
            "provider": "langsmith",
            "enabled": _langsmith_enabled(),
            "project": os.getenv("LANGSMITH_PROJECT") or "default",
            "prompt_version": PROMPT_VERSION,
        },
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
        "session_updates": session_updates or {},
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


def _derive_session_updates(intermediate_steps: list[tuple[Any, Any]]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for action, observation in intermediate_steps:
        if getattr(action, "tool", None) != "find_kbo_game":
            continue
        payload = _observation_as_dict(observation)
        if not payload.get("ok"):
            continue
        data = payload.get("data") or {}
        if payload.get("status") == "ambiguous_game":
            candidates = data.get("candidates") or []
            if candidates:
                updates["candidate_games"] = candidates
        elif payload.get("status") == "found":
            updates["selected_game"] = data
            updates["candidate_games"] = [data]
    return updates


def _resolve_intents(tools_used: list[str], *, stop_reason: str) -> list[str]:
    intents = []
    if "score_seat_candidates" in tools_used:
        intents.append("seat_recommendation")
    if "get_ticketing_guide" in tools_used:
        intents.append("ticketing")
    if "get_logistics_guide" in tools_used:
        intents.append("logistics")
    if "get_weather_context" in tools_used and not intents:
        intents.append("weather")
    if "find_kbo_game" in tools_used and not intents:
        intents.append("schedule_lookup")
    if not intents and stop_reason == "missing_required_input":
        intents.append("clarification")
    if not intents:
        intents.append("general")
    return intents


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
        early_stopping_method="force",
    )


def run_agent(
    message: str,
    user_context: dict[str, Any] | None = None,
    *,
    session_id: str | None = None,
    original_message: str | None = None,
    pre_observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    start_time = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    trace_id = f"kbo_{uuid.uuid4().hex}"
    raw_message = original_message or message

    if not message.strip():
        resolved_intents = ["clarification"]
        return {
            "answer": "요청이 비어 있습니다. 경기 날짜, 팀, 원하는 도움을 함께 알려주세요.",
            "metadata": _metadata(
                trace_id=trace_id,
                session_id=session_id,
                start_time=start_time,
                started_at=started_at,
                primary_intent=resolved_intents[0],
                resolved_intents=resolved_intents,
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
            },
            config=_langsmith_run_config(
                trace_id=trace_id,
                session_id=session_id,
                original_message=raw_message,
                processed_message=message,
                user_context=user_context,
            ),
        )
    except Exception as exc:
        resolved_intents = ["agent_error"]
        return {
            "answer": (
                "Agent 실행 중 문제가 발생했습니다. "
                "현재는 날짜, 팀, 구장 정보를 더 구체적으로 입력한 뒤 다시 시도해 주세요."
            ),
            "metadata": _metadata(
                trace_id=trace_id,
                session_id=session_id,
                start_time=start_time,
                started_at=started_at,
                primary_intent=resolved_intents[0],
                resolved_intents=resolved_intents,
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
    session_updates = _derive_session_updates(intermediate_steps)
    observations = _renumber_observations(observations)
    tools_used = [observation["tool"] for observation in observations]
    stop_reason = "final_answer"
    if len(intermediate_steps) >= MAX_ITERATIONS:
        stop_reason = "max_iterations_exceeded"
    resolved_intents = _resolve_intents(tools_used, stop_reason=stop_reason)
    answer = _extract_text(result.get("output"))

    return {
        "answer": answer or "답변을 생성하지 못했습니다.",
        "metadata": _metadata(
            trace_id=trace_id,
            session_id=session_id,
            start_time=start_time,
            started_at=started_at,
            tools_used=tools_used,
            primary_intent=resolved_intents[0],
            resolved_intents=resolved_intents,
            observations=observations,
            stop_reason=stop_reason,
            fallback_used=False,
            session_updates=session_updates,
        ),
    }
