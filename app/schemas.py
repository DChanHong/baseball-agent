import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = CONTROL_CHAR_PATTERN.sub("", value).strip()
    return normalized or None


class UserContext(BaseModel):
    favorite_team: str | None = Field(default=None, max_length=20)
    origin: str | None = None
    preferences: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("favorite_team", mode="before")
    @classmethod
    def normalize_favorite_team(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("preferences", mode="before")
    @classmethod
    def normalize_preferences(cls, value: list[str] | None) -> list[str]:
        if value is None:
            return []
        normalized_preferences = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("preferences must contain only strings")
            normalized = _normalize_optional_text(item)
            if normalized is not None:
                normalized_preferences.append(normalized)
        return normalized_preferences

    @field_validator("preferences")
    @classmethod
    def preferences_must_be_short(cls, value: list[str]) -> list[str]:
        too_long = [item for item in value if len(item) > 80]
        if too_long:
            raise ValueError("each preference must be 80 characters or fewer")
        return value


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    user_context: UserContext | None = None
    session_id: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value

    @field_validator("session_id")
    @classmethod
    def session_id_must_be_safe_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not SESSION_ID_PATTERN.fullmatch(value):
            raise ValueError("session_id may contain only letters, numbers, underscores, and hyphens")
        return value


class ToolObservation(BaseModel):
    step: int
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)
    observation_excerpt: str | None = None


class AgentMetadata(BaseModel):
    trace_id: str | None = None
    session_id: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    intent: str | None = None
    primary_intent: str | None = None
    resolved_intents: list[str] = Field(default_factory=list)
    agent_mode: str = "langchain_agent_executor"
    observability: dict[str, Any] = Field(default_factory=dict)
    model: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    trace_summary: dict[str, Any] = Field(default_factory=dict)
    tools_used: list[str] = Field(default_factory=list)
    observations: list[ToolObservation] = Field(default_factory=list)
    stop_reason: str = "final_answer"
    iterations: int = 0
    elapsed_ms: int = 0
    fallback_used: bool = False
    session_updates: dict[str, Any] = Field(default_factory=dict)
    security: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    answer: str
    metadata: AgentMetadata
