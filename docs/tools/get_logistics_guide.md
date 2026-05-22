# get_logistics_guide

## 1. Tool 개요

| 항목 | 내용 |
| --- | --- |
| Tool 이름 | `get_logistics_guide` |
| 구현 위치 | `app/tools.py` |
| LangChain 등록 | `get_langchain_tools()`에서 `StructuredTool`로 등록 |
| 역할 | 출발지, 구장, 경기 날짜/시간 기준으로 원정 동선과 당일 복귀 리스크를 안내한다. |
| 주요 데이터 | `data/static/logistics_guides.json`, `data/static/stadium_metadata.json`, FAISS RAG 인덱스 |
| 공통 반환 | `{ok, status, data, error}` |

## 2. 언제 호출하는가

- 사용자가 원정, 동선, 교통, 막차, KTX, 버스, 당일 복귀, 숙박 대안을 묻는 경우 호출한다.
- 좌석/예매 안내와 함께 원정 플랜까지 묶어 달라는 요청에서 호출한다.
- 경기 일정과 구장이 확정된 뒤 출발지 기준 이동 가능성을 설명해야 할 때 호출한다.

## 3. 입력 조건

| 입력 | 필수 | 타입 | 설명 |
| --- | --- | --- | --- |
| `origin` | 필수 | `str \| None` | 출발지. 예: `부산`, `서울`, `대구`. |
| `stadium_id` | 조건부 필수 | `str \| None` | 도착 구장 ID. |
| `stadium_name` | 조건부 필수 | `str \| None` | 도착 구장명. `stadium_id`가 없을 때 정규화에 사용한다. |
| `game_date` | 필수 | `str \| None` | 경기 날짜. |
| `game_time` | 필수 | `str \| None` | 경기 시작 시각. |
| `preferred_transport` | 선택 | `str \| None` | 선호 이동 수단. 예: `KTX`, `버스`, `자차`. |
| `return_same_day` | 선택 | `bool \| None` | 당일 복귀 희망 여부. |

필수 조건:

- `origin`, `game_date`, `game_time`이 있어야 한다.
- `stadium_id` 또는 `stadium_name`으로 구장을 정규화할 수 있어야 한다.
- 내부적으로 `search_baseball_knowledge()`를 사용하므로 FAISS 인덱스와 `OPENAI_API_KEY`가 필요하다. 다만 검색 실패 시 일반 fallback 성공 응답을 반환한다.

## 4. 내부 처리 과정

1. `origin`이 없으면 `MISSING_ORIGIN`을 반환한다.
2. `game_date`가 없으면 `MISSING_DATE`를 반환한다.
3. `game_time`이 없으면 `MISSING_TIME`을 반환한다.
4. `stadium_id` 또는 `stadium_name`을 `_normalize_stadium()`으로 정규화한다.
5. 구장을 찾지 못하면 `MISSING_STADIUM`을 반환한다.
6. 출발지, 구장명, 구장 ID, 경기일, 경기시간, 이동수단, 당일 복귀 여부로 검색 query를 만든다.
7. `search_baseball_knowledge()`를 `purpose=logistics`, `top_k=5`로 호출한다.
8. 검색 성공 시 `metadata.source_type == logistics_guide` 문서를 우선 사용한다.
9. 검색 실패 시 Tool 실패로 끝내지 않고 `fallback_planned` 성공 응답을 반환한다.

## 5. 성공 출력

### RAG 동선 문서 조회 성공

```json
{
  "ok": true,
  "status": "planned",
  "data": {
    "origin": "부산",
    "stadium_id": "jamsil",
    "stadium_name": "잠실야구장",
    "game_date": "2026-05-16",
    "game_time": "17:00",
    "preferred_transport": "KTX",
    "return_same_day_requested": true,
    "documents": [
      {
        "content": "원정 동선 가이드: 부산 -> 잠실야구장...",
        "metadata": {
          "source_type": "logistics_guide",
          "source_file": "data/static/logistics_guides.json",
          "origin": "부산",
          "stadium_id": "jamsil",
          "stadium_name": "잠실야구장",
          "same_day_possible": "conditional",
          "document_unit": "origin_stadium_logistics",
          "data_limitations": "실시간 열차, 버스, 지하철 막차 API를 조회하지 않는다."
        }
      }
    ],
    "lookup_mode": "rag",
    "data_limitations": "실시간 열차, 버스, 지하철 막차 API를 조회하지 않고 인덱싱된 동선 rule을 근거로 답합니다."
  },
  "error": null
}
```

### RAG 검색 실패 후 일반 fallback

```json
{
  "ok": true,
  "status": "fallback_planned",
  "data": {
    "origin": "부산",
    "stadium_id": "jamsil",
    "stadium_name": "잠실야구장",
    "game_date": "2026-05-16",
    "game_time": "17:00",
    "recommended_routes": [],
    "return_plan": {
      "same_day_possible": "unknown",
      "note": "RAG 동선 문서를 찾지 못해 일반 원정 준비 기준으로 안내합니다."
    },
    "generic_fallback": {
      "recommended_checks": [
        "경기 종료 예상 시각에서 최소 60분 이상 여유를 두고 막차 확인",
        "연장전과 우천 지연 가능성을 고려한 숙박 대안 확보",
        "KTX/SRT/고속버스 마지막 출발 시각과 취소표 가능성 확인"
      ]
    },
    "lookup_mode": "fallback",
    "data_limitations": "실시간 교통 API를 조회하지 않습니다."
  },
  "error": null
}
```

## 6. 실패 출력

| status | error.code | 발생 조건 | Agent 후속 행동 |
| --- | --- | --- | --- |
| `missing_required_input` | `MISSING_ORIGIN` | 출발지가 없음 | 출발지를 되묻는다. |
| `missing_required_input` | `MISSING_DATE` | 경기 날짜가 없음 | 경기 날짜를 되묻는다. |
| `missing_required_input` | `MISSING_TIME` | 경기 시간이 없음 | 경기 시간을 되묻거나 일정 확정을 먼저 수행한다. |
| `missing_required_input` | `MISSING_STADIUM` | 구장을 정규화할 수 없음 | 경기 또는 구장 정보를 다시 확인한다. |

참고:

- RAG 검색 실패는 현재 구현상 Tool 실패가 아니라 `fallback_planned` 성공 응답으로 처리된다.

## 7. 예상 호출 흐름

```text
find_kbo_game
-> get_stadium_info
-> get_logistics_guide
-> final_answer
```

좌석/예매와 함께 묻는 복합 요청:

```text
find_kbo_game
-> get_stadium_info
-> get_weather_context
-> search_baseball_knowledge
-> score_seat_candidates
-> get_ticketing_guide
-> get_logistics_guide
-> final_answer
```

## 8. Observability 체크포인트

- arguments에 `origin`, `stadium_id` 또는 `stadium_name`, `game_date`, `game_time`이 모두 있는지 확인한다.
- `return_same_day=true` 요청이면 최종 답변에 당일 복귀 리스크와 숙박 대안이 포함되어야 한다.
- `lookup_mode=fallback`이면 실시간 교통 API를 조회하지 않았다는 한계를 설명해야 한다.
- `MISSING_ORIGIN` 발생 시 출발지를 되묻고 같은 인자로 반복 호출하지 않아야 한다.

