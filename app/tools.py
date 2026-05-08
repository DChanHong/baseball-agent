import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from langchain_core.documents import Document
except ImportError:
    @dataclass
    class Document:
        page_content: str
        metadata: dict[str, Any]


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
STATIC_DATA_DIR = DATA_DIR / "static"
STADIUM_SEAT_DIR = RAW_DATA_DIR / "stadium_seats"
FAISS_INDEX_DIR = DATA_DIR / "index" / "faiss"
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"

if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env", override=True)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _as_text(value: Any, default: str = "정보 없음") -> str:
    if value is None:
        return default
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else default
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _format_price(price: Any) -> str:
    if not isinstance(price, dict) or not price:
        return "가격 정보 없음"

    weekday = price.get("weekday")
    weekend = price.get("weekend")
    if weekday is None and weekend is None:
        return "가격 정보 없음"
    return f"주중 {weekday if weekday is not None else '정보 없음'}원, 주말 {weekend if weekend is not None else '정보 없음'}원"


def _metadata(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


def _get_openai_embeddings():
    try:
        from langchain_openai import OpenAIEmbeddings
    except ImportError as exc:
        raise RuntimeError("langchain-openai 패키지가 설치되지 않았습니다.") from exc

    model = os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_OPENAI_EMBEDDING_MODEL)
    return OpenAIEmbeddings(model=model)


def _get_faiss_class():
    try:
        from langchain_community.vectorstores import FAISS
    except ImportError as exc:
        raise RuntimeError(
            "langchain-community 패키지가 설치되지 않았습니다. requirements.txt에 langchain-community를 추가해야 합니다."
        ) from exc

    return FAISS


def _faiss_index_exists(index_dir: Path = FAISS_INDEX_DIR) -> bool:
    return (index_dir / "index.faiss").exists() and (index_dir / "index.pkl").exists()


def _is_openai_auth_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "incorrect api key" in message or "invalid_api_key" in message or "status': 401" in message


def _tool_success(status: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "status": status, "data": data, "error": None}


def _tool_error(status: str, code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status": status,
        "data": None,
        "error": {"code": code, "message": message},
    }


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None

    stripped = value.strip()
    iso_match = re.search(r"(20\d{2})[-./년\s]+(\d{1,2})[-./월\s]+(\d{1,2})", stripped)
    if iso_match:
        year, month, day = (int(part) for part in iso_match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    compact_match = re.search(r"(20\d{2})(\d{2})(\d{2})", stripped)
    if compact_match:
        year, month, day = (int(part) for part in compact_match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    return None


def _load_team_aliases() -> list[dict[str, Any]]:
    payload = _read_json(STATIC_DATA_DIR / "team_aliases.json")
    return (payload.get("data") or {}).get("teams") or []


def _normalize_team(team_query: str | None) -> dict[str, Any] | None:
    if not team_query:
        return None

    query = team_query.replace(" ", "").lower()
    for team in _load_team_aliases():
        candidates = [team.get("team"), team.get("schedule_name"), *(team.get("aliases") or [])]
        for candidate in candidates:
            if candidate and str(candidate).replace(" ", "").lower() in query:
                return team

    return None


def _load_all_schedule_games() -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    for path in sorted(RAW_DATA_DIR.glob("kbo_schedule_2026_*.json")):
        payload = _read_json(path)
        for game in (payload.get("data") or {}).get("games") or []:
            copied = dict(game)
            copied["_source_file"] = str(path.relative_to(PROJECT_ROOT))
            games.append(copied)
    return games


def _load_stadiums() -> list[dict[str, Any]]:
    payload = _read_json(STATIC_DATA_DIR / "stadium_metadata.json")
    return (payload.get("data") or {}).get("stadiums") or []


def _normalize_stadium(stadium_id: str | None = None, stadium_name: str | None = None) -> dict[str, Any] | None:
    id_query = stadium_id.strip().lower() if stadium_id else None
    name_query = stadium_name.replace(" ", "").lower() if stadium_name else None

    for stadium in _load_stadiums():
        names = [stadium.get("id"), stadium.get("name"), stadium.get("short_name"), stadium.get("city")]
        if id_query and str(stadium.get("id", "")).lower() == id_query:
            return stadium
        if name_query:
            for name in names:
                if name and str(name).replace(" ", "").lower() in name_query:
                    return stadium
            for home_team in stadium.get("home_teams") or []:
                if str(home_team).replace(" ", "").lower() in name_query:
                    return stadium

    return None


def _stadium_id_from_schedule(schedule_stadium: dict[str, Any]) -> str | None:
    stadium = _normalize_stadium(stadium_name=schedule_stadium.get("name"))
    if stadium:
        return stadium.get("id")
    stadium = _normalize_stadium(stadium_name=schedule_stadium.get("short_name"))
    if stadium:
        return stadium.get("id")
    return None


def build_stadium_seat_documents(seat_dir: Path = STADIUM_SEAT_DIR) -> list[Document]:
    documents: list[Document] = []

    for path in sorted(seat_dir.glob("*_seats.json")):
        if path.name == "crawl_all_stadium_seats_summary.json":
            continue

        payload = _read_json(path)
        data = payload.get("data") or {}
        source = payload.get("metadata") or {}
        source_url = source.get("source_url")

        stadium_id = data.get("stadium_id")
        stadium_name = data.get("stadium_name")
        team = data.get("team")

        for index, zone in enumerate(data.get("seat_zones") or [], start=1):
            price_text = _format_price(zone.get("price_krw"))
            tags = zone.get("tags") or []
            use_cases = zone.get("recommendation_use_cases") or []
            notes = zone.get("notes") or []

            content = "\n".join(
                [
                    f"좌석 정보: {stadium_name} {team} {zone.get('seat_name')}",
                    f"구장: {stadium_name}",
                    f"구장 ID: {stadium_id}",
                    f"팀: {team}",
                    f"좌석명: {zone.get('seat_name')}",
                    f"분류: {_as_text(zone.get('category'))}",
                    f"대상: {_as_text(zone.get('audience'))}",
                    f"방향/구역: {_as_text(zone.get('side'))}",
                    f"가격: {price_text}",
                    f"태그: {_as_text(tags)}",
                    f"추천 상황: {_as_text(use_cases)}",
                    f"주의사항: {_as_text(notes)}",
                    f"출처: {_as_text(source_url)}",
                ]
            )

            documents.append(
                Document(
                    page_content=content,
                    metadata=_metadata(
                        source_type="stadium_seat",
                        source_file=str(path.relative_to(PROJECT_ROOT)),
                        source_url=source_url,
                        stadium_id=stadium_id,
                        stadium_name=stadium_name,
                        team=team,
                        seat_name=zone.get("seat_name"),
                        category=zone.get("category"),
                        audience=zone.get("audience"),
                        document_unit="seat_zone",
                        document_index=index,
                        data_limitations="좌석/가격 데이터는 크롤링 시점 기준이며 실시간 잔여석을 반영하지 않는다.",
                    ),
                )
            )

    return documents


def build_stadium_metadata_documents(path: Path = STATIC_DATA_DIR / "stadium_metadata.json") -> list[Document]:
    payload = _read_json(path)
    stadiums = (payload.get("data") or {}).get("stadiums") or []
    documents: list[Document] = []

    for stadium in stadiums:
        ticketing = stadium.get("ticketing") or {}
        coordinates = stadium.get("coordinates") or {}
        weather_grid = stadium.get("weather_grid") or {}

        content = "\n".join(
            [
                f"구장 정보: {stadium.get('name')}",
                f"구장 ID: {stadium.get('id')}",
                f"짧은 이름: {stadium.get('short_name')}",
                f"도시: {stadium.get('city')}",
                f"홈팀: {_as_text(stadium.get('home_teams'))}",
                f"돔구장 여부: {stadium.get('is_dome')}",
                f"주소: {stadium.get('address')}",
                f"좌표: 위도 {coordinates.get('lat')}, 경도 {coordinates.get('lng')}",
                f"기상청 grid: nx {weather_grid.get('nx')}, ny {weather_grid.get('ny')}",
                f"수용 인원: {_as_text(stadium.get('capacity'))}",
                f"예매처: {_as_text(ticketing.get('platforms'))}",
                f"예매 메모: {_as_text(ticketing.get('note'))}",
            ]
        )

        documents.append(
            Document(
                page_content=content,
                metadata=_metadata(
                    source_type="stadium_metadata",
                    source_file=str(path.relative_to(PROJECT_ROOT)),
                    stadium_id=stadium.get("id"),
                    stadium_name=stadium.get("name"),
                    city=stadium.get("city"),
                    home_teams=_as_text(stadium.get("home_teams"), default=""),
                    is_dome=stadium.get("is_dome"),
                    document_unit="stadium",
                    data_limitations="정적 구장 seed 데이터이며 좌표와 grid는 운영 중 보정될 수 있다.",
                ),
            )
        )

    return documents


def build_ticketing_guide_documents(path: Path = STATIC_DATA_DIR / "ticketing_guides.json") -> list[Document]:
    payload = _read_json(path)
    guides = (payload.get("data") or {}).get("guides") or []
    documents: list[Document] = []

    for guide in guides:
        content = "\n".join(
            [
                f"예매 가이드: {guide.get('team')}",
                f"팀: {guide.get('team')}",
                f"일정 팀명: {guide.get('schedule_name')}",
                f"구장 ID: {guide.get('stadium_id')}",
                f"예매처: {guide.get('platform')}",
                f"예매처 URL: {guide.get('platform_url')}",
                f"공식 URL: {guide.get('official_url')}",
                f"예매 난이도: {guide.get('difficulty')}",
                f"오픈 rule: {guide.get('open_rule')}",
                f"팁: {_as_text(guide.get('tips'))}",
                f"데이터 한계: {_as_text(guide.get('data_limitations'))}",
            ]
        )

        documents.append(
            Document(
                page_content=content,
                metadata=_metadata(
                    source_type="ticketing_guide",
                    source_file=str(path.relative_to(PROJECT_ROOT)),
                    source_url=guide.get("source_url") or guide.get("official_url"),
                    stadium_id=guide.get("stadium_id"),
                    team=guide.get("team"),
                    schedule_name=guide.get("schedule_name"),
                    platform=guide.get("platform"),
                    difficulty=guide.get("difficulty"),
                    document_unit="team_ticketing_guide",
                    data_limitations=guide.get("data_limitations"),
                ),
            )
        )

    return documents


def build_logistics_guide_documents(path: Path = STATIC_DATA_DIR / "logistics_guides.json") -> list[Document]:
    payload = _read_json(path)
    data = payload.get("data") or {}
    guides = data.get("guides") or []
    documents: list[Document] = []

    for guide in guides:
        route_summaries = [
            f"{route.get('mode')}: {route.get('summary')} ({route.get('estimated_duration_minutes')}분, risk={route.get('risk')})"
            for route in guide.get("recommended_routes") or []
        ]
        return_plan = guide.get("return_plan") or {}

        content = "\n".join(
            [
                f"원정 동선 가이드: {guide.get('origin')} -> {guide.get('stadium_name')}",
                f"출발지: {guide.get('origin')}",
                f"구장 ID: {guide.get('stadium_id')}",
                f"구장명: {guide.get('stadium_name')}",
                f"추천 경로: {_as_text(route_summaries)}",
                f"당일 복귀 가능성: {_as_text(return_plan.get('same_day_possible'))}",
                f"복귀 메모: {_as_text(return_plan.get('note'))}",
                f"대안: {_as_text(guide.get('fallback_plan'))}",
                f"데이터 한계: {_as_text(guide.get('data_limitations'))}",
            ]
        )

        documents.append(
            Document(
                page_content=content,
                metadata=_metadata(
                    source_type="logistics_guide",
                    source_file=str(path.relative_to(PROJECT_ROOT)),
                    origin=guide.get("origin"),
                    stadium_id=guide.get("stadium_id"),
                    stadium_name=guide.get("stadium_name"),
                    same_day_possible=return_plan.get("same_day_possible"),
                    document_unit="origin_stadium_logistics",
                    data_limitations=guide.get("data_limitations"),
                ),
            )
        )

    fallback = data.get("generic_fallback")
    if fallback:
        content = "\n".join(
            [
                "원정 동선 일반 fallback 가이드",
                f"확인 항목: {_as_text(fallback.get('recommended_checks'))}",
                f"당일 복귀 판단 rule: {_as_text(fallback.get('same_day_return_rule'))}",
            ]
        )
        documents.append(
            Document(
                page_content=content,
                metadata=_metadata(
                    source_type="logistics_guide",
                    source_file=str(path.relative_to(PROJECT_ROOT)),
                    document_unit="generic_logistics_fallback",
                    data_limitations=(payload.get("metadata") or {}).get("data_limitations"),
                ),
            )
        )

    return documents


def build_rag_documents() -> list[Document]:
    documents: list[Document] = []
    documents.extend(build_stadium_seat_documents())
    documents.extend(build_stadium_metadata_documents())
    documents.extend(build_ticketing_guide_documents())
    documents.extend(build_logistics_guide_documents())
    return documents


def build_faiss_index(index_dir: Path = FAISS_INDEX_DIR) -> dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        return {
            "ok": False,
            "status": "missing_required_input",
            "data": None,
            "error": {
                "code": "MISSING_OPENAI_API_KEY",
                "message": "FAISS 인덱스를 생성하려면 OPENAI_API_KEY 환경변수가 필요합니다.",
            },
        }

    try:
        documents = build_rag_documents()
        if not documents:
            return {
                "ok": False,
                "status": "no_documents",
                "data": None,
                "error": {
                    "code": "NO_RAG_DOCUMENTS",
                    "message": "FAISS 인덱스를 생성할 RAG 문서가 없습니다.",
                },
            }

        FAISS = _get_faiss_class()
        embeddings = _get_openai_embeddings()
        vectorstore = FAISS.from_documents(documents, embeddings)

        index_dir.mkdir(parents=True, exist_ok=True)
        vectorstore.save_local(str(index_dir))
    except Exception as exc:
        if _is_openai_auth_error(exc):
            return {
                "ok": False,
                "status": "auth_failed",
                "data": None,
                "error": {
                    "code": "INVALID_OPENAI_API_KEY",
                    "message": "OpenAI API key가 유효하지 않아 FAISS 인덱스를 생성하지 못했습니다.",
                },
            }

        return {
            "ok": False,
            "status": "external_api_failed",
            "data": None,
            "error": {
                "code": "FAISS_INDEX_BUILD_FAILED",
                "message": str(exc),
            },
        }

    counts: dict[str, int] = {}
    for document in documents:
        source_type = document.metadata.get("source_type", "unknown")
        counts[source_type] = counts.get(source_type, 0) + 1

    return {
        "ok": True,
        "status": "built",
        "data": {
            "index_dir": str(index_dir.relative_to(PROJECT_ROOT)),
            "document_count": len(documents),
            "counts_by_source_type": counts,
            "embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_OPENAI_EMBEDDING_MODEL),
        },
        "error": None,
    }


def load_faiss_index(index_dir: Path = FAISS_INDEX_DIR):
    if not _faiss_index_exists(index_dir):
        return {
            "ok": False,
            "status": "index_not_ready",
            "data": None,
            "error": {
                "code": "FAISS_INDEX_NOT_FOUND",
                "message": f"FAISS 인덱스가 없습니다. 먼저 build_faiss_index()를 실행하세요: {index_dir}",
            },
        }

    if not os.getenv("OPENAI_API_KEY"):
        return {
            "ok": False,
            "status": "missing_required_input",
            "data": None,
            "error": {
                "code": "MISSING_OPENAI_API_KEY",
                "message": "FAISS 인덱스 검색에는 query embedding 생성을 위한 OPENAI_API_KEY가 필요합니다.",
            },
        }

    try:
        FAISS = _get_faiss_class()
        embeddings = _get_openai_embeddings()
        vectorstore = FAISS.load_local(
            str(index_dir),
            embeddings,
            allow_dangerous_deserialization=True,
        )
    except Exception as exc:
        if _is_openai_auth_error(exc):
            return {
                "ok": False,
                "status": "auth_failed",
                "data": None,
                "error": {
                    "code": "INVALID_OPENAI_API_KEY",
                    "message": "OpenAI API key가 유효하지 않아 FAISS 인덱스를 로드하지 못했습니다.",
                },
            }

        return {
            "ok": False,
            "status": "index_load_failed",
            "data": None,
            "error": {
                "code": "FAISS_INDEX_LOAD_FAILED",
                "message": str(exc),
            },
        }

    return {
        "ok": True,
        "status": "loaded",
        "data": {
            "index_dir": str(index_dir.relative_to(PROJECT_ROOT)),
            "vectorstore": vectorstore,
            "embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_OPENAI_EMBEDDING_MODEL),
        },
        "error": None,
    }


def search_faiss_documents(
    query: str,
    top_k: int = 4,
    index_dir: Path = FAISS_INDEX_DIR,
) -> dict[str, Any]:
    if not query.strip():
        return {
            "ok": False,
            "status": "missing_required_input",
            "data": None,
            "error": {
                "code": "MISSING_QUERY",
                "message": "검색 query가 필요합니다.",
            },
        }

    load_result = load_faiss_index(index_dir)
    if not load_result["ok"]:
        return load_result

    try:
        vectorstore = load_result["data"]["vectorstore"]
        documents = vectorstore.similarity_search(query, k=top_k)
    except Exception as exc:
        return {
            "ok": False,
            "status": "search_failed",
            "data": None,
            "error": {
                "code": "FAISS_SEARCH_FAILED",
                "message": str(exc),
            },
        }

    if not documents:
        return {
            "ok": False,
            "status": "no_documents_found",
            "data": None,
            "error": {
                "code": "NO_DOCUMENTS_FOUND",
                "message": "검색 조건에 맞는 RAG 문서를 찾지 못했습니다.",
            },
        }

    return {
        "ok": True,
        "status": "found",
        "data": {
            "query": query,
            "documents": [
                {
                    "content": document.page_content,
                    "metadata": document.metadata,
                }
                for document in documents
            ],
        },
        "error": None,
    }


def get_faiss_index_status(index_dir: Path = FAISS_INDEX_DIR) -> dict[str, Any]:
    exists = _faiss_index_exists(index_dir)
    return {
        "ok": exists,
        "status": "ready" if exists else "index_not_ready",
        "data": {
            "index_dir": str(index_dir.relative_to(PROJECT_ROOT)),
            "index_faiss_exists": (index_dir / "index.faiss").exists(),
            "index_pkl_exists": (index_dir / "index.pkl").exists(),
            "embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_OPENAI_EMBEDDING_MODEL),
        },
        "error": None
        if exists
        else {
            "code": "FAISS_INDEX_NOT_FOUND",
            "message": "FAISS 인덱스가 아직 생성되지 않았습니다.",
        },
    }


def find_kbo_game(
    date: str | None = None,
    team_query: str | None = None,
    stadium_query: str | None = None,
    opponent_query: str | None = None,
) -> dict[str, Any]:
    parsed_date = _parse_date(date)
    if not parsed_date:
        return _tool_error("missing_required_input", "MISSING_DATE", "경기 날짜가 필요합니다.")

    team = _normalize_team(team_query)
    if not team:
        return _tool_error("missing_required_input", "MISSING_TEAM", "경기 팀 또는 응원 팀이 필요합니다.")

    opponent = _normalize_team(opponent_query)
    stadium = _normalize_stadium(stadium_name=stadium_query) if stadium_query else None
    schedule_name = team.get("schedule_name")
    opponent_schedule_name = opponent.get("schedule_name") if opponent else None

    candidates = []
    for game in _load_all_schedule_games():
        teams = game.get("teams") or {}
        game_teams = {teams.get("home"), teams.get("away")}
        if game.get("date") != parsed_date:
            continue
        if schedule_name not in game_teams:
            continue
        if opponent_schedule_name and opponent_schedule_name not in game_teams:
            continue
        if stadium and _stadium_id_from_schedule(game.get("stadium") or {}) != stadium.get("id"):
            continue
        candidates.append(game)

    if not candidates:
        return _tool_error("not_found", "GAME_NOT_FOUND", "조건에 맞는 KBO 경기를 찾지 못했습니다.")

    if len(candidates) > 1:
        return _tool_success(
            "ambiguous_game",
            {
                "candidates": [
                    {
                        "game_id": game.get("game_id"),
                        "date": game.get("date"),
                        "time": game.get("time"),
                        "home_team": (game.get("teams") or {}).get("home"),
                        "away_team": (game.get("teams") or {}).get("away"),
                        "stadium_name": (game.get("stadium") or {}).get("name"),
                    }
                    for game in candidates
                ]
            },
        )

    game = candidates[0]
    schedule_stadium = game.get("stadium") or {}
    teams = game.get("teams") or {}
    stadium_id = _stadium_id_from_schedule(schedule_stadium)
    normalized_stadium = _normalize_stadium(stadium_id=stadium_id) if stadium_id else None
    game_id = game.get("game_id") or f"{game.get('date')}-{teams.get('away')}-{teams.get('home')}-{schedule_stadium.get('short_name')}"

    return _tool_success(
        "found",
        {
            "game_id": game_id,
            "date": game.get("date"),
            "time": game.get("time"),
            "home_team": teams.get("home"),
            "away_team": teams.get("away"),
            "home_team_full": (_normalize_team(teams.get("home")) or {}).get("team"),
            "away_team_full": (_normalize_team(teams.get("away")) or {}).get("team"),
            "stadium_id": stadium_id,
            "stadium_name": (normalized_stadium or {}).get("name") or schedule_stadium.get("name"),
            "stadium_short_name": schedule_stadium.get("short_name"),
            "source_url": (game.get("source") or {}).get("url"),
        },
    )


def get_stadium_info(
    stadium_id: str | None = None,
    stadium_name: str | None = None,
    home_team: str | None = None,
) -> dict[str, Any]:
    stadium = _normalize_stadium(stadium_id=stadium_id, stadium_name=stadium_name)
    if not stadium and home_team:
        normalized_team = _normalize_team(home_team)
        team_name = normalized_team.get("team") if normalized_team else home_team
        for candidate in _load_stadiums():
            if team_name in (candidate.get("home_teams") or []):
                stadium = candidate
                break

    if not stadium:
        return _tool_error("not_found", "STADIUM_NOT_FOUND", "지원하는 구장 정보에서 찾지 못했습니다.")

    return _tool_success(
        "found",
        {
            "stadium_id": stadium.get("id"),
            "stadium_name": stadium.get("name"),
            "short_name": stadium.get("short_name"),
            "city": stadium.get("city"),
            "is_dome": stadium.get("is_dome"),
            "home_teams": stadium.get("home_teams") or [],
            "address": stadium.get("address"),
            "coordinates": stadium.get("coordinates"),
            "weather_grid": stadium.get("weather_grid"),
            "capacity": stadium.get("capacity"),
            "ticketing": stadium.get("ticketing") or {},
        },
    )


def get_weather_context(
    game_date: str | None = None,
    game_time: str | None = None,
    stadium_id: str | None = None,
    is_dome: bool = False,
    weather_grid: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parsed_date = _parse_date(game_date)
    if not parsed_date:
        return _tool_error("missing_required_input", "MISSING_DATE", "경기 날짜가 필요합니다.")

    try:
        target_date = date.fromisoformat(parsed_date)
    except ValueError:
        return _tool_error("missing_required_input", "INVALID_DATE", "경기 날짜 형식이 올바르지 않습니다.")

    days_until = (target_date - date.today()).days
    hour = 18
    if game_time:
        time_match = re.search(r"(\d{1,2}):(\d{2})", game_time)
        if time_match:
            hour = int(time_match.group(1))

    risk_flags: list[str] = []
    if is_dome:
        recommendation_mode = "preference_based"
        forecast_level = "dome_adjusted"
        forecast_reliability = "medium"
        weather_summary = "돔구장이라 우천 리스크를 낮게 보고 시야, 응원, 가격 선호를 우선합니다."
    elif 0 <= days_until <= 3:
        recommendation_mode = "weather_based"
        forecast_level = "short_term"
        forecast_reliability = "high"
        if hour < 17:
            risk_flags.append("heat")
            weather_summary = "낮 경기 기준 햇빛과 더위 리스크가 있어 그늘, 상단, 통로 접근성을 우선합니다."
        else:
            weather_summary = "단기 예보 사용 구간입니다. 야외 구장은 우천과 체감온도 리스크를 함께 봅니다."
    elif 4 <= days_until <= 10:
        recommendation_mode = "weather_risk_based"
        forecast_level = "medium_term"
        forecast_reliability = "medium"
        if hour < 17:
            risk_flags.append("heat")
        weather_summary = "중기 예보 구간이라 정확한 날씨보다 우천/폭염 가능성을 보수적으로 반영합니다."
    else:
        recommendation_mode = "preference_based"
        forecast_level = "unavailable"
        forecast_reliability = "none"
        weather_summary = "11일 이후 경기라 날씨 예보를 사용하지 않고 성향 기반으로 추천합니다."

    status = "forecast_unavailable_by_policy" if forecast_level == "unavailable" else recommendation_mode
    return _tool_success(
        status,
        {
            "stadium_id": stadium_id,
            "game_date": parsed_date,
            "game_time": game_time,
            "recommendation_mode": recommendation_mode,
            "forecast_level": forecast_level,
            "forecast_reliability": forecast_reliability,
            "days_until_game": days_until,
            "risk_flags": risk_flags,
            "weather_summary": weather_summary,
            "weather_grid": weather_grid,
        },
    )


def search_baseball_knowledge(
    query: str,
    purpose: str,
    stadium_id: str | None = None,
    team: str | None = None,
    top_k: int = 4,
) -> dict[str, Any]:
    if not query.strip():
        return _tool_error("missing_required_input", "MISSING_QUERY", "검색 query가 필요합니다.")

    enriched_query_parts = [query, purpose]
    if stadium_id:
        enriched_query_parts.append(stadium_id)
    if team:
        enriched_query_parts.append(team)

    result = search_faiss_documents(" ".join(enriched_query_parts), top_k=top_k)
    if not result["ok"]:
        return result

    documents = result["data"]["documents"]
    if stadium_id or team:
        normalized_team = (_normalize_team(team) or {}).get("team") if team else None
        filtered = []
        for document in documents:
            metadata = document.get("metadata") or {}
            if stadium_id and metadata.get("stadium_id") and metadata.get("stadium_id") != stadium_id:
                continue
            if normalized_team and metadata.get("team") and metadata.get("team") != normalized_team:
                continue
            filtered.append(document)
        if filtered:
            documents = filtered

    return _tool_success(
        "found",
        {
            "query": query,
            "purpose": purpose,
            "documents": documents,
        },
    )


def _extract_price_from_content(content: str) -> int | None:
    prices = [int(match.replace(",", "")) for match in re.findall(r"(\d[\d,]*)원", content)]
    return min(prices) if prices else None


def _preference_terms(preferences: list[str] | str | None) -> list[str]:
    if preferences is None:
        return []
    if isinstance(preferences, str):
        return [item.strip() for item in re.split(r"[,/ ]+", preferences) if item.strip()]
    return [str(item).strip() for item in preferences if str(item).strip()]


def score_seat_candidates(
    game: dict[str, Any],
    weather_context: dict[str, Any],
    seat_documents: list[dict[str, Any]],
    preferences: list[str] | str | None = None,
    budget: int | None = None,
    cheering_team: str | None = None,
) -> dict[str, Any]:
    if not seat_documents:
        return _tool_error("no_candidates", "NO_SEAT_DOCUMENTS", "점수화할 좌석 후보가 없습니다.")

    preference_values = _preference_terms(preferences)
    risk_flags = set((weather_context or {}).get("risk_flags") or [])
    recommendation_mode = (weather_context or {}).get("recommendation_mode", "preference_based")
    normalized_cheering_team = _normalize_team(cheering_team) if cheering_team else None
    limitations: set[str] = set()
    scored: list[dict[str, Any]] = []

    for document in seat_documents:
        content = document.get("content") or document.get("page_content") or ""
        metadata = document.get("metadata") or {}
        if metadata.get("source_type") != "stadium_seat":
            continue

        score = 50
        reasons: list[str] = []
        lower_content = content.lower()
        seat_name = metadata.get("seat_name") or "좌석"
        price = _extract_price_from_content(content)

        if budget and price:
            if price <= budget:
                score += 12
                reasons.append("예산 범위 안")
            else:
                score -= 10
                reasons.append("예산 초과 가능")
        elif price is None:
            limitations.add("PRICE_DATA_LIMITED")

        for preference in preference_values:
            pref = preference.lower()
            if pref in lower_content:
                score += 10
                reasons.append(f"{preference} 선호와 일치")
            elif preference in ("가성비", "저렴", "예산") and any(token in lower_content for token in ["budget", "상단", "외야", "네이비"]):
                score += 10
                reasons.append("가성비 선호와 일치")
            elif preference in ("응원", "원정") and any(token in lower_content for token in ["cheering", "응원", "3루"]):
                score += 10
                reasons.append("응원 선호와 일치")
            elif preference in ("시야", "관람") and any(token in lower_content for token in ["view", "네이비", "중앙"]):
                score += 8
                reasons.append("시야 선호와 일치")

        if "heat" in risk_flags and any(token in lower_content for token in ["upper_deck", "상단", "네이비"]):
            score += 8
            reasons.append("더위 리스크에서 상단/시야형 좌석 우선")
        if recommendation_mode == "preference_based":
            score += 3

        if normalized_cheering_team and metadata.get("team") == normalized_cheering_team.get("team"):
            score += 4
            reasons.append("응원 팀 좌석 데이터와 일치")

        if not reasons:
            reasons.append("RAG 검색 후보")

        scored.append(
            {
                "seat_name": seat_name,
                "score": max(0, min(100, score)),
                "reasons": reasons[:4],
                "price_hint_krw": price,
                "stadium_id": metadata.get("stadium_id"),
                "team": metadata.get("team"),
                "source_url": metadata.get("source_url"),
                "data_limitations": metadata.get("data_limitations"),
            }
        )

    if not scored:
        return _tool_error("no_candidates", "NO_SEAT_DOCUMENTS", "점수화할 좌석 후보가 없습니다.")

    scored.sort(key=lambda item: item["score"], reverse=True)
    if any(item.get("price_hint_krw") is None for item in scored):
        limitations.add("PRICE_DATA_LIMITED")

    return _tool_success(
        "scored",
        {
            "game": game,
            "recommendation_mode": recommendation_mode,
            "recommendations": scored[:3],
            "limitations": sorted(limitations),
        },
    )


def get_ticketing_guide(
    team: str | None = None,
    stadium_id: str | None = None,
    game_date: str | None = None,
    opponent: str | None = None,
    popularity_hint: str | None = None,
) -> dict[str, Any]:
    if not team and not stadium_id:
        return _tool_error("missing_required_input", "MISSING_TEAM", "예매 가이드를 찾으려면 팀 또는 구장 정보가 필요합니다.")

    normalized_team = _normalize_team(team) if team else None
    payload = _read_json(STATIC_DATA_DIR / "ticketing_guides.json")
    guides = (payload.get("data") or {}).get("guides") or []

    for guide in guides:
        if normalized_team and guide.get("schedule_name") == normalized_team.get("schedule_name"):
            return _tool_success("found", dict(guide, game_date=game_date, opponent=opponent, popularity_hint=popularity_hint))
        if stadium_id and guide.get("stadium_id") == stadium_id:
            return _tool_success("found", dict(guide, game_date=game_date, opponent=opponent, popularity_hint=popularity_hint))

    return _tool_error("not_found", "TICKETING_GUIDE_NOT_FOUND", "해당 팀 또는 구장의 예매 가이드를 찾지 못했습니다.")


def get_logistics_guide(
    origin: str | None = None,
    stadium_id: str | None = None,
    stadium_name: str | None = None,
    game_date: str | None = None,
    game_time: str | None = None,
    preferred_transport: str | None = None,
    return_same_day: bool | None = None,
) -> dict[str, Any]:
    if not origin:
        return _tool_error("missing_required_input", "MISSING_ORIGIN", "원정 동선을 계산하려면 출발지가 필요합니다.")
    if not game_date:
        return _tool_error("missing_required_input", "MISSING_DATE", "원정 동선을 계산하려면 경기 날짜가 필요합니다.")
    if not game_time:
        return _tool_error("missing_required_input", "MISSING_TIME", "원정 동선을 계산하려면 경기 시간이 필요합니다.")

    stadium = _normalize_stadium(stadium_id=stadium_id, stadium_name=stadium_name)
    if not stadium:
        return _tool_error("missing_required_input", "MISSING_STADIUM", "원정 동선을 계산하려면 구장 정보가 필요합니다.")

    payload = _read_json(STATIC_DATA_DIR / "logistics_guides.json")
    data = payload.get("data") or {}
    origin_normalized = origin.replace(" ", "")

    for guide in data.get("guides") or []:
        if guide.get("origin", "").replace(" ", "") == origin_normalized and guide.get("stadium_id") == stadium.get("id"):
            result = dict(guide)
            result["game_date"] = _parse_date(game_date) or game_date
            result["game_time"] = game_time
            result["preferred_transport"] = preferred_transport
            result["return_same_day_requested"] = return_same_day
            return _tool_success("planned", result)

    fallback = data.get("generic_fallback") or {}
    return _tool_success(
        "fallback_planned",
        {
            "origin": origin,
            "stadium_id": stadium.get("id"),
            "stadium_name": stadium.get("name"),
            "game_date": _parse_date(game_date) or game_date,
            "game_time": game_time,
            "recommended_routes": [],
            "return_plan": {
                "same_day_possible": "unknown",
                "note": "정적 동선 데이터에 없는 조합이라 일반 원정 준비 기준으로 안내합니다.",
            },
            "generic_fallback": fallback,
            "data_limitations": (payload.get("metadata") or {}).get("data_limitations"),
        },
    )


def get_langchain_tools() -> list[Any]:
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:
        raise RuntimeError("langchain-core 패키지가 설치되지 않아 LangChain Tool을 구성할 수 없습니다.") from exc

    return [
        StructuredTool.from_function(
            func=find_kbo_game,
            name="find_kbo_game",
            description=(
                "날짜, 팀명, 선택적 구장/상대팀 조건으로 2026 KBO 경기 일정을 찾는다. "
                "좌석 추천, 예매 가이드, 원정 동선 전에 경기 확정이 필요할 때 사용한다."
            ),
        ),
        StructuredTool.from_function(
            func=get_stadium_info,
            name="get_stadium_info",
            description="stadium_id, stadium_name, home_team 중 하나로 구장 위치, 돔 여부, 날씨 grid, 예매처 정보를 조회한다.",
        ),
        StructuredTool.from_function(
            func=get_weather_context,
            name="get_weather_context",
            description="경기 날짜/시간과 구장 돔 여부를 바탕으로 weather_based, weather_risk_based, preference_based 추천 모드를 결정한다.",
        ),
        StructuredTool.from_function(
            func=search_baseball_knowledge,
            name="search_baseball_knowledge",
            description="FAISS RAG 인덱스에서 좌석, 구장, 예매, 동선 근거 문서를 검색한다.",
        ),
        StructuredTool.from_function(
            func=score_seat_candidates,
            name="score_seat_candidates",
            description="RAG 좌석 후보 문서와 날씨/선호/예산을 반영해 좌석 추천 순위를 만든다.",
        ),
        StructuredTool.from_function(
            func=get_ticketing_guide,
            name="get_ticketing_guide",
            description="팀 또는 구장 기준으로 예매처, 공식 링크, 난이도, 티켓팅 팁을 정적 데이터에서 조회한다.",
        ),
        StructuredTool.from_function(
            func=get_logistics_guide,
            name="get_logistics_guide",
            description="출발지, 구장, 경기 날짜/시간 기준으로 원정 동선과 당일 복귀 리스크를 정적 rule로 안내한다.",
        ),
    ]


def get_rag_document_build_result() -> dict[str, Any]:
    try:
        documents = build_rag_documents()
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "status": "source_file_not_found",
            "data": None,
            "error": {
                "code": "RAG_SOURCE_FILE_NOT_FOUND",
                "message": str(exc),
            },
        }

    counts: dict[str, int] = {}
    for document in documents:
        source_type = document.metadata.get("source_type", "unknown")
        counts[source_type] = counts.get(source_type, 0) + 1

    return {
        "ok": True,
        "status": "built",
        "data": {
            "document_count": len(documents),
            "counts_by_source_type": counts,
        },
        "error": None,
    }


def get_game_data(message: str) -> dict:
    """Mock game data provider. Replace with KBO/Naver integration later."""
    if not message.strip():
        return {
            "ok": False,
            "data": None,
            "error": {
                "code": "EMPTY_INPUT",
                "message": "사용자 요청이 비어 있습니다.",
            },
        }

    return {
        "ok": True,
        "data": {
            "game_id": "mock-20260515-lotte-jamsil",
            "teams": {
                "home": {"name": "두산 베어스", "code": "OB"},
                "away": {"name": "롯데 자이언츠", "code": "LT"},
            },
            "stadium": {
                "name": "잠실야구장",
                "is_dome": False,
            },
            "schedule": {
                "date": "2026-05-15",
                "time": "14:00",
            },
            "status": "PRE_GAME",
        },
        "error": None,
    }


def get_stadium_environment(stadium_name: str) -> dict:
    """Mock stadium environment tool. Replace with weather/API/RAG later."""
    if stadium_name != "잠실야구장":
        return {
            "ok": False,
            "data": None,
            "error": {
                "code": "STADIUM_NOT_FOUND",
                "message": "지원하지 않는 구장입니다.",
            },
        }

    return {
        "ok": True,
        "data": {
            "weather": {
                "temp": 31,
                "condition": "sunny",
                "precipitation_probability": 10,
            },
            "recommended_zone": "3루 네이비석 상단",
            "weather_tip": "낮 경기라 햇빛 노출이 커서 선크림과 모자를 챙기는 편이 좋습니다.",
            "fallback_used": False,
        },
        "error": None,
    }
