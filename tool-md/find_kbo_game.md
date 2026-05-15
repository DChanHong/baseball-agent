# find_kbo_game

## 1. Tool 개요

| 항목 | 내용 |
| --- | --- |
| Tool 이름 | `find_kbo_game` |
| 구현 위치 | `app/tools.py` |
| LangChain 등록 | `get_langchain_tools()`에서 `StructuredTool`로 등록 |
| 역할 | 날짜, 팀, 상대팀, 구장 조건으로 2026 KBO 경기 일정을 조회한다. |
| 주요 데이터 | `data/raw/kbo_schedule_2026_*.json`, `data/static/team_aliases.json`, `data/static/stadium_metadata.json` |
| 공통 반환 | `{ok, status, data, error}` |

## 2. 언제 호출하는가

- 좌석 추천, 예매 가이드, 원정 동선 안내 전에 실제 경기 일정을 확정해야 할 때 호출한다.
- 사용자가 날짜와 팀을 함께 제공한 경우 호출한다.
- `오늘`, `내일`, `이번주`, `이번주말`, `다음주`, `다음주말`, `2026-05-16`, `2026년 5월 16일` 같은 날짜 표현을 포함한 요청에서 호출한다.
- `/chat` 서버 전처리에서도 일정/직관 요청처럼 보이면 Agent 실행 전에 같은 함수를 호출한다. 이 경우 trace arguments에 `source: server_preprocess`가 붙는다.

## 3. 입력 조건

| 입력 | 필수 | 타입 | 설명 |
| --- | --- | --- | --- |
| `date` | 필수 | `str \| None` | ISO 날짜 또는 한국어 상대 날짜/자연어 날짜 표현. `_parse_date_candidates()`로 하나 이상의 후보 날짜로 변환된다. |
| `team_query` | 조건부 필수 | `str \| None` | 사용자가 말한 팀명, 별칭, 문장 전체. `team_aliases.json` 기준으로 정규화한다. |
| `stadium_query` | 선택 | `str \| None` | 구장명, 짧은 구장명, 도시, 홈팀 힌트. |
| `opponent_query` | 선택 | `str \| None` | 상대팀 힌트. `team_query`가 없으면 팀 조건으로 대체 사용된다. |

필수 조건:

- `date`에서 날짜 후보를 만들 수 있어야 한다.
- `team_query` 또는 `opponent_query`에서 KBO 팀을 정규화할 수 있어야 한다.

## 4. 내부 처리 과정

1. `date`를 `_parse_date_candidates()`로 후보 날짜 목록으로 변환한다.
2. 날짜가 없으면 `MISSING_DATE`를 반환한다.
3. `team_query` 또는 `opponent_query`를 `_normalize_team()`으로 정규화한다.
4. 팀을 찾지 못하면 `MISSING_TEAM`을 반환한다.
5. `stadium_query`가 있으면 `_normalize_stadium()`으로 구장 조건을 만든다.
6. `data/raw/kbo_schedule_2026_*.json` 전체를 읽어 날짜, 팀, 상대팀, 구장 조건을 필터링한다.
7. 후보가 없으면 `GAME_NOT_FOUND`를 반환한다.
8. 후보가 2개 이상이면 `ambiguous_game`으로 후보 목록을 반환한다.
9. 후보가 1개이면 경기 상세 정보를 `found`로 반환한다.

## 5. 성공 출력

### 단일 경기 확정

```json
{
  "ok": true,
  "status": "found",
  "data": {
    "game_id": "2026-05-16-롯데-두산-잠실",
    "date": "2026-05-16",
    "weekday": "토",
    "time": "17:00",
    "home_team": "두산",
    "away_team": "롯데",
    "home_team_full": "두산 베어스",
    "away_team_full": "롯데 자이언츠",
    "stadium_id": "jamsil",
    "stadium_name": "잠실야구장",
    "stadium_short_name": "잠실",
    "source_url": "https://www.koreabaseball.com/..."
  },
  "error": null
}
```

### 여러 경기 후보

```json
{
  "ok": true,
  "status": "ambiguous_game",
  "data": {
    "candidates": [
      {
        "game_id": "2026-05-16-롯데-두산-잠실",
        "date": "2026-05-16",
        "weekday": "토",
        "time": "17:00",
        "home_team": "두산",
        "away_team": "롯데",
        "stadium_id": "jamsil",
        "stadium_name": "잠실야구장"
      }
    ]
  },
  "error": null
}
```

## 6. 실패 출력

| status | error.code | 발생 조건 | Agent 후속 행동 |
| --- | --- | --- | --- |
| `missing_required_input` | `MISSING_DATE` | 날짜 표현을 파싱할 수 없음 | 날짜를 되묻는다. 같은 인자로 반복 호출하지 않는다. |
| `missing_required_input` | `MISSING_TEAM` | 팀명/별칭을 정규화할 수 없음 | 팀명 또는 응원 팀을 되묻는다. |
| `not_found` | `GAME_NOT_FOUND` | 조건에 맞는 일정이 없음 | 날짜, 팀, 상대팀, 구장을 다시 확인하거나 조건 완화를 요청한다. |

## 7. 예상 호출 흐름

### 좌석 추천

```text
find_kbo_game
-> get_stadium_info
-> get_weather_context
-> search_baseball_knowledge
-> score_seat_candidates
-> final_answer
```

### 예매 가이드

```text
find_kbo_game
-> get_stadium_info 또는 get_ticketing_guide
-> search_baseball_knowledge
-> final_answer
```

### 원정 동선

```text
find_kbo_game
-> get_stadium_info
-> get_logistics_guide
-> final_answer
```

## 8. Observability 체크포인트

- trace에 `tool: find_kbo_game`이 남아야 한다.
- arguments에는 최소한 `date`, `team_query`가 남아야 한다.
- 서버 전처리 호출이면 arguments에 `source: server_preprocess`가 남는다.
- result에는 `ok`, `status`, `error`가 남아야 한다.
- `ambiguous_game`이면 후속 요청에서 `select_game_from_session_state` observation이 이어지는지 확인한다.
- `MISSING_DATE`, `MISSING_TEAM` 발생 시 같은 툴을 같은 인자로 반복 호출하지 않아야 한다.

