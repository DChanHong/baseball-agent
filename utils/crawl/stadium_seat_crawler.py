from __future__ import annotations

import argparse
import json
import re
import ssl
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


SAJIK_LOTTE_GIANTS_TICKET_URL = "https://www.giantsclub.com/html/?pcode=339"
JAMSIL_LG_TWINS_TICKET_URL = "https://www.lgtwins.com/ticket/general"
JAMSIL_DOOSAN_BEARS_STADIUM_URL = "https://www.doosanbears.com/bears/stadium?tabId=seoul"
GOCHEOK_KIWOOM_HEROES_TICKET_URL = "https://heroesbaseball.co.kr/ticket/normal/viewCharge.do"
INCHEON_SSG_LANDERS_TICKET_URL = "https://www.ssglanders.com/game/ticket"
SUWON_KT_WIZ_TICKET_URL = "https://www.ktwiz.co.kr/ticket/price"
GWANGJU_KIA_TIGERS_TICKET_URL = "https://tigers.co.kr/ticket/reservation"
DAEGU_SAMSUNG_LIONS_TICKET_URL = "https://www.samsunglions.com/score/score_4_2_1.asp"
DAEJEON_HANWHA_EAGLES_TICKET_URL = "https://www.ticketlink.co.kr/sports/137/63"
CHANGWON_NC_DINOS_STADIUM_URL = "https://www.ncdinos.com/dinos/stadium.do"


STADIUM_SEAT_SOURCES: dict[str, dict[str, Any]] = {
    "jamsil_lg_twins": {
        "stadium_id": "jamsil",
        "stadium_name": "잠실야구장",
        "team": "LG 트윈스",
        "source_name": "LG Twins Official Ticket Guide",
        "url": JAMSIL_LG_TWINS_TICKET_URL,
        "output_filename": "jamsil_lg_twins_seats.json",
    },
    "jamsil_doosan_bears": {
        "stadium_id": "jamsil",
        "stadium_name": "잠실야구장",
        "team": "두산 베어스",
        "source_name": "Doosan Bears Official Stadium Guide",
        "url": JAMSIL_DOOSAN_BEARS_STADIUM_URL,
        "output_filename": "jamsil_doosan_bears_seats.json",
    },
    "gocheok_kiwoom_heroes": {
        "stadium_id": "gocheok",
        "stadium_name": "고척스카이돔",
        "team": "키움 히어로즈",
        "source_name": "Kiwoom Heroes Official Ticket Guide",
        "url": GOCHEOK_KIWOOM_HEROES_TICKET_URL,
        "output_filename": "gocheok_kiwoom_heroes_seats.json",
    },
    "incheon_ssg_landers": {
        "stadium_id": "incheon",
        "stadium_name": "인천 SSG 랜더스필드",
        "team": "SSG 랜더스",
        "source_name": "SSG Landers Official Ticket Guide",
        "url": INCHEON_SSG_LANDERS_TICKET_URL,
        "output_filename": "incheon_ssg_landers_seats.json",
    },
    "suwon_kt_wiz": {
        "stadium_id": "suwon",
        "stadium_name": "수원 KT위즈파크",
        "team": "KT 위즈",
        "source_name": "KT Wiz Official Ticket Guide",
        "url": SUWON_KT_WIZ_TICKET_URL,
        "output_filename": "suwon_kt_wiz_seats.json",
    },
    "daejeon_hanwha_eagles": {
        "stadium_id": "daejeon",
        "stadium_name": "대전 한화생명 볼파크",
        "team": "한화 이글스",
        "source_name": "Hanwha Eagles Official Ticketlink Guide",
        "url": DAEJEON_HANWHA_EAGLES_TICKET_URL,
        "output_filename": "daejeon_hanwha_eagles_seats.json",
    },
    "daegu_samsung_lions": {
        "stadium_id": "daegu",
        "stadium_name": "대구 삼성라이온즈파크",
        "team": "삼성 라이온즈",
        "source_name": "Samsung Lions Official Ticket Guide",
        "url": DAEGU_SAMSUNG_LIONS_TICKET_URL,
        "output_filename": "daegu_samsung_lions_seats.json",
    },
    "gwangju_kia_tigers": {
        "stadium_id": "gwangju",
        "stadium_name": "광주-기아 챔피언스 필드",
        "team": "KIA 타이거즈",
        "source_name": "KIA Tigers Official Ticket Guide",
        "url": GWANGJU_KIA_TIGERS_TICKET_URL,
        "output_filename": "gwangju_kia_tigers_seats.json",
    },
    "changwon_nc_dinos": {
        "stadium_id": "changwon",
        "stadium_name": "창원NC파크",
        "team": "NC 다이노스",
        "source_name": "NC Dinos Official Stadium Guide",
        "url": CHANGWON_NC_DINOS_STADIUM_URL,
        "output_filename": "changwon_nc_dinos_seats.json",
    },
    "sajik_lotte_giants": {
        "stadium_id": "sajik",
        "stadium_name": "부산 사직야구장",
        "team": "롯데 자이언츠",
        "source_name": "Lotte Giants Official Ticket Guide",
        "url": SAJIK_LOTTE_GIANTS_TICKET_URL,
        "output_filename": "sajik_lotte_giants_seats.json",
    },
}


PRICE_LABELS = ["ivory_plus", "ivory", "weekday", "weekend", "blue", "navy"]
PRICE_HEADER_LABELS = {
    "아이보리+": "ivory_plus",
    "아이보리": "ivory",
    "주중": "weekday",
    "주말": "weekend",
    "블루": "blue",
    "네이비": "navy",
    "레드": "red",
}


class GiantsTicketParser(HTMLParser):
    """Extract headings and tables from the Giants ticket guide page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.items: list[dict[str, Any]] = []
        self._tag_stack: list[str] = []
        self._capture_heading: str | None = None
        self._heading_parts: list[str] = []
        self._current_table: dict[str, Any] | None = None
        self._current_row: list[dict[str, Any]] | None = None
        self._current_cell: dict[str, Any] | None = None
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._tag_stack.append(tag)
        attr_map = {name: value for name, value in attrs}

        if tag in {"h3", "h4", "h5"}:
            self._capture_heading = tag
            self._heading_parts = []
            return

        if tag == "table":
            self._current_table = {"rows": [], "summary": attr_map.get("summary")}
            return

        if tag == "tr" and self._current_table is not None:
            self._current_row = []
            return

        if tag in {"th", "td"} and self._current_row is not None:
            self._current_cell = {
                "tag": tag,
                "rowspan": int(attr_map.get("rowspan") or "1"),
                "colspan": int(attr_map.get("colspan") or "1"),
            }
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h3", "h4", "h5"} and self._capture_heading == tag:
            text = clean_text(" ".join(self._heading_parts))
            if text:
                self.items.append({"type": "heading", "level": tag, "text": text})
            self._capture_heading = None
            self._heading_parts = []

        if tag in {"th", "td"} and self._current_cell is not None:
            self._current_cell["text"] = clean_text(" ".join(self._cell_parts))
            self._current_row.append(self._current_cell)
            self._current_cell = None
            self._cell_parts = []

        if tag == "tr" and self._current_table is not None and self._current_row is not None:
            if self._current_row:
                self._current_table["rows"].append(self._current_row)
            self._current_row = None

        if tag == "table" and self._current_table is not None:
            self.items.append({"type": "table", **self._current_table})
            self._current_table = None

        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        text = unescape(data)
        if self._capture_heading:
            self._heading_parts.append(text)
        if self._current_cell is not None:
            self._cell_parts.append(text)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def fetch_html(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) baseball-agent/0.1"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        },
    )

    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read()
    except URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            context = ssl._create_unverified_context()
            with urlopen(request, timeout=15, context=context) as response:
                raw = response.read()
        else:
            raise RuntimeError(f"Seat guide request failed: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Seat guide request failed: {exc}") from exc

    return raw.decode("utf-8", errors="replace")


def expand_table(rows: list[list[dict[str, Any]]]) -> list[list[str]]:
    grid: list[list[str]] = []
    spans: dict[tuple[int, int], str] = {}

    for row_idx, row in enumerate(rows):
        grid_row: list[str] = []
        col_idx = 0

        for cell in row:
            while (row_idx, col_idx) in spans:
                grid_row.append(spans[(row_idx, col_idx)])
                col_idx += 1

            text = clean_text(cell.get("text", ""))
            rowspan = int(cell.get("rowspan") or 1)
            colspan = int(cell.get("colspan") or 1)

            for offset in range(colspan):
                grid_row.append(text)
                if rowspan > 1:
                    for next_row in range(row_idx + 1, row_idx + rowspan):
                        spans[(next_row, col_idx + offset)] = text
            col_idx += colspan

        while (row_idx, col_idx) in spans:
            grid_row.append(spans[(row_idx, col_idx)])
            col_idx += 1

        if any(grid_row):
            grid.append(grid_row)

    return grid


def extract_tables(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    current_heading: str | None = None

    for item in items:
        if item["type"] == "heading":
            current_heading = item["text"]
            continue

        if item["type"] == "table":
            expanded_rows = expand_table(item["rows"])
            tables.append(
                {
                    "heading": current_heading,
                    "summary": item.get("summary"),
                    "rows": expanded_rows,
                }
            )

    return tables


def is_price_table(table: dict[str, Any]) -> bool:
    joined = " ".join(" ".join(row) for row in table["rows"][:5])
    return "아이보리" in joined and "주중" in joined and "주말" in joined


def normalize_seat_name(value: str) -> str:
    value = clean_text(value)
    value = value.replace("(그라운드석)", "그라운드석")
    return value


def parse_price(value: str) -> int | None:
    if clean_text(value) == "무료":
        return 0
    digits = re.sub(r"[^\d]", "", value or "")
    return int(digits) if digits else None


def infer_seat_tags(seat_name: str) -> dict[str, Any]:
    tags: list[str] = []
    recommendation_use_cases: list[str] = []
    side: str | None = None

    if "1루" in seat_name:
        side = "home"
        tags.append("home_side")
    if "3루" in seat_name:
        side = "away"
        tags.append("away_side")
    if "중앙" in seat_name:
        tags.append("central_view")
        recommendation_use_cases.append("view")
    if "응원" in seat_name:
        tags.append("cheering")
        recommendation_use_cases.append("cheering")
    if "탁자" in seat_name or "테이블" in seat_name or "table" in seat_name.lower():
        tags.append("table")
        recommendation_use_cases.append("comfort")
    if "외야" in seat_name:
        tags.append("outfield")
        recommendation_use_cases.append("budget")
    if "그린" in seat_name:
        tags.append("outfield")
        recommendation_use_cases.append("budget")
    if "네이비" in seat_name or "4층" in seat_name:
        tags.append("upper_deck")
        recommendation_use_cases.extend(["budget", "view"])
    if "상단" in seat_name:
        tags.append("upper_deck")
        recommendation_use_cases.extend(["budget", "view"])
    if "시야방해" in seat_name:
        tags.append("obstructed_view")
    if "그라운드" in seat_name or "필드" in seat_name or "프리미엄" in seat_name:
        tags.append("close_to_field")
        recommendation_use_cases.append("immersion")
    if "단체" in seat_name or "글램핑" in seat_name:
        tags.append("group")
        recommendation_use_cases.append("group")

    return {
        "side": side,
        "tags": sorted(set(tags)),
        "recommendation_use_cases": sorted(set(recommendation_use_cases)),
    }


def normalize_price_table(table: dict[str, Any]) -> list[dict[str, Any]]:
    seat_zones: list[dict[str, Any]] = []

    for row in table["rows"]:
        if len(row) < 8:
            continue
        if row[0] in {"구분", "일반", "청소년", "초등생"}:
            continue

        category = row[0]
        seat_name = normalize_seat_name(row[1])
        audience = row[2] if category == "일반석" else "all"

        if not seat_name or seat_name in PRICE_HEADER_LABELS:
            continue

        if category == "일반석":
            price_values = row[3:9]
            note_values = row[9:]
        else:
            price_values = row[2:8]
            note_values = row[8:]

        prices = {}
        for label, value in zip(PRICE_LABELS, price_values, strict=False):
            price = parse_price(value)
            if price is not None:
                prices[label] = price

        note_values = [value for value in note_values if value and not parse_price(value)]
        inferred = infer_seat_tags(seat_name)
        seat_zones.append(
            {
                "seat_name": seat_name,
                "category": category,
                "audience": audience,
                "side": inferred["side"],
                "price_krw": prices,
                "tags": inferred["tags"],
                "recommendation_use_cases": inferred["recommendation_use_cases"],
                "notes": note_values,
            }
        )

    return seat_zones


def dedupe_seat_zones(seat_zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}

    for zone in seat_zones:
        key = (zone["seat_name"], zone["audience"])
        if key not in deduped:
            deduped[key] = zone
            continue

        existing = deduped[key]
        existing["notes"] = sorted(set(existing["notes"] + zone["notes"]))
        existing["tags"] = sorted(set(existing["tags"] + zone["tags"]))
        existing["recommendation_use_cases"] = sorted(
            set(existing["recommendation_use_cases"] + zone["recommendation_use_cases"])
        )

    return list(deduped.values())


def normalize_sajik_lotte_giants(html: str, source: dict[str, Any]) -> dict[str, Any]:
    parser = GiantsTicketParser()
    parser.feed(html)
    tables = extract_tables(parser.items)
    price_tables = [table for table in tables if is_price_table(table)]

    seat_zones: list[dict[str, Any]] = []
    for table in price_tables:
        seat_zones.extend(normalize_price_table(table))

    return build_success_payload(source, dedupe_seat_zones(seat_zones), price_tables)


def normalize_lg_twins(html: str, source: dict[str, Any]) -> dict[str, Any]:
    parser = GiantsTicketParser()
    parser.feed(html)
    tables = extract_tables(parser.items)
    price_tables = [table for table in tables if table.get("heading") == "티켓 안내"]

    seat_zones: list[dict[str, Any]] = []
    for table in price_tables:
        for row in table["rows"]:
            if len(row) < 4 or row[0] in {"좌석등급", "등급"}:
                continue

            seat_name = normalize_seat_name(row[0])
            audience = clean_text(row[1])
            weekday_price = parse_price(row[2])
            weekend_price = parse_price(row[3])

            if weekday_price is None and weekend_price is None:
                continue

            inferred = infer_seat_tags(seat_name)
            seat_zones.append(
                {
                    "seat_name": seat_name,
                    "category": "일반석",
                    "audience": audience,
                    "side": inferred["side"],
                    "price_krw": {
                        "weekday": weekday_price,
                        "weekend": weekend_price,
                    },
                    "tags": inferred["tags"],
                    "recommendation_use_cases": inferred["recommendation_use_cases"],
                    "notes": [],
                }
            )

    deduped = dedupe_seat_zones(seat_zones)
    return build_success_payload(source, deduped, price_tables)


def normalize_kiwoom_heroes(html: str, source: dict[str, Any]) -> dict[str, Any]:
    parser = GiantsTicketParser()
    parser.feed(html)
    tables = extract_tables(parser.items)
    price_tables = [
        table
        for table in tables
        if table.get("heading") == "2026 시즌 입장 요금 안내" and len(table["rows"]) > 5
    ]

    seat_zones: list[dict[str, Any]] = []
    for table in price_tables[:1]:
        for row in table["rows"]:
            if len(row) < 7 or row[0] == "좌석권종":
                continue

            category = clean_text(row[0])
            seat_name = normalize_seat_name(row[1])
            audience = clean_text(row[2])
            weekday_price = parse_price(row[3])
            weekend_price = parse_price(row[4])
            summer_weekday_price = parse_price(row[5])
            summer_weekend_price = parse_price(row[6])

            if weekday_price is None and weekend_price is None:
                continue

            inferred = infer_seat_tags(seat_name)
            seat_zones.append(
                {
                    "seat_name": seat_name,
                    "category": category,
                    "audience": audience,
                    "side": inferred["side"],
                    "price_krw": {
                        "weekday": weekday_price,
                        "weekend": weekend_price,
                        "summer_weekday": summer_weekday_price,
                        "summer_weekend": summer_weekend_price,
                    },
                    "tags": inferred["tags"],
                    "recommendation_use_cases": inferred["recommendation_use_cases"],
                    "notes": [clean_text(row[7])] if len(row) > 7 and clean_text(row[7]) else [],
                }
            )

    deduped = dedupe_seat_zones(seat_zones)
    return build_success_payload(source, deduped, price_tables[:1])


def extract_script_url(html: str, pattern: str, base_url: str) -> str:
    match = re.search(pattern, html)
    if not match:
        raise RuntimeError("Could not find official ticket data script URL.")

    script_path = match.group(1)
    if script_path.startswith("http"):
        return script_path

    return base_url.rstrip("/") + "/" + script_path.lstrip("/")


def parse_js_object_fields(js_object: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, quoted_value in re.findall(r'([A-Za-z][A-Za-z0-9_]*):"((?:\\.|[^"\\])*)"', js_object):
        try:
            fields[key] = json.loads(f'"{quoted_value}"')
        except json.JSONDecodeError:
            fields[key] = quoted_value.replace(r"\'", "'")
    for key, numeric_value in re.findall(r"([A-Za-z][A-Za-z0-9_]*):(\d+)", js_object):
        fields.setdefault(key, numeric_value)
    return fields


def build_kia_seat_zone(fields: dict[str, str], audience_key: str, price_prefix: str) -> dict[str, Any] | None:
    seat_name = normalize_seat_name(fields.get("area") or fields.get("id") or "")
    audience = clean_text(fields.get(audience_key, ""))
    weekday_price = parse_price(fields.get(f"{price_prefix}WeeklyPrice", ""))
    weekend_price = parse_price(fields.get(f"{price_prefix}WeekendPrice", ""))

    if not seat_name or not audience or (weekday_price is None and weekend_price is None):
        return None

    notes = []
    section_id = fields.get("id")
    gate = fields.get("gate")
    if section_id and section_id != seat_name:
        notes.append(f"section_id={section_id}")
    if gate:
        notes.append(f"gate={gate}")

    inferred = infer_seat_tags(seat_name)
    return {
        "seat_name": seat_name,
        "category": "일반석",
        "audience": audience,
        "side": inferred["side"],
        "price_krw": {
            "weekday": weekday_price,
            "weekend": weekend_price,
        },
        "tags": inferred["tags"],
        "recommendation_use_cases": inferred["recommendation_use_cases"],
        "notes": notes,
    }


def normalize_kia_tigers(html: str, source: dict[str, Any]) -> dict[str, Any]:
    script_url = extract_script_url(
        html,
        r'<script src="([^"]*/static/js/main\.[^"]+\.chunk\.js)"',
        "https://tigers.co.kr",
    )
    script = fetch_html(script_url)

    seat_zones: list[dict[str, Any]] = []
    official_rows = [["좌석", "대상", "주중", "주말", "비고"]]
    for match in re.finditer(r"\{key:.*?(?=\},\{key:|\],om=function)", script):
        fields = parse_js_object_fields(match.group(0))
        for audience_key, price_prefix in [
            ("adult", "adult"),
            ("studentArmy", "studentArmy"),
            ("kid", "kid"),
            ("homan", "HonamBaseballTeam"),
            ("kidMemership", "kidMem"),
        ]:
            zone = build_kia_seat_zone(fields, audience_key, price_prefix)
            if zone is None:
                continue
            seat_zones.append(zone)
            official_rows.append(
                [
                    zone["seat_name"],
                    zone["audience"],
                    str(zone["price_krw"].get("weekday") if zone["price_krw"].get("weekday") is not None else ""),
                    str(zone["price_krw"].get("weekend") if zone["price_krw"].get("weekend") is not None else ""),
                    " / ".join(zone["notes"]),
                ]
            )

    official_tables = [
        {
            "heading": "광주-기아 챔피언스 필드 좌석/입장요금",
            "summary": "KIA 타이거즈 공식 웹사이트 좌석안내도에 포함된 좌석별 요금 데이터",
            "rows": official_rows,
        }
    ]
    return build_success_payload(source, dedupe_seat_zones(seat_zones), official_tables)


KT_WIZ_PRICE_RESOURCE_API_URL = (
    "https://www.ktwiz.co.kr/api/v2/resource?id=TICKET_PRICE_IMAGE_PC"
)

KT_WIZ_PRICE_ROWS = [
    ("중앙 테이블", "비씨카드존", 60000, 70000),
    ("중앙 테이블", "네이버클립존", 60000, 70000),
    ("중앙 테이블", "KT존", 50000, 60000),
    ("내야(1,3루)", "하이파이브존(1루), 익사이팅석(3루)", 27000, 32000),
    ("내야(1,3루)", "응원지정석", 20000, 24000),
    ("내야(1,3루)", "휠체어석(장애인)", 10000, 12000),
    ("내야(1,3루)", "스카이존(5F)", 12000, 14000),
    ("외야(1,3루)", "티빙테이블석", 30000, 35000),
    ("외야(1,3루)", "위즈 캠핑존", 200000, 240000),
    ("외야(1,3루)", "외야 잔디 자유석", 12000, 14000),
]


SSG_LANDERS_PRICE_ROWS = [
    ("4층 SKY뷰석", "일반", 13000, 15000),
    ("4층 SKY뷰석", "청소년", 9000, 10500),
    ("4층 SKY뷰석", "어린이,경로,중증장애인,국가유공자,군인", 6500, 7500),
    ("외야 필드석", "일반", 15000, 18000),
    ("외야 필드석", "청소년", 10500, 12500),
    ("외야 필드석", "어린이,경로,중증장애인,국가유공자,군인", 7500, 9000),
    ("내야 필드석", "일반", 16000, 19000),
    ("내야 필드석", "청소년", 11000, 13000),
    ("내야 필드석", "어린이,경로,중증장애인,국가유공자,군인", 8000, 9500),
    ("몰리스 그린존", "일반", 20000, 28000),
    ("몰리스 그린존", "청소년", 14000, 19500),
    ("몰리스 그린존", "어린이", 10000, 14000),
    ("최정 400홈런 기념존", "all", 400, 400),
    ("휠체어 장애인석", "all", 5000, 5000),
    ("으쓱이존", "all", 19000, 22000),
    ("원정응원석", "all", 19000, 22000),
    ("덕아웃 상단석", "all", 21000, 25000),
    ("초가정자", "all", 23000, 31000),
    ("로케트배터리 외야파티덱", "all", 25000, 31000),
    ("SKY탁자석", "all", 26000, 36000),
    ("외야패밀리존", "all", 27000, 37000),
    ("홈런커플존", "all", 32000, 41000),
    ("이마트 프렌들리존", "all", 34000, 41000),
    ("이마트 바비큐존/도드람한돈 바비큐존", "all", 37000, 48000),
    ("요기요 내야패밀리존", "all", 40000, 53000),
    ("노브랜드 테이블석(2층)", "all", 47000, 55000),
    ("피코크 테이블석(1층)", "all", 53000, 64000),
    ("랜더스 라이브존", "all", 60000, 75000),
    ("미니스카이박스", "all", 67000, 86000),
    ("스카이박스", "all", 83000, 97000),
]


SAMSUNG_LIONS_PRICE_ROWS = [
    ("VIP석", "all", 50000, 60000, 65000),
    ("으뜸병원 중앙테이블석", "all", 45000, 55000, 60000),
    ("1,3루 테이블석", "all", 40000, 50000, 55000),
    ("1,3루 익사이팅석", "all", 22000, 27000, 30000),
    ("블루존", "all", 19000, 22000, 25000),
    ("3루 내야지정석", "all", 15000, 17000, 19000),
    ("원정응원석", "all", 19000, 22000, 25000),
    ("1루 내야지정석", "all", 10000, 13000, 14000),
    ("SKY 블루존", "일반", 10000, 12000, 15000),
    ("SKY 블루존", "어린이,청소년,경로,장애인 등", 7000, 9000, 12000),
    ("SKY 하단 지정석", "일반", 10000, 11000, 13000),
    ("SKY 하단 지정석", "어린이,청소년,경로,장애인 등", 7000, 8000, 10000),
    ("1,3루 SKY 상단 지정석", "일반", 8000, 9000, 11000),
    ("1,3루 SKY 상단 지정석", "어린이,청소년,경로,장애인 등", 5000, 6000, 8000),
    ("중앙 SKY 상단 지정석", "일반", 9000, 10000, 12000),
    ("중앙 SKY 상단 지정석", "어린이,청소년,경로,장애인 등", 6000, 7000, 9000),
    ("외야지정석", "일반", 9000, 10000, 11000),
    ("외야지정석", "어린이,청소년,경로,장애인 등", 6000, 7000, 8000),
    ("외야패밀리석", "all", 18000, 20000, 23000),
    ("외야테이블석 4인", "all", 72000, 80000, 92000),
    ("외야테이블석 8인", "all", 144000, 160000, 184000),
    ("외야카풀테이블석 2인", "all", 30000, 36000, 40000),
    ("루프탑테이블석", "all", 20000, 23000, 25000),
    ("파티플로어 라이브석", "all", 65000, 70000, 75000),
    ("잔디그린존", "all", 10000, 11000, 13000),
    ("캠핑존 6인", "all", 180000, 240000, 270000),
    ("장애인(휠체어)석", "all", 5000, 5000, 5000),
]


HANWHA_EAGLES_TICKETLINK_TAB_DETAIL_URL = (
    "https://mapi.ticketlink.co.kr/mapi/sports/team/getTabInfoDetail"
    "?typeCode=SEAT&teamId=63&channelTypeCode=WEB&languageCode=KO"
)

HANWHA_EAGLES_PRICE_ROWS = [
    ("중앙", "포수후면석", "all", 52500, 58000, 71000, 81500, 86500, ""),
    ("중앙", "중앙지정석", "all", 44500, 44500, 48000, 54500, 58000, ""),
    ("중앙", "중앙탁자석", "all", 52000, 52000, 56500, 64500, 68000, ""),
    ("중앙", "중앙휠체어석", "all", 22500, 22500, 24000, 27500, 29000, ""),
    ("내야", "내야지정석 A", "all", 18000, 18000, 21500, 25500, 28500, ""),
    ("내야", "응원단석", "all", 20000, 20000, 25000, 29000, 32000, ""),
    ("내야", "내야지정석 B", "all", 15500, 17500, 19000, 21500, 24000, ""),
    ("내야", "내야박스석", "all", 34000, 34000, 40500, 46000, 49000, "6인"),
    ("내야", "내야탁자석(1층)", "all", 38500, 38500, 46500, 52500, 56000, ""),
    ("내야", "내야탁자석(4층)", "all", 27000, 27000, 35500, 40000, 44000, ""),
    ("내야", "내야휠체어석", "all", 9000, 9000, 11000, 13000, 14500, ""),
    ("내야", "이닝스 VIP 라운지", "all", 152000, 152000, 156500, 164500, 168000, ""),
    ("내야", "이닝스 VIP 테라스", "all", 116000, 116000, 122000, 127500, 130000, ""),
    ("내야", "스플래쉬 자쿠지", "all", 65500, 67500, 69000, 71500, 74000, ""),
    ("내야", "스플래쉬 일반", "all", 45500, 47500, 49000, 51500, 54000, ""),
    ("내야", "스플래쉬 탁자", "all", 57000, 57000, 65500, 70000, 74000, ""),
    ("외야", "외야지정석", "all", 12000, 13000, 14500, 16000, 18000, ""),
    ("외야", "잔디석", "all", 23000, 23000, 27000, 31000, 34000, "3인, 4인"),
    ("외야", "외야커플석", "all", 34000, 34000, 40500, 46000, 49000, "2인, 6인"),
    ("외야", "외야탁자석", "all", 29000, 29000, 36500, 41000, 45000, ""),
    ("외야", "외야휠체어석", "all", 6000, 6500, 7500, 8000, 9000, ""),
    ("외야", "스카이박스", "all", 100000, 100000, 110000, 116500, 122000, "12인, 15인"),
]


def normalize_ssg_landers(html: str, source: dict[str, Any]) -> dict[str, Any]:
    match = re.search(r'<img src="([^"]*price_2026\.png)"[^>]*입장권 가격표', html)
    image_url = "https://www.ssglanders.com/img/game/price_2026.png"
    if match:
        image_path = match.group(1)
        image_url = (
            image_path
            if image_path.startswith("http")
            else "https://www.ssglanders.com" + image_path
        )

    seat_zones: list[dict[str, Any]] = []
    official_rows = [["좌석", "대상", "주중(월-목)", "주말(금-일 및 공휴일)"]]
    for seat_name, audience, weekday_price, weekend_price in SSG_LANDERS_PRICE_ROWS:
        inferred = infer_seat_tags(seat_name)
        seat_zones.append(
            {
                "seat_name": seat_name,
                "category": "일반석",
                "audience": audience,
                "side": inferred["side"],
                "price_krw": {
                    "weekday": weekday_price,
                    "weekend": weekend_price,
                },
                "tags": inferred["tags"],
                "recommendation_use_cases": inferred["recommendation_use_cases"],
                "notes": ["공식 이미지 가격표 수동 정규화"],
            }
        )
        official_rows.append([seat_name, audience, str(weekday_price), str(weekend_price)])

    official_tables = [
        {
            "heading": "SSG 랜더스 티켓 가격 안내",
            "summary": f"SSG Landers official ticket price image: {image_url}",
            "rows": official_rows,
        }
    ]
    return build_success_payload(source, seat_zones, official_tables)


def normalize_hanwha_eagles(html: str, source: dict[str, Any]) -> dict[str, Any]:
    tab_payload = json.loads(fetch_html(HANWHA_EAGLES_TICKETLINK_TAB_DETAIL_URL))
    tab_html = tab_payload.get("data") or ""
    match = re.search(r'<img src=\\"([^\\"]*260506\.png)\\"', json.dumps(tab_html))
    image_url = "https://image.toast.com/aaaaab/ticketlink/TKL_1/260506.png"
    if match:
        image_url = match.group(1)
    elif "260506.png" not in tab_html:
        raise RuntimeError("Hanwha Eagles official 2026 ticket guide image was not found.")

    seat_zones: list[dict[str, Any]] = []
    official_rows = [["구분", "좌석", "대상", "1구간", "2구간", "3구간", "4구간", "스페셜", "비고"]]
    for (
        category,
        seat_name,
        audience,
        section_1_price,
        section_2_price,
        section_3_price,
        section_4_price,
        special_price,
        note,
    ) in HANWHA_EAGLES_PRICE_ROWS:
        inferred = infer_seat_tags(seat_name)
        notes = ["공식 이미지 가격표 수동 정규화"]
        if note:
            notes.append(note)
        seat_zones.append(
            {
                "seat_name": seat_name,
                "category": category,
                "audience": audience,
                "side": inferred["side"],
                "price_krw": {
                    "section_1": section_1_price,
                    "section_2": section_2_price,
                    "section_3": section_3_price,
                    "section_4": section_4_price,
                    "special": special_price,
                },
                "tags": inferred["tags"],
                "recommendation_use_cases": inferred["recommendation_use_cases"],
                "notes": notes,
            }
        )
        official_rows.append(
            [
                category,
                seat_name,
                audience,
                str(section_1_price),
                str(section_2_price),
                str(section_3_price),
                str(section_4_price),
                str(special_price),
                note,
            ]
        )

    official_tables = [
        {
            "heading": "2026 한화 이글스 입장권 가격",
            "summary": f"Hanwha Eagles official Ticketlink guide image: {image_url}",
            "rows": official_rows,
        }
    ]
    return build_success_payload(source, seat_zones, official_tables)


def normalize_samsung_lions(html: str, source: dict[str, Any]) -> dict[str, Any]:
    match = re.search(r'<img src="([^"]*2026ticket_03\.png[^"]*)"', html)
    if not match:
        raise RuntimeError("Samsung Lions official ticket price image was not found.")

    image_path = match.group(1)
    image_url = (
        image_path
        if image_path.startswith("http")
        else "https://www.samsunglions.com" + image_path
    )

    seat_zones: list[dict[str, Any]] = []
    official_rows = [["좌석", "대상", "그레이", "화이트", "블루"]]
    for seat_name, audience, gray_price, white_price, blue_price in SAMSUNG_LIONS_PRICE_ROWS:
        inferred = infer_seat_tags(seat_name)
        seat_zones.append(
            {
                "seat_name": seat_name,
                "category": "일반석",
                "audience": audience,
                "side": inferred["side"],
                "price_krw": {
                    "gray": gray_price,
                    "white": white_price,
                    "blue": blue_price,
                },
                "tags": inferred["tags"],
                "recommendation_use_cases": inferred["recommendation_use_cases"],
                "notes": ["공식 이미지 가격표 수동 정규화"],
            }
        )
        official_rows.append(
            [seat_name, audience, str(gray_price), str(white_price), str(blue_price)]
        )

    official_tables = [
        {
            "heading": "2026 삼성 라이온즈 입장요금표",
            "summary": (
                f"Samsung Lions official ticket price image: {image_url}. "
                "그레이=화/수/목 일반 주중경기, 화이트=금/일/이벤트 주중경기, "
                "블루=토/공휴일/이벤트 주말경기."
            ),
            "rows": official_rows,
        }
    ]
    return build_success_payload(source, seat_zones, official_tables)


def normalize_nc_dinos(html: str, source: dict[str, Any]) -> dict[str, Any]:
    capacity_match = re.search(r"<td>\s*([\d,]+)석\s*</td>", html)
    capacity = parse_price(capacity_match.group(1)) if capacity_match else None
    map_match = re.search(r'<img src="([^"]*img_map\.jpg)"[^>]*alt="좌석배치도"', html)
    map_url = "https://www.ncdinos.com/assets/images/sub/img_map.jpg"
    if map_match:
        map_url = "https://www.ncdinos.com" + map_match.group(1)

    seat_zones: list[dict[str, Any]] = []
    official_rows = [["좌석", "좌석수/수량", "비고"]]
    for seat_name, count, note in [
        ("관중석", capacity, "공식 구장 안내의 총 관중석 수"),
        ("스카이박스", 32, "공식 구장 안내 본문에 표시된 스카이박스 수"),
        ("프리미엄석", None, "공식 구장 안내 본문에 언급된 좌석 구역"),
        ("내야석", None, "공식 구장 안내 본문에 언급된 좌석 구역"),
    ]:
        inferred = infer_seat_tags(seat_name)
        zone = {
            "seat_name": seat_name,
            "category": "좌석/시설",
            "audience": "all",
            "side": inferred["side"],
            "price_krw": {},
            "tags": inferred["tags"],
            "recommendation_use_cases": inferred["recommendation_use_cases"],
            "notes": [note, "NC 티켓 가격은 로그인 이후 예매 화면에서 노출되어 공식 공개 가격표 수집 불가"],
        }
        if count is not None:
            zone["capacity"] = count
        seat_zones.append(zone)
        official_rows.append([seat_name, str(count or ""), note])

    official_tables = [
        {
            "heading": "창원NC파크 좌석/시설 안내",
            "summary": f"NC Dinos official stadium guide seat map: {map_url}",
            "rows": official_rows,
        }
    ]
    return build_success_payload(source, seat_zones, official_tables)


def normalize_kt_wiz(html: str, source: dict[str, Any]) -> dict[str, Any]:
    resource_payload = json.loads(fetch_html(KT_WIZ_PRICE_RESOURCE_API_URL))
    image_url = (
        resource_payload.get("data", {})
        .get("resource", {})
        .get("value")
    )
    if not image_url:
        raise RuntimeError("KT Wiz official ticket price image resource was not found.")

    seat_zones: list[dict[str, Any]] = []
    official_rows = [["구분", "좌석", "주중(화/수/목)", "주말(금/토/일/공휴일)"]]
    for category, seat_name, weekday_price, weekend_price in KT_WIZ_PRICE_ROWS:
        inferred = infer_seat_tags(seat_name)
        seat_zones.append(
            {
                "seat_name": seat_name,
                "category": category,
                "audience": "all",
                "side": inferred["side"],
                "price_krw": {
                    "weekday": weekday_price,
                    "weekend": weekend_price,
                },
                "tags": inferred["tags"],
                "recommendation_use_cases": inferred["recommendation_use_cases"],
                "notes": ["공식 이미지 가격표 수동 정규화"],
            }
        )
        official_rows.append([category, seat_name, str(weekday_price), str(weekend_price)])

    official_tables = [
        {
            "heading": "2026 kt wiz park 티켓 금액",
            "summary": f"KT Wiz official ticket price image: {image_url}",
            "rows": official_rows,
        }
    ]
    return build_success_payload(source, seat_zones, official_tables)


def normalize_doosan_bears(html: str, source: dict[str, Any]) -> dict[str, Any]:
    seat_zones: list[dict[str, Any]] = []
    for seat_name, capacity_text in re.findall(r"([A-Za-z가-힣]+석)\s*:\s*([\d,]+)석", html):
        normalized_name = normalize_seat_name(seat_name)
        capacity = parse_price(capacity_text)
        inferred = infer_seat_tags(normalized_name)
        seat_zones.append(
            {
                "seat_name": normalized_name,
                "category": "좌석수",
                "audience": "all",
                "side": inferred["side"],
                "capacity": capacity,
                "price_krw": {},
                "tags": inferred["tags"],
                "recommendation_use_cases": inferred["recommendation_use_cases"],
                "notes": ["공식 홈구장 안내의 좌석수 기준이며, 가격표는 포함되지 않음"],
            }
        )

    official_tables = [
        {
            "heading": "잠실야구장 좌석수",
            "summary": "두산베어스 공식 홈구장 안내에 표시된 좌석 구역별 좌석수",
            "rows": [["좌석", "좌석수"]]
            + [[zone["seat_name"], str(zone.get("capacity") or "")] for zone in seat_zones],
        }
    ]
    return build_success_payload(source, seat_zones, official_tables)


def build_success_payload(
    source: dict[str, Any],
    seat_zones: list[dict[str, Any]],
    official_tables: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "ok": True,
        "data": {
            "stadium_id": source["stadium_id"],
            "stadium_name": source["stadium_name"],
            "team": source["team"],
            "season": 2026,
            "seat_zone_count": len(seat_zones),
            "seat_zones": seat_zones,
            "official_tables": official_tables,
        },
        "error": None,
        "metadata": {
            "source": source["source_name"],
            "source_url": source["url"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "fallback_used": False,
        },
    }


def get_source(source_id: str) -> dict[str, Any]:
    if source_id not in STADIUM_SEAT_SOURCES:
        raise ValueError(f"Unsupported stadium seat source id: {source_id}")
    return STADIUM_SEAT_SOURCES[source_id]


def fetch_source_html(source: dict[str, Any]) -> str:
    if not source.get("url"):
        raise ValueError(
            "Seat source URL is not configured yet: "
            f"{source['stadium_name']} / {source['team']}"
        )
    return fetch_html(source["url"])


def build_not_configured_payload(source: dict[str, Any], error_message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "data": {
            "stadium_id": source["stadium_id"],
            "stadium_name": source["stadium_name"],
            "team": source["team"],
            "seat_zone_count": 0,
            "seat_zones": [],
            "official_tables": [],
        },
        "error": {
            "code": "SEAT_SOURCE_NOT_CONFIGURED",
            "message": error_message,
        },
        "metadata": {
            "source": source["source_name"],
            "source_url": source.get("url"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "fallback_used": True,
        },
    }


def crawl_sajik_lotte_giants_seats() -> dict[str, Any]:
    source = get_source("sajik_lotte_giants")
    html = fetch_source_html(source)
    return normalize_sajik_lotte_giants(html, source)


def crawl_jamsil_lg_twins_seats() -> dict[str, Any]:
    source = get_source("jamsil_lg_twins")
    html = fetch_source_html(source)
    return normalize_lg_twins(html, source)


def crawl_jamsil_doosan_bears_seats() -> dict[str, Any]:
    source = get_source("jamsil_doosan_bears")
    html = fetch_source_html(source)
    return normalize_doosan_bears(html, source)


def crawl_gocheok_kiwoom_heroes_seats() -> dict[str, Any]:
    source = get_source("gocheok_kiwoom_heroes")
    html = fetch_source_html(source)
    return normalize_kiwoom_heroes(html, source)


def crawl_incheon_ssg_landers_seats() -> dict[str, Any]:
    source = get_source("incheon_ssg_landers")
    html = fetch_source_html(source)
    return normalize_ssg_landers(html, source)


def crawl_suwon_kt_wiz_seats() -> dict[str, Any]:
    source = get_source("suwon_kt_wiz")
    html = fetch_source_html(source)
    return normalize_kt_wiz(html, source)


def crawl_daejeon_hanwha_eagles_seats() -> dict[str, Any]:
    source = get_source("daejeon_hanwha_eagles")
    html = fetch_source_html(source)
    return normalize_hanwha_eagles(html, source)


def crawl_daegu_samsung_lions_seats() -> dict[str, Any]:
    source = get_source("daegu_samsung_lions")
    html = fetch_source_html(source)
    return normalize_samsung_lions(html, source)


def crawl_gwangju_kia_tigers_seats() -> dict[str, Any]:
    source = get_source("gwangju_kia_tigers")
    html = fetch_source_html(source)
    return normalize_kia_tigers(html, source)


def crawl_changwon_nc_dinos_seats() -> dict[str, Any]:
    source = get_source("changwon_nc_dinos")
    html = fetch_source_html(source)
    return normalize_nc_dinos(html, source)


def crawl_configured_official_table_source(source_id: str) -> dict[str, Any]:
    source = get_source(source_id)
    try:
        html = fetch_source_html(source)
    except ValueError as exc:
        return build_not_configured_payload(source, str(exc))

    parser = GiantsTicketParser()
    parser.feed(html)
    tables = extract_tables(parser.items)
    price_tables = [table for table in tables if is_generic_price_table(table)]

    return {
        "ok": True,
        "data": {
            "stadium_id": source["stadium_id"],
            "stadium_name": source["stadium_name"],
            "team": source["team"],
            "seat_zone_count": 0,
            "seat_zones": [],
            "official_tables": price_tables,
        },
        "error": None,
        "metadata": {
            "source": source["source_name"],
            "source_url": source.get("url"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "fallback_used": False,
            "normalization_status": "raw_tables_only",
        },
    }


CRAWLERS = {
    "jamsil_lg_twins": crawl_jamsil_lg_twins_seats,
    "jamsil_doosan_bears": crawl_jamsil_doosan_bears_seats,
    "gocheok_kiwoom_heroes": crawl_gocheok_kiwoom_heroes_seats,
    "incheon_ssg_landers": crawl_incheon_ssg_landers_seats,
    "suwon_kt_wiz": crawl_suwon_kt_wiz_seats,
    "daejeon_hanwha_eagles": crawl_daejeon_hanwha_eagles_seats,
    "daegu_samsung_lions": crawl_daegu_samsung_lions_seats,
    "gwangju_kia_tigers": crawl_gwangju_kia_tigers_seats,
    "changwon_nc_dinos": crawl_changwon_nc_dinos_seats,
    "sajik_lotte_giants": crawl_sajik_lotte_giants_seats,
}


def is_generic_price_table(table: dict[str, Any]) -> bool:
    joined = " ".join(" ".join(row) for row in table["rows"][:5])
    price_markers = ["가격", "요금", "주중", "주말", "평일", "공휴일"]
    seat_markers = ["좌석", "구역", "권종", "등급"]
    return any(marker in joined for marker in price_markers) and any(
        marker in joined for marker in seat_markers
    )


def crawl_stadium_seats(source_id: str) -> dict[str, Any]:
    if source_id not in CRAWLERS:
        raise ValueError(f"Unsupported stadium seat source id: {source_id}")
    return CRAWLERS[source_id]()


def default_output_path(source_id: str, output_dir: Path) -> Path:
    source = get_source(source_id)
    return output_dir / source["output_filename"]


def crawl_all_stadium_seats(output_dir: Path) -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    for source_id in CRAWLERS:
        payload = crawl_stadium_seats(source_id)
        output = default_output_path(source_id, output_dir)
        save_json(payload, output)
        results.append(
            {
                "source_id": source_id,
                "output": str(output),
                "ok": payload["ok"],
                "error": payload["error"],
            }
        )

    return {
        "ok": all(result["ok"] for result in results),
        "data": {"results": results},
        "error": None,
        "metadata": {
            "source": "stadium_seat_crawler",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def save_json(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl official KBO stadium seat guides.")
    parser.add_argument(
        "--stadium-id",
        choices=["all", *sorted(STADIUM_SEAT_SOURCES)],
        required=True,
        help="Use source ids such as sajik_lotte_giants, or all.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Single output JSON path. Not used with --stadium-id all.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/stadium_seats"),
        help="Output directory for default file names and --stadium-id all.",
    )
    args = parser.parse_args()

    if args.stadium_id == "all":
        summary = crawl_all_stadium_seats(args.output_dir)
        save_json(summary, args.output_dir / "crawl_all_stadium_seats_summary.json")
        return

    output = args.output or default_output_path(args.stadium_id, args.output_dir)
    payload = crawl_stadium_seats(args.stadium_id)
    save_json(payload, output)


if __name__ == "__main__":
    main()
