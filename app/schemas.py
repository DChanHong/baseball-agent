from typing import Any

from pydantic import BaseModel, Field, field_validator


class UserContext(BaseModel):
    favorite_team: str | None = None
    origin: str | None = None
    preferences: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    user_context: UserContext | None = None
    session_id: str | None = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
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
