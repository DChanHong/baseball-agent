# get_stadium_info

## 1. Tool 개요

| 항목 | 내용 |
| --- | --- |
| Tool 이름 | `get_stadium_info` |
| 구현 위치 | `app/tools.py` |
| LangChain 등록 | `get_langchain_tools()`에서 `StructuredTool`로 등록 |
| 역할 | 구장 ID, 구장명, 홈팀 기준으로 구장 메타데이터를 조회한다. |
| 주요 데이터 | `data/static/stadium_metadata.json`, `data/static/team_aliases.json` |
| 공통 반환 | `{ok, status, data, error}` |

## 2. 언제 호출하는가

- `find_kbo_game`으로 경기와 구장이 확정된 뒤 구장 상세 정보가 필요할 때 호출한다.
- 날씨 판단 전에 돔 여부, 좌표, weather grid가 필요할 때 호출한다.
- 좌석 추천, 예매 가이드, 원정 동선에서 구장 기준 정보를 정규화해야 할 때 호출한다.
- 사용자가 구장명이나 홈팀만 말했을 때 구장을 확정하기 위해 호출한다.

## 3. 입력 조건

| 입력 | 필수 | 타입 | 설명 |
| --- | --- | --- | --- |
| `stadium_id` | 조건부 필수 | `str \| None` | 내부 구장 ID. 예: `jamsil`, `gocheok`, `sajik`. |
| `stadium_name` | 조건부 필수 | `str \| None` | 구장명, 짧은 이름, 도시명, 홈팀 힌트. |
| `home_team` | 선택 | `str \| None` | 홈팀명. `stadium_id`, `stadium_name`으로 찾지 못한 경우 보조 조건으로 사용한다. |

필수 조건:

- `stadium_id`, `stadium_name`, `home_team` 중 하나로 구장을 찾을 수 있어야 한다.

## 4. 내부 처리 과정

1. `stadium_id` 또는 `stadium_name`을 `_normalize_stadium()`으로 정규화한다.
2. 구장을 찾지 못했고 `home_team`이 있으면 `_normalize_team()`으로 팀을 정규화한다.
3. 정규화된 팀명이 `stadium_metadata.json`의 `home_teams`에 포함되는 구장을 찾는다.
4. 구장을 찾지 못하면 `STADIUM_NOT_FOUND`를 반환한다.
5. 구장을 찾으면 위치, 돔 여부, 좌표, weather grid, 예매 기본 정보를 반환한다.

## 5. 성공 출력

```json
{
  "ok": true,
  "status": "found",
  "data": {
    "stadium_id": "jamsil",
    "stadium_name": "잠실야구장",
    "short_name": "잠실",
    "city": "서울",
    "is_dome": false,
    "home_teams": ["LG 트윈스", "두산 베어스"],
    "address": "서울특별시 송파구 올림픽로 25",
    "coordinates": {
      "lat": 37.5122,
      "lng": 127.0719
    },
    "weather_grid": {
      "nx": 61,
      "ny": 126
    },
    "capacity": 23750,
    "ticketing": {
      "platforms": ["티켓링크", "인터파크"],
      "note": "LG 홈경기는 티켓링크, 두산 홈경기는 인터파크 예매를 기본값으로 사용한다."
    }
  },
  "error": null
}
```

## 6. 실패 출력

| status | error.code | 발생 조건 | Agent 후속 행동 |
| --- | --- | --- | --- |
| `not_found` | `STADIUM_NOT_FOUND` | 입력값으로 지원 구장을 찾지 못함 | 구장명, 홈팀, 경기 정보를 다시 확인한다. |

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

### 날씨 질문

```text
find_kbo_game
-> get_stadium_info
-> get_weather_context
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

- `find_kbo_game`의 `stadium_id`가 `get_stadium_info` arguments로 이어지는지 확인한다.
- result의 `is_dome`, `coordinates`, `weather_grid`가 `get_weather_context` 호출에 사용되는지 확인한다.
- `STADIUM_NOT_FOUND` 발생 시 같은 입력으로 반복 호출하지 않고 구장/팀 확인 질문으로 종료해야 한다.

