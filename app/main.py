from fastapi import FastAPI
from pydantic import BaseModel

from app.agent_loop import run_agent


app = FastAPI(title="Baseball Game-Day Agent")


class ChatRequest(BaseModel):
    message: str


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    return run_agent(request.message)
