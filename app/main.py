from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.agent_loop import run_agent
from app.schemas import ChatRequest, ChatResponse
from app.tools import find_kbo_game


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"

app = FastAPI(title="Baseball Game-Day Agent")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

SESSION_HISTORY_LIMIT = 8
SESSION_HISTORY: dict[str, list[dict[str, str]]] = {}
SESSION_STATE: dict[str, dict[str, Any]] = {}


def _looks_like_schedule_lookup(message: str) -> bool:
    return any(keyword in message for keyword in ["경기", "일정", "직관", "보러", "다음주", "이번주"])


def _looks_like_action_followup(message: str) -> bool:
    return any(keyword in message for keyword in ["좌석", "자리", "추천", "예매", "동선", "막차", "교통", "날씨"])


def _select_game_from_candidates(message: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    compact = message.replace(" ", "")
    weekday_map = {
        "월": ["월", "월요일"],
        "화": ["화", "화요일"],
        "수": ["수", "수요일"],
        "목": ["목", "목요일"],
        "금": ["금", "금요일"],
        "토": ["토", "토요일", "주말"],
        "일": ["일", "일요일"],
    }

    for candidate in candidates:
        date_value = candidate.get("date")
        if date_value and date_value.replace("-", "") in compact:
            return candidate
        if date_value and date_value[5:].replace("-", "월") + "일" in compact:
            return candidate

    for weekday, aliases in weekday_map.items():
        if any(alias in compact for alias in aliases):
            matches = [candidate for candidate in candidates if candidate.get("weekday") == weekday]
            if len(matches) == 1:
                return matches[0]

    if len(candidates) == 1:
        return candidates[0]
    return None


def _game_label(game: dict[str, Any]) -> str:
    return (
        f"{game.get('date')}({game.get('weekday')}) {game.get('time')} "
        f"{game.get('away_team')} vs {game.get('home_team')} {game.get('stadium_name')}"
    )


def _preprocess_request(message: str, user_context: dict[str, Any], session_state: dict[str, Any]) -> str:
    if _looks_like_schedule_lookup(message):
        schedule_result = find_kbo_game(date=message, team_query=message)
        if schedule_result["ok"] and schedule_result["status"] == "ambiguous_game":
            candidates = schedule_result["data"].get("candidates") or []
            session_state["candidate_games"] = candidates
            user_context["candidate_games"] = candidates
        elif schedule_result["ok"] and schedule_result["status"] == "found":
            selected_game = schedule_result["data"]
            session_state["candidate_games"] = [selected_game]
            session_state["selected_game"] = selected_game
            user_context["selected_game"] = selected_game

    candidates = session_state.get("candidate_games") or []
    if candidates:
        selected_game = _select_game_from_candidates(message, candidates)
        if selected_game:
            session_state["selected_game"] = selected_game
            user_context["selected_game"] = selected_game

    selected_game = session_state.get("selected_game")
    if selected_game and _looks_like_action_followup(message):
        user_context["selected_game"] = selected_game
        scoring_instruction = ""
        if any(keyword in message for keyword in ["좌석", "자리", "추천"]):
            scoring_instruction = " 좌석 추천이면 search_baseball_knowledge 후 score_seat_candidates까지 호출해 추천 순위를 만들어줘."
        return f"{_game_label(selected_game)} 경기 기준으로 답변해줘.{scoring_instruction} 사용자 원문: {message}"

    if candidates:
        user_context["candidate_games"] = candidates
    return message


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
    session_state = SESSION_STATE.setdefault(session_id, {}) if session_id else {}

    if session_id:
        history = SESSION_HISTORY.get(session_id, [])
        user_context["conversation_history"] = history[-SESSION_HISTORY_LIMIT:]

    processed_message = _preprocess_request(request.message, user_context, session_state)
    result = run_agent(processed_message, user_context=user_context or None)

    if session_id:
        history = SESSION_HISTORY.setdefault(session_id, [])
        history.append({"role": "user", "content": request.message})
        history.append({"role": "assistant", "content": result.get("answer", "")})
        SESSION_HISTORY[session_id] = history[-SESSION_HISTORY_LIMIT:]
        SESSION_STATE[session_id] = session_state

    return result
