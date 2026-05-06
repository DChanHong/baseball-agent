from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


KBO_SCHEDULE_URL = "https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList"
DEFAULT_SERIES_ID_LIST = "0,9,6"


STADIUM_META = {
    "잠실": {"name": "잠실야구장", "city": "서울", "is_dome": False},
    "고척": {"name": "고척스카이돔", "city": "서울", "is_dome": True},
    "문학": {"name": "인천 SSG 랜더스필드", "city": "인천", "is_dome": False},
    "수원": {"name": "수원 KT위즈파크", "city": "수원", "is_dome": False},
    "대전": {"name": "대전 한화생명 볼파크", "city": "대전", "is_dome": False},
    "대구": {"name": "대구 삼성라이온즈파크", "city": "대구", "is_dome": False},
    "광주": {"name": "광주 기아챔피언스필드", "city": "광주", "is_dome": False},
    "창원": {"name": "창원 NC파크", "city": "창원", "is_dome": False},
    "사직": {"name": "부산 사직야구장", "city": "부산", "is_dome": False},
}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


class SpanExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_span = False
        self.spans: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "span":
            self._in_span = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "span":
            self._in_span = False

    def handle_data(self, data: str) -> None:
        if self._in_span:
            text = data.strip()
            if text:
                self.spans.append(text)


def strip_html(value: str) -> str:
    parser = TextExtractor()
    parser.feed(unescape(value or ""))
    return parser.text()


def extract_span_texts(value: str) -> list[str]:
    parser = SpanExtractor()
    parser.feed(unescape(value or ""))
    return parser.spans


def extract_game_link(value: str) -> dict[str, str | None]:
    game_date = re.search(r"gameDate=(\d{8})", value or "")
    game_id = re.search(r"gameId=([A-Za-z0-9]+)", value or "")
    return {
        "game_date": game_date.group(1) if game_date else None,
        "game_id": game_id.group(1) if game_id else None,
    }


def parse_date_label(year: int, label: str) -> str:
    match = re.search(r"(\d{2})\.(\d{2})", label)
    if not match:
        raise ValueError(f"Cannot parse KBO date label: {label}")
    month, day = match.groups()
    return f"{year}-{month}-{day}"


def parse_matchup(play_html: str) -> dict[str, Any]:
    spans = extract_span_texts(play_html)
    if len(spans) < 3:
        return {
            "away": None,
            "home": None,
            "away_score": None,
            "home_score": None,
            "raw": strip_html(play_html),
        }

    away = spans[0]
    home = spans[-1]
    away_score = None
    home_score = None

    if len(spans) >= 5 and spans[1].isdigit() and spans[3].isdigit():
        away_score = int(spans[1])
        home_score = int(spans[3])

    return {
        "away": away,
        "home": home,
        "away_score": away_score,
        "home_score": home_score,
        "raw": strip_html(play_html),
    }


def fetch_kbo_schedule(year: int, month: int, team_id: str = "") -> dict[str, Any]:
    payload = urlencode(
        {
            "leId": "1",
            "srIdList": DEFAULT_SERIES_ID_LIST,
            "seasonId": str(year),
            "gameMonth": f"{month:02d}",
            "teamId": team_id,
        }
    ).encode("utf-8")

    request = Request(
        KBO_SCHEDULE_URL,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (compatible; baseball-agent/0.1)",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.koreabaseball.com/Schedule/Schedule.aspx",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(f"KBO schedule request failed: {exc}") from exc

    return json.loads(body)


def normalize_schedule(raw: dict[str, Any], year: int, month: int) -> dict[str, Any]:
    games: list[dict[str, Any]] = []
    current_date: str | None = None

    for item in raw.get("rows", []):
        cells = item.get("row", [])
        if not cells:
            continue

        first_class = cells[0].get("Class")
        offset = 0

        if first_class == "day":
            current_date = parse_date_label(year, strip_html(cells[0].get("Text", "")))
            offset = 1

        if current_date is None or len(cells) < offset + 7:
            continue

        time_html = cells[offset].get("Text", "")
        play_html = cells[offset + 1].get("Text", "")
        relay_html = cells[offset + 2].get("Text", "")
        tv_text = strip_html(cells[offset + 4].get("Text", "")) if len(cells) > offset + 4 else ""
        stadium_short = strip_html(cells[offset + 6].get("Text", "")) if len(cells) > offset + 6 else ""
        note = strip_html(cells[offset + 7].get("Text", "")) if len(cells) > offset + 7 else ""

        matchup = parse_matchup(play_html)
        link = extract_game_link(relay_html)
        stadium = STADIUM_META.get(
            stadium_short,
            {"name": stadium_short, "city": None, "is_dome": None},
        )

        game_status = "SCHEDULED"
        if matchup["away_score"] is not None and matchup["home_score"] is not None:
            game_status = "FINAL"
        if "취소" in note or "취소" in strip_html(play_html):
            game_status = "CANCELLED"

        games.append(
            {
                "game_id": link["game_id"],
                "date": current_date,
                "time": strip_html(time_html),
                "status": game_status,
                "teams": {
                    "away": matchup["away"],
                    "home": matchup["home"],
                    "away_score": matchup["away_score"],
                    "home_score": matchup["home_score"],
                },
                "stadium": {
                    "short_name": stadium_short,
                    **stadium,
                },
                "broadcast": tv_text,
                "note": note,
                "source": {
                    "name": "KBO Official Schedule",
                    "url": KBO_SCHEDULE_URL,
                },
            }
        )

    return {
        "ok": True,
        "data": {
            "season": year,
            "month": f"{month:02d}",
            "game_count": len(games),
            "games": games,
        },
        "error": None,
        "metadata": {
            "source": "kbo_official_ajax",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "fallback_used": False,
        },
    }


def save_json(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl KBO official monthly schedule.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--team-id", default="", help="Optional KBO team id filter.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to data/raw/kbo_schedule_YYYY_MM.json.",
    )
    args = parser.parse_args()

    output = args.output or Path(f"data/raw/kbo_schedule_{args.year}_{args.month:02d}.json")
    raw = fetch_kbo_schedule(args.year, args.month, args.team_id)
    normalized = normalize_schedule(raw, args.year, args.month)
    save_json(normalized, output)

    print(f"saved {normalized['data']['game_count']} games to {output}")


if __name__ == "__main__":
    main()
