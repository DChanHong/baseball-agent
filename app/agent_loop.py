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
from app.tools import get_langchain_tools


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


def run_agent(message: str, user_context: dict[str, Any] | None = None) -> dict[str, Any]:
    start_time = time.perf_counter()
    intent = _infer_intent(message)

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

    observations = _format_intermediate_steps(result.get("intermediate_steps") or [])
    tools_used = [observation["tool"] for observation in observations]
    stop_reason = "final_answer"
    if len(observations) >= MAX_ITERATIONS:
        stop_reason = "max_iterations_exceeded"

    return {
        "answer": _extract_text(result.get("output")) or "답변을 생성하지 못했습니다.",
        "metadata": _metadata(
            intent=intent,
            start_time=start_time,
            tools_used=tools_used,
            observations=observations,
            stop_reason=stop_reason,
            fallback_used=False,
        ),
    }
