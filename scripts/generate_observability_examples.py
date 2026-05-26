import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.main import ChatRequest, chat
from app.tools import get_faiss_index_status, get_rag_document_build_result


OUTPUT_DIR = PROJECT_ROOT / "docs" / "observability" / "examples"


CASES = [
    {
        "slug": "normal_schedule",
        "title": "Normal schedule lookup",
        "message": "다음주 롯데 경기 알려줘",
        "session_id": "local-observability-normal-schedule",
    },
    {
        "slug": "normal_seat_recommendation",
        "title": "Normal seat recommendation",
        "message": "2026년 5월 23일 롯데 경기 좌석 추천해줘. 가성비 좋고 응원하기 좋은 자리로 알려줘",
        "session_id": "local-observability-normal-seat",
    },
    {
        "slug": "failure_game_not_found",
        "title": "Failure game not found",
        "message": "2026년 2월 1일 롯데 좌석 추천해줘",
        "session_id": "local-observability-failure-game-not-found",
    },
]


def _to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(_to_plain(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _flow_diagram() -> str:
    return """flowchart TD
  A[User /chat request] --> B[FastAPI chat endpoint]
  B --> C[Session context attach]
  C --> D[LangChain AgentExecutor]
  D --> E[find_kbo_game]
  E --> F{Game found?}
  F -- ambiguous schedule --> G[Final answer: candidate games]
  F -- found --> H[get_stadium_info]
  H --> I[get_weather_context]
  I --> J[search_baseball_knowledge]
  J --> K[score_seat_candidates]
  K --> L[Final answer: seat recommendation]
  F -- not found --> M[Fallback answer]
  G --> N[Response metadata: trace_id, stop_reason, elapsed_ms, observations]
  L --> N
  M --> N
"""


def _summary(runs: list[dict[str, Any]], index_status: dict[str, Any]) -> str:
    index_data = index_status.get("data") or {}
    corpus_data = index_data.get("corpus") or {}
    lines = [
        "# Observability Example Runs",
        "",
        f"- generated_at: `{datetime.now(timezone.utc).isoformat()}`",
        f"- FAISS index status: `{index_status.get('status')}`",
        f"- FAISS document count: `{corpus_data.get('document_count')}`",
        f"- counts by source type: `{corpus_data.get('counts_by_source_type')}`",
        f"- embedding model: `{index_data.get('embedding_model')}`",
        "",
        "## Files",
        "",
        "| Case | Run JSON | Tool Calls JSON | Trace ID | Tools | Elapsed | Stop Reason |",
        "|------|----------|-----------------|----------|-------|---------|-------------|",
    ]

    for run in runs:
        metadata = run["response"]["metadata"]
        slug = run["slug"]
        tools = " -> ".join(metadata.get("tools_used") or [])
        lines.append(
            "| "
            + " | ".join(
                [
                    run["title"],
                    f"`{slug}_run.json`",
                    f"`{slug}_tool_calls.json`",
                    f"`{metadata.get('trace_id')}`",
                    f"`{tools}`",
                    f"`{metadata.get('elapsed_ms')}ms`",
                    f"`{metadata.get('stop_reason')}`",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- These files are sanitized examples generated from real local `/chat` executions.",
            "- API keys and local `.env` values are not written to the examples.",
            "- Runtime `logs/` stays ignored; reviewable submission samples live in this docs directory.",
            "- `flow.mmd` contains the high-level observability flow diagram.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    index_status = get_faiss_index_status()
    corpus_status = get_rag_document_build_result()
    if index_status.get("data") is not None:
        index_status["data"]["corpus"] = (corpus_status.get("data") or {}) if corpus_status.get("ok") else None
    _write_json(OUTPUT_DIR / "index_status.json", index_status)

    runs: list[dict[str, Any]] = []
    for case in CASES:
        response = chat(ChatRequest(message=case["message"], session_id=case["session_id"]))
        payload = {
            "case": case["title"],
            "input": {
                "message": case["message"],
                "session_id": case["session_id"],
            },
            "response": _to_plain(response),
        }
        tool_calls = {
            "case": case["title"],
            "input": payload["input"],
            "trace_id": payload["response"]["metadata"].get("trace_id"),
            "session_id": payload["response"]["metadata"].get("session_id"),
            "tools_used": payload["response"]["metadata"].get("tools_used"),
            "observations": payload["response"]["metadata"].get("observations"),
        }

        _write_json(OUTPUT_DIR / f"{case['slug']}_run.json", payload)
        _write_json(OUTPUT_DIR / f"{case['slug']}_tool_calls.json", tool_calls)
        runs.append({**case, "response": payload["response"]})

    (OUTPUT_DIR / "flow.mmd").write_text(_flow_diagram(), encoding="utf-8")
    (OUTPUT_DIR / "summary.md").write_text(_summary(runs, index_status), encoding="utf-8")


if __name__ == "__main__":
    main()
