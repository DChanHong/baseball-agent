# get_weather_context

## 1. Tool 개요

| 항목 | 내용 |
| --- | --- |
| Tool 이름 | `get_weather_context` |
| 구현 위치 | `app/tools.py` |
| LangChain 등록 | `get_langchain_tools()`에서 `StructuredTool`로 등록 |
| 역할 | 경기 날짜, 경기 시간, 구장 돔 여부를 바탕으로 날씨 리스크와 좌석 추천 모드를 결정한다. |
| 주요 데이터/API | `data/static/stadium_metadata.json`, Open-Meteo forecast API, 날짜 범위 기반 rule |
| 공통 반환 | `{ok, status, data, error}` |

## 2. 언제 호출하는가

- 경기와 구장이 확정된 뒤 좌석 추천 전에 호출한다.
- 사용자가 날씨, 우천, 더위, 그늘, 돔 여부를 묻는 경우 호출한다.
- 좌석 추천에서 `weather_based`, `weather_risk_based`, `preference_based` 중 어떤 추천 방식을 쓸지 결정해야 할 때 호출한다.

## 3. 입력 조건

| 입력 | 필수 | 타입 | 설명 |
| --- | --- | --- | --- |
| `game_date` | 필수 | `str \| None` | 경기 날짜. ISO 날짜 또는 파싱 가능한 날짜 표현. |
| `game_time` | 선택 | `str \| None` | 경기 시작 시각. 없으면 기본 18시로 판단한다. |
| `stadium_id` | 권장 | `str \| None` | Open-Meteo 조회를 위한 구장 좌표 조회에 사용한다. |
| `is_dome` | 필수 성격 | `bool` | 돔구장 여부. 기본값은 `false`지만 정확한 판단을 위해 `get_stadium_info` 결과를 넘겨야 한다. |
| `weather_grid` | 선택 | `dict \| None` | 기상청 grid. 현재 구현은 반환 payload에 포함하지만 Open-Meteo 호출에는 사용하지 않는다. |

필수 조건:

- `game_date`가 유효한 날짜로 파싱되어야 한다.
- 정확한 추천을 위해 `get_stadium_info` 결과의 `is_dome`, `stadium_id`, `weather_grid`를 함께 넘기는 것이 예상 흐름이다.

## 4. 내부 처리 과정

1. `game_date`를 `_parse_date()`로 ISO 날짜로 변환한다.
2. 날짜가 없으면 `MISSING_DATE`, ISO 변환에 실패하면 `INVALID_DATE`를 반환한다.
3. `game_time`에서 시간을 추출한다. 없으면 18시로 둔다.
4. 오늘 기준 경기일까지 남은 일수를 계산한다.
5. 돔구장이면 Open-Meteo를 호출하지 않고 `preference_based`, `dome_adjusted`로 처리한다.
6. 야외 구장이고 0~3일 이내면 `weather_based`, `short_term`으로 처리한다.
7. 야외 구장이고 4~10일 이내면 `weather_risk_based`, `medium_term`으로 처리한다.
8. 11일 이후 또는 과거/범위 밖이면 `preference_based`, `unavailable`로 처리한다.
9. 0~10일 야외 경기이면 구장 좌표로 Open-Meteo forecast를 조회한다.
10. 예보 조회 성공 시 강수, 체감온도, 낮 경기 기준으로 `rain`, `heat`, `sun` risk flag를 만든다.
11. 예보 조회 실패 시 실패를 반환하지 않고 rule 기반 fallback summary와 보수적 risk flag를 반환한다.

## 5. 성공 출력

### 단기 예보 기반

```json
{
  "ok": true,
  "status": "weather_based",
  "data": {
    "stadium_id": "jamsil",
    "game_date": "2026-05-16",
    "game_time": "17:00",
    "recommendation_mode": "weather_based",
    "forecast_level": "short_term",
    "forecast_reliability": "high",
    "days_until_game": 1,
    "risk_flags": ["rain", "heat"],
    "weather_summary": "2026-05-16T17:00 기준 비, 기온 27도...",
    "weather_grid": {"nx": 61, "ny": 126},
    "forecast": {
      "provider": "open_meteo",
      "source_url": "https://api.open-meteo.com/...",
      "forecast_time": "2026-05-16T17:00",
      "temperature_c": 27,
      "apparent_temperature_c": 31,
      "precipitation_probability": 60,
      "precipitation_mm": 1.2,
      "weather_condition": "비"
    },
    "weather_provider_error": null
  },
  "error": null
}
```

### 예보 범위 초과 또는 정책상 미사용

```json
{
  "ok": true,
  "status": "forecast_unavailable_by_policy",
  "data": {
    "recommendation_mode": "preference_based",
    "forecast_level": "unavailable",
    "forecast_reliability": "none",
    "risk_flags": [],
    "weather_summary": "11일 이후 경기라 날씨 예보를 사용하지 않고 성향 기반으로 추천합니다."
  },
  "error": null
}
```

### 돔구장

```json
{
  "ok": true,
  "status": "preference_based",
  "data": {
    "recommendation_mode": "preference_based",
    "forecast_level": "dome_adjusted",
    "forecast_reliability": "medium",
    "risk_flags": [],
    "weather_summary": "돔구장이라 우천 리스크를 낮게 보고 시야, 응원, 가격 선호를 우선합니다."
  },
  "error": null
}
```

## 6. 실패 출력

| status | error.code | 발생 조건 | Agent 후속 행동 |
| --- | --- | --- | --- |
| `missing_required_input` | `MISSING_DATE` | 날짜가 없거나 파싱할 수 없음 | 경기 날짜를 되묻는다. |
| `missing_required_input` | `INVALID_DATE` | 날짜 문자열이 ISO 날짜로 변환되지 않음 | 날짜 형식을 다시 요청한다. |

참고:

- Open-Meteo 조회 실패는 현재 구현에서 Tool 실패로 반환하지 않는다.
- `weather_provider_error`에 실패 메시지를 담고, 날짜 범위 기반 fallback으로 `ok: true`를 반환한다.

## 7. 예상 호출 흐름

```text
find_kbo_game
-> get_stadium_info
-> get_weather_context
-> search_baseball_knowledge
-> score_seat_candidates
-> final_answer
```

## 8. Observability 체크포인트

- arguments에 `game_date`, `game_time`, `stadium_id`, `is_dome`가 들어갔는지 확인한다.
- `is_dome=true`인데 날씨 API 의존 답변을 하지 않는지 확인한다.
- `forecast_unavailable_by_policy`는 실패가 아니라 정책상 정상 결과로 처리되어야 한다.
- `weather_provider_error`가 있어도 `ok=true`이면 Agent가 한계를 설명하고 좌석 추천을 계속 진행해야 한다.
- `risk_flags`가 `score_seat_candidates`의 `weather_context`로 전달되는지 확인한다.

