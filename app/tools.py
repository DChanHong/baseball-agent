import json
import os
from dataclasses import dataclass
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
