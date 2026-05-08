import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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


# JSON data files are read through this helper so encoding and parsing stay consistent.
def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)
# Convert nested/list values into compact Korean-readable text for RAG document content.
def _as_text(value: Any, default: str = "정보 없음") -> str:
    if value is None:
        return default
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else default
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)
# Format weekday/weekend seat price dictionaries into text used by RAG documents.
def _format_price(price: Any) -> str:
    if not isinstance(price, dict) or not price:
        return "가격 정보 없음"

    weekday = price.get("weekday")
    weekend = price.get("weekend")
    if weekday is None and weekend is None:
        return "가격 정보 없음"
    return f"주중 {weekday if weekday is not None else '정보 없음'}원, 주말 {weekend if weekend is not None else '정보 없음'}원"
# Drop None metadata values before storing them on LangChain Documents.
def _metadata(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}
# Lazily create the OpenAI embedding client only when indexing/searching needs it.
def _get_openai_embeddings():
    try:
        from langchain_openai import OpenAIEmbeddings
    except ImportError as exc:
        raise RuntimeError("langchain-openai 패키지가 설치되지 않았습니다.") from exc

    model = os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_OPENAI_EMBEDDING_MODEL)
    return OpenAIEmbeddings(model=model)
# Lazily import FAISS from langchain-community to keep import errors explicit.
def _get_faiss_class():
    try:
        from langchain_community.vectorstores import FAISS
    except ImportError as exc:
        raise RuntimeError(
            "langchain-community 패키지가 설치되지 않았습니다. requirements.txt에 langchain-community를 추가해야 합니다."
        ) from exc

    return FAISS
# Check whether both FAISS vector and pickle metadata files exist locally.
def _faiss_index_exists(index_dir: Path = FAISS_INDEX_DIR) -> bool:
    return (index_dir / "index.faiss").exists() and (index_dir / "index.pkl").exists()
# Detect OpenAI authentication errors so Tool responses can expose stable error codes.
def _is_openai_auth_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "incorrect api key" in message or "invalid_api_key" in message or "status': 401" in message
# Build the common successful Tool response contract.
def _tool_success(status: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "status": status, "data": data, "error": None}
# Build the common failed Tool response contract.
def _tool_error(status: str, code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status": status,
        "data": None,
        "error": {"code": code, "message": message},
    }
# Resolve the next matching weekday from a base date, optionally shifted by weeks.
def _next_weekday(base_date: date, weekday: int, weeks_ahead: int = 0) -> date:
    days_until = (weekday - base_date.weekday()) % 7
    if days_until == 0:
        days_until = 7
    return base_date + timedelta(days=days_until + (weeks_ahead * 7))
# Parse explicit and relative Korean date expressions into candidate ISO dates.
def _parse_date_candidates(value: str | None) -> list[str]:
    if not value:
        return []

    stripped = value.strip()
    compact = stripped.replace(" ", "")
    today = date.today()

    if "다음주" in compact or "다음주말" in compact:
        next_monday = today + timedelta(days=(7 - today.weekday()))
        next_saturday = _next_weekday(today, 5, weeks_ahead=1)
        next_sunday = next_saturday + timedelta(days=1)
        if "주말" in compact:
            return [next_saturday.isoformat(), next_sunday.isoformat()]
        if "토" in compact:
            return [next_saturday.isoformat()]
        if "일" in compact:
            return [next_sunday.isoformat()]
        return [(next_monday + timedelta(days=offset)).isoformat() for offset in range(7)]

    if "이번주" in compact or "이번주말" in compact or "주말" == compact:
        this_monday = today - timedelta(days=today.weekday())
        this_saturday = _next_weekday(today - timedelta(days=1), 5)
        this_sunday = this_saturday + timedelta(days=1)
        if "주말" in compact:
            return [this_saturday.isoformat(), this_sunday.isoformat()]
        if "토" in compact:
            return [this_saturday.isoformat()]
        if "일" in compact:
            return [this_sunday.isoformat()]
        return [(this_monday + timedelta(days=offset)).isoformat() for offset in range(7)]

    if compact in {"오늘"}:
        return [today.isoformat()]
    if compact in {"내일"}:
        return [(today + timedelta(days=1)).isoformat()]

    iso_match = re.search(r"(20\d{2})[-./년\s]+(\d{1,2})[-./월\s]+(\d{1,2})", stripped)
    if iso_match:
        year, month, day = (int(part) for part in iso_match.groups())
        try:
            return [date(year, month, day).isoformat()]
        except ValueError:
            return []

    compact_match = re.search(r"(20\d{2})(\d{2})(\d{2})", stripped)
    if compact_match:
        year, month, day = (int(part) for part in compact_match.groups())
        try:
            return [date(year, month, day).isoformat()]
        except ValueError:
            return []

    return []
# Return the first parsed ISO date when a single date is required.
def _parse_date(value: str | None) -> str | None:
    candidates = _parse_date_candidates(value)
    return candidates[0] if candidates else None
# Convert an ISO date into a Korean weekday label.
def _weekday_ko(iso_date: str | None) -> str | None:
    if not iso_date:
        return None
    try:
        weekday = date.fromisoformat(iso_date).weekday()
    except ValueError:
        return None
    return ["월", "화", "수", "목", "금", "토", "일"][weekday]
# Load team alias seed data used for deterministic team-name normalization.
def _load_team_aliases() -> list[dict[str, Any]]:
    payload = _read_json(STATIC_DATA_DIR / "team_aliases.json")
    return (payload.get("data") or {}).get("teams") or []
# Normalize user team text to canonical team and schedule names.
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
# Load all crawled 2026 KBO schedule JSON files into one game list.
def _load_all_schedule_games() -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    for path in sorted(RAW_DATA_DIR.glob("kbo_schedule_2026_*.json")):
        payload = _read_json(path)
        for game in (payload.get("data") or {}).get("games") or []:
            copied = dict(game)
            copied["_source_file"] = str(path.relative_to(PROJECT_ROOT))
            games.append(copied)
    return games
# Load stadium metadata used for exact stadium lookup and weather coordinates.
def _load_stadiums() -> list[dict[str, Any]]:
    payload = _read_json(STATIC_DATA_DIR / "stadium_metadata.json")
    return (payload.get("data") or {}).get("stadiums") or []
# Normalize stadium id/name/city/home-team text to one stadium metadata record.
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
# Map the schedule stadium payload back to the project stadium_id.
def _stadium_id_from_schedule(schedule_stadium: dict[str, Any]) -> str | None:
    stadium = _normalize_stadium(stadium_name=schedule_stadium.get("name"))
    if stadium:
        return stadium.get("id")
    stadium = _normalize_stadium(stadium_name=schedule_stadium.get("short_name"))
    if stadium:
        return stadium.get("id")
    return None
# Translate Open-Meteo WMO weather codes into Korean condition text.
def _weather_code_text(code: int | None) -> str:
    mapping = {
        0: "맑음",
        1: "대체로 맑음",
        2: "부분적으로 흐림",
        3: "흐림",
        45: "안개",
        48: "서리 안개",
        51: "약한 이슬비",
        53: "이슬비",
        55: "강한 이슬비",
        61: "약한 비",
        63: "비",
        65: "강한 비",
        71: "약한 눈",
        73: "눈",
        75: "강한 눈",
        80: "약한 소나기",
        81: "소나기",
        82: "강한 소나기",
        95: "뇌우",
    }
    return mapping.get(code, "날씨 코드 정보")


# Call Open-Meteo hourly forecast API and pick the hour closest to game time.
def _fetch_open_meteo_forecast(
    *,
    latitude: float,
    longitude: float,
    target_date: str,
    game_hour: int,
) -> dict[str, Any]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,apparent_temperature,precipitation_probability,precipitation,weather_code",
        "timezone": "Asia/Seoul",
        "start_date": target_date,
        "end_date": target_date,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))

    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        raise RuntimeError("Open-Meteo hourly forecast가 비어 있습니다.")

    target_prefix = f"{target_date}T{game_hour:02d}:"
    selected_index = next((index for index, value in enumerate(times) if value.startswith(target_prefix)), None)
    if selected_index is None:
        selected_index = min(
            range(len(times)),
            key=lambda index: abs(int(times[index][11:13]) - game_hour) if len(times[index]) >= 13 else 99,
        )

    def value_at(key: str) -> Any:
        values = hourly.get(key) or []
        return values[selected_index] if selected_index < len(values) else None

    weather_code = value_at("weather_code")
    return {
        "provider": "open_meteo",
        "source_url": url,
        "forecast_time": times[selected_index],
        "temperature_c": value_at("temperature_2m"),
        "apparent_temperature_c": value_at("apparent_temperature"),
        "precipitation_probability": value_at("precipitation_probability"),
        "precipitation_mm": value_at("precipitation"),
        "weather_code": weather_code,
        "weather_condition": _weather_code_text(weather_code),
    }
# Convert each stadium seat zone into one RAG Document.
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
# Convert each stadium metadata record into one RAG Document.
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
# Convert each ticketing guide record into one RAG Document.
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
# Convert each logistics scenario and generic fallback into RAG Documents.
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
# Build the full local RAG corpus from seat, stadium, ticketing, and logistics data.
def build_rag_documents() -> list[Document]:
    documents: list[Document] = []
    documents.extend(build_stadium_seat_documents())
    documents.extend(build_stadium_metadata_documents())
    documents.extend(build_ticketing_guide_documents())
    documents.extend(build_logistics_guide_documents())
    return documents
# Embed the RAG corpus with OpenAI and save the FAISS index locally.
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
# Load the local FAISS index for similarity search.
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


# Run a raw FAISS similarity search and return document content plus metadata.
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
# Report whether the local FAISS files are ready for search.
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


# Tool: find KBO games from date/team/stadium hints using exact schedule lookup.
def find_kbo_game(
    date: str | None = None,
    team_query: str | None = None,
    stadium_query: str | None = None,
    opponent_query: str | None = None,
) -> dict[str, Any]:
    parsed_dates = _parse_date_candidates(date)
    if not parsed_dates:
        return _tool_error("missing_required_input", "MISSING_DATE", "경기 날짜가 필요합니다.")

    effective_team_query = team_query or opponent_query
    effective_opponent_query = opponent_query if team_query else None
    team = _normalize_team(effective_team_query)
    if not team:
        return _tool_error("missing_required_input", "MISSING_TEAM", "경기 팀 또는 응원 팀이 필요합니다.")

    opponent = _normalize_team(effective_opponent_query)
    stadium = _normalize_stadium(stadium_name=stadium_query) if stadium_query else None
    schedule_name = team.get("schedule_name")
    opponent_schedule_name = opponent.get("schedule_name") if opponent else None

    candidates = []
    for game in _load_all_schedule_games():
        teams = game.get("teams") or {}
        game_teams = {teams.get("home"), teams.get("away")}
        if game.get("date") not in parsed_dates:
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
                        "game_id": game.get("game_id")
                        or f"{game.get('date')}-{(game.get('teams') or {}).get('away')}-{(game.get('teams') or {}).get('home')}-{(game.get('stadium') or {}).get('short_name')}",
                        "date": game.get("date"),
                        "weekday": _weekday_ko(game.get("date")),
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
            "weekday": _weekday_ko(game.get("date")),
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


# Tool: return normalized stadium metadata needed by weather, seat, ticketing, and logistics flows.
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


# Tool: decide weather recommendation mode and fetch real forecast when policy allows.
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
    elif 4 <= days_until <= 10:
        recommendation_mode = "weather_risk_based"
        forecast_level = "medium_term"
        forecast_reliability = "medium"
    else:
        recommendation_mode = "preference_based"
        forecast_level = "unavailable"
        forecast_reliability = "none"
        weather_summary = "11일 이후 경기라 날씨 예보를 사용하지 않고 성향 기반으로 추천합니다."

    forecast = None
    weather_provider_error = None
    if not is_dome and 0 <= days_until <= 10:
        stadium = _normalize_stadium(stadium_id=stadium_id) if stadium_id else None
        coordinates = (stadium or {}).get("coordinates") or {}
        try:
            if coordinates.get("lat") is None or coordinates.get("lng") is None:
                raise RuntimeError("구장 좌표가 없어 실제 날씨 조회를 생략합니다.")
            forecast = _fetch_open_meteo_forecast(
                latitude=float(coordinates["lat"]),
                longitude=float(coordinates["lng"]),
                target_date=parsed_date,
                game_hour=hour,
            )
        except Exception as exc:
            weather_provider_error = str(exc)

    if forecast:
        temp = forecast.get("temperature_c")
        apparent_temp = forecast.get("apparent_temperature_c")
        pop = forecast.get("precipitation_probability") or 0
        precipitation = forecast.get("precipitation_mm") or 0
        condition = forecast.get("weather_condition")

        if pop >= 50 or precipitation >= 1:
            risk_flags.append("rain")
        if apparent_temp is not None and apparent_temp >= 30:
            risk_flags.append("heat")
        if hour < 17 and temp is not None and temp >= 27:
            risk_flags.append("sun")

        weather_summary = (
            f"{forecast['forecast_time']} 기준 {condition}, 기온 {temp}도"
            f"(체감 {apparent_temp}도), 강수확률 {pop}%, 예상 강수량 {precipitation}mm입니다."
        )
    elif not is_dome and forecast_level != "unavailable":
        if hour < 17:
            risk_flags.append("heat")
        weather_summary = (
            "실제 날씨 조회에 실패해 날짜 범위 기반 rule로 처리합니다. "
            "야외 구장은 우천/폭염 가능성을 보수적으로 반영합니다."
        )

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
            "forecast": forecast,
            "weather_provider_error": weather_provider_error,
        },
    )


# Tool: search the indexed baseball knowledge base with optional team/stadium filtering.
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
# Extract a rough minimum KRW price from a RAG seat document.
def _extract_price_from_content(content: str) -> int | None:
    prices = [int(match.replace(",", "")) for match in re.findall(r"(\d[\d,]*)원", content)]
    return min(prices) if prices else None
# Normalize user preference input into comparable tokens.
def _preference_terms(preferences: list[str] | str | None) -> list[str]:
    if preferences is None:
        return []
    if isinstance(preferences, str):
        return [item.strip() for item in re.split(r"[,/ ]+", preferences) if item.strip()]
    return [str(item).strip() for item in preferences if str(item).strip()]


# Tool: score RAG seat candidates using preferences, budget, weather risks, and source limits.
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


# Tool: retrieve ticketing guidance from the FAISS RAG index first.
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
    query_parts = ["예매 가이드", "티켓팅", "공식 예매처"]
    if normalized_team:
        query_parts.extend([normalized_team.get("team"), normalized_team.get("schedule_name")])
    elif team:
        query_parts.append(team)
    if stadium_id:
        query_parts.append(stadium_id)
    if opponent:
        query_parts.append(f"상대팀 {opponent}")
    if game_date:
        query_parts.append(f"경기일 {game_date}")

    result = search_baseball_knowledge(
        query=" ".join(str(part) for part in query_parts if part),
        purpose="ticketing",
        stadium_id=stadium_id,
        team=(normalized_team or {}).get("team") if normalized_team else team,
        top_k=5,
    )
    if result["ok"]:
        documents = [
            document
            for document in result["data"].get("documents", [])
            if (document.get("metadata") or {}).get("source_type") == "ticketing_guide"
        ] or result["data"].get("documents", [])
        return _tool_success(
            "found",
            {
                "team": (normalized_team or {}).get("team") if normalized_team else team,
                "stadium_id": stadium_id,
                "game_date": game_date,
                "opponent": opponent,
                "popularity_hint": popularity_hint,
                "documents": documents,
                "lookup_mode": "rag",
                "data_limitations": "예매 오픈 시각과 잔여석은 실시간 조회하지 않고 인덱싱된 안내 문서를 근거로 답합니다.",
            },
        )

    return _tool_error("not_found", "TICKETING_GUIDE_NOT_FOUND", "RAG 인덱스에서 예매 가이드를 찾지 못했습니다.")


# Tool: retrieve away-trip logistics guidance from the FAISS RAG index first.
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

    query = " ".join(
        str(part)
        for part in [
            "원정 동선",
            origin,
            stadium.get("name"),
            stadium.get("id"),
            game_date,
            game_time,
            preferred_transport,
            "당일 복귀" if return_same_day else None,
        ]
        if part
    )
    result = search_baseball_knowledge(
        query=query,
        purpose="logistics",
        stadium_id=stadium.get("id"),
        top_k=5,
    )
    if result["ok"]:
        documents = [
            document
            for document in result["data"].get("documents", [])
            if (document.get("metadata") or {}).get("source_type") == "logistics_guide"
        ] or result["data"].get("documents", [])
        return _tool_success(
            "planned",
            {
                "origin": origin,
                "stadium_id": stadium.get("id"),
                "stadium_name": stadium.get("name"),
                "game_date": _parse_date(game_date) or game_date,
                "game_time": game_time,
                "preferred_transport": preferred_transport,
                "return_same_day_requested": return_same_day,
                "documents": documents,
                "lookup_mode": "rag",
                "data_limitations": "실시간 열차, 버스, 지하철 막차 API를 조회하지 않고 인덱싱된 동선 rule을 근거로 답합니다.",
            },
        )

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
                "note": "RAG 동선 문서를 찾지 못해 일반 원정 준비 기준으로 안내합니다.",
            },
            "generic_fallback": {
                "recommended_checks": [
                    "경기 종료 예상 시각에서 최소 60분 이상 여유를 두고 막차 확인",
                    "연장전과 우천 지연 가능성을 고려한 숙박 대안 확보",
                    "KTX/SRT/고속버스 마지막 출발 시각과 취소표 가능성 확인",
                ]
            },
            "lookup_mode": "fallback",
            "data_limitations": "실시간 교통 API를 조회하지 않습니다.",
        },
    )
# Register all public Tool functions as LangChain StructuredTools.
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
# Return a lightweight summary of the RAG corpus build without creating an index.
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
    except Exception as exc:
        return {
            "ok": False,
            "status": "source_build_failed",
            "data": None,
            "error": {
                "code": "RAG_DOCUMENT_BUILD_FAILED",
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
