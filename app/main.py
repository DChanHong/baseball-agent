from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.agent_loop import run_agent
from app.schemas import ChatRequest, ChatResponse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"

app = FastAPI(title="Baseball Game-Day Agent")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

SESSION_HISTORY_LIMIT = 8
SESSION_HISTORY: dict[str, list[dict[str, str]]] = {}


@app.get("/health")
def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "baseball-game-day-agent",
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
    session_id = request.session_id

    if session_id:
        history = SESSION_HISTORY.get(session_id, [])
        user_context["conversation_history"] = history[-SESSION_HISTORY_LIMIT:]

    result = run_agent(request.message, user_context=user_context or None)

    if session_id:
        history = SESSION_HISTORY.setdefault(session_id, [])
        history.append({"role": "user", "content": request.message})
        history.append({"role": "assistant", "content": result.get("answer", "")})
        SESSION_HISTORY[session_id] = history[-SESSION_HISTORY_LIMIT:]

    return result
