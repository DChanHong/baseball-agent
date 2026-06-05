from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[1]
CASE_FILE = ROOT_DIR / "tests" / "security" / "gandalf_attack_cases.json"

sys.path.insert(0, str(ROOT_DIR))

from app.main import app  # noqa: E402
from app.security import analyze_message  # noqa: E402

NORMAL_MESSAGES = [
    "2026년 5월 23일 롯데 경기 좌석 추천해줘",
    "사직 롯데 홈경기 예매 방법 알려줘",
    "서울에서 잠실 야구장 가는 동선 알려줘",
]


def _load_cases() -> list[dict[str, str]]:
    with CASE_FILE.open(encoding="utf-8") as fp:
        cases = json.load(fp)
    if not isinstance(cases, list):
        raise ValueError("Security cases must be a JSON array.")
    return cases


def _check_refusal_cases(cases: list[dict[str, str]]) -> list[str]:
    client = TestClient(app)
    failures: list[str] = []

    for case in cases:
        expected_code = case["expected_refusal_code"]
        analysis = analyze_message(case["message"])["security"]
        if not analysis.get("blocked") or analysis.get("refusal_code") != expected_code:
            failures.append(
                f"{case['id']}: analyze_message expected {expected_code}, got {analysis.get('refusal_code')}"
            )
            continue

        response = client.post(
            "/chat",
            json={"message": case["message"], "session_id": "security-smoke"},
        )
        data = response.json()
        metadata = data.get("metadata", {})
        security = metadata.get("security", {})
        if (
            response.status_code != 200
            or metadata.get("stop_reason") != "security_refusal"
            or security.get("blocked") is not True
            or security.get("refusal_code") != expected_code
        ):
            failures.append(
                f"{case['id']}: /chat expected {expected_code}, got status={response.status_code}, "
                f"stop_reason={metadata.get('stop_reason')}, refusal_code={security.get('refusal_code')}"
            )

    return failures


def _check_normal_messages() -> list[str]:
    failures: list[str] = []
    for message in NORMAL_MESSAGES:
        security = analyze_message(message)["security"]
        if security.get("blocked"):
            failures.append(f"normal message unexpectedly blocked: {message}")
    return failures


def main() -> None:
    cases = _load_cases()
    failures = _check_refusal_cases(cases) + _check_normal_messages()

    print(f"security_refusal_cases={len(cases)}")
    print(f"normal_smoke_cases={len(NORMAL_MESSAGES)}")
    print(f"failures={len(failures)}")

    if failures:
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print("security_smoke=pass")


if __name__ == "__main__":
    main()
