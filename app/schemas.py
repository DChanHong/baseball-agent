from typing import Any

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    favorite_team: str | None = None
    origin: str | None = None
    preferences: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str
    user_context: UserContext | None = None


class ToolObservation(BaseModel):
    step: int
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)


class AgentMetadata(BaseModel):
    intent: str | None = None
    agent_mode: str = "langchain_agent_executor"
    tools_used: list[str] = Field(default_factory=list)
    observations: list[ToolObservation] = Field(default_factory=list)
    stop_reason: str = "final_answer"
    iterations: int = 0
    elapsed_ms: int = 0
    fallback_used: bool = False


class ChatResponse(BaseModel):
    answer: str
    metadata: AgentMetadata
