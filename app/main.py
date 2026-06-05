from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.agent_loop import build_security_refusal_response, run_agent
from app.schemas import ChatRequest, ChatResponse
from app.security import analyze_message, refusal_answer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"

app = FastAPI(title="Baseball Game-Day Agent")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

SESSION_HISTORY_LIMIT = 8
SESSION_USER_MESSAGE_LIMIT = 500
SESSION_ASSISTANT_MESSAGE_LIMIT = 1000
TRUNCATED_SUFFIX = "...[truncated]"
SERVER_SESSION_ID = f"server-{uuid4().hex}"
SESSION_HISTORY: dict[str, list[dict[str, str]]] = {}
SESSION_STATE: dict[str, dict[str, Any]] = {}


def _truncate_for_history(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - len(TRUNCATED_SUFFIX)] + TRUNCATED_SUFFIX


def _attach_session_context(user_context: dict[str, Any], session_state: dict[str, Any]) -> None:
    if session_state.get("candidate_games"):
        user_context["candidate_games"] = session_state["candidate_games"]
    if session_state.get("selected_game"):
        user_context["selected_game"] = session_state["selected_game"]


def _apply_session_updates(session_state: dict[str, Any], result: dict[str, Any]) -> None:
    metadata = result.get("metadata") or {}
    updates = metadata.get("session_updates") or {}
    if updates.get("candidate_games"):
        session_state["candidate_games"] = updates["candidate_games"]
    if updates.get("selected_game"):
        session_state["selected_game"] = updates["selected_game"]
        session_state["candidate_games"] = [updates["selected_game"]]


@app.get("/health")
def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "baseball-game-day-agent",
        "default_session_id": SERVER_SESSION_ID,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    template_path = TEMPLATES_DIR / "index.html"
    if template_path.exists():
        return templates.TemplateResponse(request, "index.html")

    return HTMLResponse(
        """
        <!doctype html>
        <html lang="ko">
          <head>
            <meta charset="utf-8">
            <title>Baseball Game-Day Agent</title>
          </head>
          <body>
            <h1>Baseball Game-Day Agent</h1>
            <p>채팅 클라이언트는 다음 단계에서 추가됩니다.</p>
          </body>
        </html>
        """
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> dict[str, Any]:
    user_context = request.user_context.model_dump() if request.user_context else {}
    session_id = request.session_id or SERVER_SESSION_ID
    security_analysis = analyze_message(request.message)
    processed_message = security_analysis["processed_message"]
    security = security_analysis["security"]

    if security.get("blocked"):
        return build_security_refusal_response(
            answer=refusal_answer(security.get("refusal_code")),
            session_id=session_id,
            security=security,
        )

    if not processed_message.strip():
        return run_agent(
            processed_message,
            user_context=None,
            session_id=session_id,
            original_message=request.message,
            security=security,
        )

    session_state = SESSION_STATE.setdefault(session_id, {})

    history = SESSION_HISTORY.get(session_id, [])
    user_context["conversation_history"] = history[-SESSION_HISTORY_LIMIT:]
    _attach_session_context(user_context, session_state)

    result = run_agent(
        processed_message,
        user_context=user_context or None,
        session_id=session_id,
        original_message=request.message,
        security=security,
    )

    _apply_session_updates(session_state, result)
    history = SESSION_HISTORY.setdefault(session_id, [])
    history.append({"role": "user", "content": _truncate_for_history(processed_message, SESSION_USER_MESSAGE_LIMIT)})
    history.append(
        {
            "role": "assistant",
            "content": _truncate_for_history(result.get("answer", ""), SESSION_ASSISTANT_MESSAGE_LIMIT),
        }
    )
    SESSION_HISTORY[session_id] = history[-SESSION_HISTORY_LIMIT:]
    SESSION_STATE[session_id] = session_state

    return result
