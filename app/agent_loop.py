import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from app.prompts import SYSTEM_PROMPT
from app.tools import get_langchain_tools


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

MAX_ITERATIONS = 8
MAX_EXECUTION_TIME = 30
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
UNAVAILABLE_GEMINI_MODELS = {"gemini-2.0-flash", "models/gemini-2.0-flash"}
PROMPT_VERSION = "kbo-game-day-agent-v1"
MAX_OBSERVATION_EXCERPT_CHARS = 1500
LANGSMITH_MESSAGE_PREVIEW_CHARS = 120
DEFAULT_PRICING_SOURCE = "google_gemini_api_pricing_config"
DEFAULT_GEMINI_PRICES_PER_1M_TOKENS = {
    "gemini-2.5-flash": {
        "input": 0.30,
        "output": 2.50,
    },
}
SENSITIVE_KEYS = {
    "access_token",
    "address",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "cookie",
    "credential",
    "email",
    "id_token",
    "password",
    "payment_info",
    "phone",
    "refresh_token",
    "secret",
    "session",
    "session_id",
    "set_cookie",
    "token",
    "user_id",
}
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
KOREAN_PHONE_PATTERN = re.compile(r"\b01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}\b")
BEARER_TOKEN_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE)
LONG_SECRET_PATTERN = re.compile(r"\b(?=[A-Za-z0-9_./+=-]*[A-Za-z])(?=[A-Za-z0-9_./+=-]*\d)[A-Za-z0-9_./+=-]{32,}\b")


class ToolTraceCallback(BaseCallbackHandler):
    """Collect lightweight per-tool observability fields for the API metadata."""

    def __init__(self) -> None:
        self._started_at_by_run_id: dict[str, float] = {}
        self._events_by_run_id: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        run_key = str(run_id)
        tool_name = serialized.get("name") or serialized.get("id") or "unknown"
        self._started_at_by_run_id[run_key] = time.perf_counter()
        self._events_by_run_id[run_key] = {
            "tool": tool_name,
            "arguments": _mask_tool_arguments(inputs if inputs is not None else input_str),
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
        }

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        run_key = str(run_id)
        started_at = self._started_at_by_run_id.pop(run_key, None)
        event = self._events_by_run_id.pop(run_key, {"tool": "unknown", "arguments": {}})
        event["latency_ms"] = int((time.perf_counter() - started_at) * 1000) if started_at else None
        event["result"] = _parse_observation_result(output)
        event["result_summary"] = _summarize_tool_output(event.get("tool", "unknown"), output)
        event["observation_excerpt"] = _build_observation_excerpt(output)
        self.events.append(event)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        run_key = str(run_id)
        started_at = self._started_at_by_run_id.pop(run_key, None)
        event = self._events_by_run_id.pop(run_key, {"tool": "unknown", "arguments": {}})
        event["latency_ms"] = int((time.perf_counter() - started_at) * 1000) if started_at else None
        event["result"] = {
            "ok": False,
            "status": "tool_error",
            "error": {"code": type(error).__name__, "message": str(error)},
        }
        event["result_summary"] = {"error_type": type(error).__name__}
        event["observation_excerpt"] = _build_observation_excerpt(event["result"])
        self.events.append(event)


class UsageTraceCallback(BaseCallbackHandler):
    """Collect per-request LLM token usage for API metadata."""

    def __init__(self, *, chat_model: str) -> None:
        self.chat_model = chat_model
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.llm_call_count = 0

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        usage = _extract_usage_from_llm_result(response)
        if not usage:
            return

        self.llm_call_count += 1
        input_tokens = _coerce_int(usage.get("input_tokens"))
        output_tokens = _coerce_int(usage.get("output_tokens"))
        total_tokens = _coerce_int(usage.get("total_tokens"))
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += total_tokens or input_tokens + output_tokens

    def to_metadata(self) -> dict[str, Any]:
        estimated_cost = _estimate_llm_cost(
            model=self.chat_model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )
        return {
            "available": self.llm_call_count > 0,
            "chat_model": self.chat_model,
            "llm_call_count": self.llm_call_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": estimated_cost,
            "currency": "USD",
            "pricing_source": DEFAULT_PRICING_SOURCE,
        }


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
    security: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = user_context or {}
    selected_game = context.get("selected_game") or {}
    candidate_games = context.get("candidate_games") or []
    security_info = security or {}
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
            "original_message_len": len(original_message),
            "processed_message_len": len(processed_message),
            "original_message_preview": _safe_text_preview(original_message),
            "processed_message_preview": _safe_text_preview(processed_message),
            "selected_game_id": selected_game.get("game_id"),
            "selected_stadium_id": selected_game.get("stadium_id"),
            "candidate_game_count": len(candidate_games),
            "security_checked": bool(security_info.get("checked")),
            "security_blocked": bool(security_info.get("blocked")),
            "security_flag_count": security_info.get("flag_count", 0),
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
    usage: dict[str, Any] | None = None,
    security: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_observations = observations or []
    current_tools_used = tools_used or []
    current_usage = usage or _empty_usage_metadata()
    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
    trace_summary = _build_trace_summary(
        observations=current_observations,
        usage=current_usage,
        elapsed_ms=elapsed_ms,
        stop_reason=stop_reason,
        fallback_used=fallback_used,
    )
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
        "usage": current_usage,
        "trace_summary": trace_summary,
        "tools_used": current_tools_used,
        "observations": current_observations,
        "stop_reason": stop_reason,
        "iterations": len(current_observations),
        "elapsed_ms": elapsed_ms,
        "fallback_used": fallback_used,
        "session_updates": session_updates or {},
        "security": security or {"checked": False, "blocked": False, "flags": [], "flag_count": 0},
    }


def _empty_usage_metadata() -> dict[str, Any]:
    return {
        "available": False,
        "chat_model": _get_gemini_model(),
        "llm_call_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "estimated_cost": 0.0,
        "currency": "USD",
        "pricing_source": DEFAULT_PRICING_SOURCE,
    }


def _build_trace_summary(
    *,
    observations: list[dict[str, Any]],
    usage: dict[str, Any],
    elapsed_ms: int,
    stop_reason: str,
    fallback_used: bool,
) -> dict[str, Any]:
    failed_tools = []
    for observation in observations:
        result = observation.get("result") or {}
        if result.get("ok") is False or result.get("error"):
            failed_tools.append(
                {
                    "step": observation.get("step"),
                    "tool": observation.get("tool"),
                    "status": result.get("status"),
                    "error_code": ((result.get("error") or {}) if isinstance(result.get("error"), dict) else {}).get(
                        "code"
                    ),
                }
            )

    return {
        "total_latency_ms": elapsed_ms,
        "tool_call_count": len(observations),
        "tool_error_count": len(failed_tools),
        "tools_sequence": [observation.get("tool", "unknown") for observation in observations],
        "failed_tools": failed_tools,
        "llm_call_count": usage.get("llm_call_count", 0),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "estimated_cost": usage.get("estimated_cost", 0.0),
        "currency": usage.get("currency", "USD"),
        "stop_reason": stop_reason,
        "fallback_used": fallback_used,
    }


def _coerce_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _find_first_number(mapping: dict[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        if key in mapping:
            value = _coerce_int(mapping.get(key))
            if value:
                return value
    return 0


def _extract_usage_from_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}

    nested_candidates = (
        value.get("usage_metadata"),
        value.get("token_usage"),
        value.get("usage"),
        value.get("usageInfo"),
    )
    for candidate in nested_candidates:
        usage = _extract_usage_from_mapping(candidate)
        if usage:
            return usage

    input_tokens = _find_first_number(
        value,
        (
            "input_tokens",
            "prompt_tokens",
            "prompt_token_count",
            "inputTokenCount",
            "promptTokenCount",
        ),
    )
    output_tokens = _find_first_number(
        value,
        (
            "output_tokens",
            "completion_tokens",
            "candidates_token_count",
            "outputTokenCount",
            "candidatesTokenCount",
        ),
    )
    total_tokens = _find_first_number(
        value,
        (
            "total_tokens",
            "total_token_count",
            "totalTokenCount",
        ),
    )
    if not any((input_tokens, output_tokens, total_tokens)):
        return {}
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens or input_tokens + output_tokens,
    }


def _extract_usage_from_llm_result(response: Any) -> dict[str, int]:
    usage = _extract_usage_from_mapping(getattr(response, "llm_output", None))
    if usage:
        return usage

    for generation_group in getattr(response, "generations", []) or []:
        for generation in generation_group or []:
            message = getattr(generation, "message", None)
            for candidate in (
                getattr(message, "usage_metadata", None),
                getattr(message, "response_metadata", None),
                getattr(generation, "generation_info", None),
            ):
                usage = _extract_usage_from_mapping(candidate)
                if usage:
                    return usage
    return {}


def _model_pricing(model: str) -> dict[str, float]:
    normalized_model = model.removeprefix("models/")
    input_override = os.getenv("LLM_INPUT_PRICE_PER_1M_TOKENS")
    output_override = os.getenv("LLM_OUTPUT_PRICE_PER_1M_TOKENS")
    if input_override is not None and output_override is not None:
        try:
            return {"input": float(input_override), "output": float(output_override)}
        except ValueError:
            pass
    return DEFAULT_GEMINI_PRICES_PER_1M_TOKENS.get(normalized_model, {"input": 0.0, "output": 0.0})


def _estimate_llm_cost(*, model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = _model_pricing(model)
    cost = (input_tokens / 1_000_000 * pricing["input"]) + (output_tokens / 1_000_000 * pricing["output"])
    return round(cost, 6)


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


def _normalize_sensitive_key(key: Any) -> str:
    return str(key).lower().replace("-", "_")


def _is_sensitive_key(key: Any) -> bool:
    normalized_key = _normalize_sensitive_key(key)
    return (
        normalized_key in SENSITIVE_KEYS
        or normalized_key.endswith("_token")
        or normalized_key.endswith("_key")
        or normalized_key.endswith("_secret")
        or "authorization" in normalized_key
    )


def _mask_sensitive_text(value: str) -> str:
    masked = EMAIL_PATTERN.sub("[email]", value)
    masked = KOREAN_PHONE_PATTERN.sub("[phone]", masked)
    masked = BEARER_TOKEN_PATTERN.sub("Bearer [token]", masked)
    masked = LONG_SECRET_PATTERN.sub("[secret]", masked)
    return masked


def _safe_text_preview(value: str, limit: int = LANGSMITH_MESSAGE_PREVIEW_CHARS) -> str:
    preview = _mask_sensitive_text(value)
    if len(preview) > limit:
        return preview[:limit] + "...[truncated]"
    return preview


def _mask_tool_arguments(value: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return _mask_sensitive_text(value)
        return _mask_tool_arguments(parsed)

    if isinstance(value, list):
        return [_mask_tool_arguments(item) for item in value]

    if not isinstance(value, dict):
        return value

    masked: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = _normalize_sensitive_key(key)
        if _is_sensitive_key(key):
            masked[key] = "[excluded]"
        elif normalized_key == "origin" and isinstance(item, str) and len(item) > 12:
            masked[key] = _mask_sensitive_text(item[:2]) + "***"
        else:
            masked[key] = _mask_tool_arguments(item)
    return masked


def _sanitize_observation_value(value: Any) -> Any:
    if isinstance(value, str):
        return _mask_sensitive_text(value)

    if isinstance(value, list):
        return [_sanitize_observation_value(item) for item in value[:10]]

    if not isinstance(value, dict):
        return value

    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = _normalize_sensitive_key(key)
        if _is_sensitive_key(key):
            sanitized[key] = "[excluded]"
        elif normalized_key == "origin" and isinstance(item, str) and len(item) > 12:
            sanitized[key] = _mask_sensitive_text(item[:2]) + "***"
        else:
            sanitized[key] = _sanitize_observation_value(item)
    return sanitized


def _build_observation_excerpt(observation: Any) -> str:
    payload = _observation_as_dict(observation)
    excerpt_value = _sanitize_observation_value(payload if payload else observation)
    if isinstance(excerpt_value, str):
        excerpt = excerpt_value
    else:
        try:
            excerpt = json.dumps(excerpt_value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            excerpt = str(excerpt_value)

    if len(excerpt) > MAX_OBSERVATION_EXCERPT_CHARS:
        return excerpt[:MAX_OBSERVATION_EXCERPT_CHARS] + "...[truncated]"
    return excerpt


def _summarize_tool_output(tool_name: str, output: Any) -> dict[str, Any]:
    payload = _observation_as_dict(output)
    if not payload:
        return {}

    data = payload.get("data") or {}
    summary: dict[str, Any] = {
        "ok": payload.get("ok"),
        "status": payload.get("status"),
    }
    if payload.get("error"):
        summary["error_code"] = (payload.get("error") or {}).get("code")

    if tool_name == "find_kbo_game":
        candidates = data.get("candidates") or []
        summary.update(
            {
                "candidate_count": len(candidates),
                "game_id": data.get("game_id"),
                "date": data.get("date"),
                "stadium_id": data.get("stadium_id"),
            }
        )
    elif tool_name == "get_stadium_info":
        summary.update(
            {
                "stadium_id": data.get("stadium_id"),
                "is_dome": data.get("is_dome"),
                "home_team_count": len(data.get("home_teams") or []),
            }
        )
    elif tool_name == "get_weather_context":
        summary.update(
            {
                "recommendation_mode": data.get("recommendation_mode"),
                "forecast_level": data.get("forecast_level"),
                "risk_flags": data.get("risk_flags") or [],
                "weather_provider_failed": bool(data.get("weather_provider_error")),
            }
        )
    elif tool_name == "search_baseball_knowledge":
        documents = data.get("documents") or []
        source_summary = data.get("source_summary") or {}
        source_types = sorted(
            {
                (document.get("metadata") or {}).get("source_type")
                for document in documents
                if isinstance(document, dict) and (document.get("metadata") or {}).get("source_type")
            }
        )
        summary.update(
            {
                "returned_count": data.get("returned_count", len(documents)),
                "search_top_k": data.get("search_top_k"),
                "source_types": source_types,
                "trust_levels": source_summary.get("trust_levels") or [],
                "security_flag_count": source_summary.get("security_flag_count", 0),
            }
        )
    elif tool_name == "score_seat_candidates":
        recommendations = data.get("recommendations") or []
        summary.update(
            {
                "recommendation_count": len(recommendations),
                "top_seat": (recommendations[0] or {}).get("seat_name") if recommendations else None,
                "limitations": data.get("limitations") or [],
            }
        )
    elif tool_name == "get_ticketing_guide":
        summary.update(
            {
                "team": data.get("team"),
                "stadium_id": data.get("stadium_id"),
                "match_basis": data.get("match_basis"),
                "lookup_mode": data.get("lookup_mode"),
            }
        )
    elif tool_name == "get_logistics_guide":
        summary.update(
            {
                "origin": data.get("origin"),
                "stadium_id": data.get("stadium_id"),
                "lookup_mode": data.get("lookup_mode"),
                "route_count": len(data.get("recommended_routes") or []),
                "same_day_possible": (data.get("return_plan") or {}).get("same_day_possible"),
            }
        )

    return {key: value for key, value in summary.items() if value is not None}


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


def _format_intermediate_steps(
    intermediate_steps: list[tuple[Any, Any]],
    tool_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    observations = []
    events = tool_events or []
    for step, (action, observation) in enumerate(intermediate_steps, start=1):
        event = events[step - 1] if step - 1 < len(events) else {}
        observations.append(
            {
                "step": step,
                "tool": getattr(action, "tool", "unknown"),
                "arguments": _mask_tool_arguments(getattr(action, "tool_input", {}) or {}),
                "result": _parse_observation_result(observation),
                "latency_ms": event.get("latency_ms"),
                "result_summary": event.get("result_summary")
                or _summarize_tool_output(getattr(action, "tool", "unknown"), observation),
                "observation_excerpt": event.get("observation_excerpt")
                or _build_observation_excerpt(observation),
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


def _fallback_answer_from_observations(observations: list[dict[str, Any]]) -> str | None:
    latest_score_summary = None
    for observation in reversed(observations):
        if observation.get("tool") == "score_seat_candidates":
            result = observation.get("result") or {}
            if result.get("ok"):
                latest_score_summary = observation.get("result_summary") or {}
                break

    if latest_score_summary:
        top_seat = latest_score_summary.get("top_seat") or "점수화 결과 1순위 좌석"
        recommendation_count = latest_score_summary.get("recommendation_count") or 0
        return (
            f"좌석 후보 {recommendation_count}개를 점수화한 결과, 우선 추천 좌석은 {top_seat}입니다. "
            "자세한 추천 근거는 이번 실행의 Tool observation에 기록되어 있습니다. "
            "좌석/가격 정보는 크롤링 시점 기준이며 실시간 잔여석은 반영하지 않습니다."
        )

    return None


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
    security: dict[str, Any] | None = None,
) -> dict[str, Any]:
    start_time = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    trace_id = f"kbo_{uuid.uuid4().hex}"
    raw_message = original_message or message
    usage_trace_callback = UsageTraceCallback(chat_model=_get_gemini_model())

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
                security=security,
            ),
        }

    try:
        executor = _create_agent_executor()
        tool_trace_callback = ToolTraceCallback()
        run_config = _langsmith_run_config(
            trace_id=trace_id,
            session_id=session_id,
            original_message=raw_message,
            processed_message=message,
            user_context=user_context,
            security=security,
        )
        run_config["callbacks"] = [tool_trace_callback, usage_trace_callback]
        result = executor.invoke(
            {
                "input": message,
                "user_context": json.dumps(user_context or {}, ensure_ascii=False),
            },
            config=run_config,
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
                        "observation_excerpt": _build_observation_excerpt(
                            {
                                "ok": False,
                                "status": "agent_failed",
                                "error": {
                                    "code": "AGENT_EXECUTION_FAILED",
                                    "message": str(exc),
                                },
                            }
                        ),
                    }
                ],
                stop_reason="tool_failure_limit_exceeded",
                fallback_used=True,
                usage=usage_trace_callback.to_metadata(),
                security=security,
            ),
        }

    intermediate_steps = result.get("intermediate_steps") or []
    observations = [
        *(pre_observations or []),
        *_format_intermediate_steps(intermediate_steps, tool_trace_callback.events),
    ]
    session_updates = _derive_session_updates(intermediate_steps)
    observations = _renumber_observations(observations)
    tools_used = [observation["tool"] for observation in observations]
    stop_reason = "final_answer"
    if len(intermediate_steps) >= MAX_ITERATIONS:
        stop_reason = "max_iterations_exceeded"
    answer = _extract_text(result.get("output"))
    if answer.startswith("Agent stopped due to max iterations"):
        stop_reason = "max_iterations_exceeded"
        answer = _fallback_answer_from_observations(observations) or answer
    resolved_intents = _resolve_intents(tools_used, stop_reason=stop_reason)

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
            usage=usage_trace_callback.to_metadata(),
            security=security,
        ),
    }


def build_security_refusal_response(
    *,
    answer: str,
    session_id: str | None = None,
    security: dict[str, Any] | None = None,
) -> dict[str, Any]:
    start_time = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    trace_id = f"kbo_{uuid.uuid4().hex}"
    resolved_intents = ["security_refusal"]
    return {
        "answer": answer,
        "metadata": _metadata(
            trace_id=trace_id,
            session_id=session_id,
            start_time=start_time,
            started_at=started_at,
            primary_intent=resolved_intents[0],
            resolved_intents=resolved_intents,
            stop_reason="security_refusal",
            fallback_used=True,
            security=security,
        ),
    }
