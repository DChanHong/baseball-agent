# score_seat_candidates

## 1. Tool 개요

| 항목 | 내용 |
| --- | --- |
| Tool 이름 | `score_seat_candidates` |
| 구현 위치 | `app/tools.py` |
| LangChain 등록 | `get_langchain_tools()`에서 `StructuredTool`로 등록 |
| 역할 | RAG로 찾은 좌석 후보 문서를 날씨, 선호, 예산, 응원 팀 기준으로 점수화한다. |
| 주요 입력 데이터 | `search_baseball_knowledge`의 `stadium_seat` documents, `get_weather_context` 결과, `find_kbo_game` 결과 |
| 공통 반환 | `{ok, status, data, error}` |

## 2. 언제 호출하는가

- 좌석 추천 요청에서 `search_baseball_knowledge`로 좌석 후보 문서를 찾은 뒤 호출한다.
- 최종 좌석 추천 답변을 만들기 전에 후보를 정렬해야 할 때 호출한다.
- Agent가 이 툴을 누락한 경우, `app/agent_loop.py`의 `_apply_seat_scoring_fallback()`이 조건을 만족하면 서버에서 보강 호출할 수 있다.

## 3. 입력 조건

| 입력 | 필수 | 타입 | 설명 |
| --- | --- | --- | --- |
| `game` | 필수 | `dict` | `find_kbo_game` 또는 session selected game 결과. 날짜, 시간, 홈/원정팀, 구장 정보가 들어간다. |
| `weather_context` | 필수 | `dict` | `get_weather_context`의 `data`. `risk_flags`, `recommendation_mode`를 사용한다. |
| `seat_documents` | 필수 | `list[dict]` | `search_baseball_knowledge`의 documents. `metadata.source_type == stadium_seat` 문서만 점수화한다. |
| `preferences` | 선택 | `list[str] \| str \| None` | 사용자 선호. 예: `가성비`, `응원`, `시야`, `그늘`. |
| `budget` | 선택 | `int \| None` | 예산. 문서 content에서 `원` 가격을 추출해 비교한다. |
| `cheering_team` | 선택 | `str \| None` | 응원 팀. 문서 metadata의 `team`과 비교한다. |

필수 조건:

- `seat_documents`가 비어 있으면 안 된다.
- 좌석 문서의 metadata에 `source_type: stadium_seat`가 있어야 실제 점수화 대상이 된다.

## 4. 내부 처리 과정

1. `seat_documents`가 비어 있으면 `NO_SEAT_DOCUMENTS`를 반환한다.
2. `preferences`를 비교 가능한 토큰 목록으로 정규화한다.
3. `weather_context.risk_flags`, `weather_context.recommendation_mode`를 읽는다.
4. 각 문서의 `content`, `metadata`를 확인한다.
5. `metadata.source_type`이 `stadium_seat`이 아닌 문서는 건너뛴다.
6. 기본 점수 50점에서 시작한다.
7. 예산과 문서 가격이 맞으면 가점, 예산 초과 가능성이 있으면 감점한다.
8. 사용자 선호가 문서 내용과 맞으면 가점한다.
9. `heat` risk가 있고 상단/네이비/시야형 좌석이면 가점한다.
10. `preference_based` 모드이면 소폭 가점한다.
11. 응원 팀과 문서 team이 맞으면 가점한다.
12. 점수 내림차순으로 정렬해 상위 3개 추천을 반환한다.

## 5. 성공 출력

```json
{
  "ok": true,
  "status": "scored",
  "data": {
    "game": {
      "game_id": "2026-05-16-롯데-두산-잠실",
      "date": "2026-05-16",
      "time": "17:00",
      "home_team": "두산",
      "away_team": "롯데",
      "stadium_id": "jamsil",
      "stadium_name": "잠실야구장"
    },
    "recommendation_mode": "weather_based",
    "recommendations": [
      {
        "seat_name": "3루 네이비석",
        "score": 78,
        "reasons": ["응원 선호와 일치", "더위 리스크에서 상단/시야형 좌석 우선"],
        "price_hint_krw": 18000,
        "stadium_id": "jamsil",
        "team": "두산 베어스",
        "source_url": "https://www.doosanbears.com/...",
        "data_limitations": "좌석/가격 데이터는 크롤링 시점 기준이며 실시간 잔여석을 반영하지 않는다."
      }
    ],
    "limitations": ["PRICE_DATA_LIMITED"]
  },
  "error": null
}
```

## 6. 실패 출력

| status | error.code | 발생 조건 | Agent 후속 행동 |
| --- | --- | --- | --- |
| `no_candidates` | `NO_SEAT_DOCUMENTS` | `seat_documents`가 비어 있음 | RAG 검색 query를 넓히거나 일반 좌석 가이드로 fallback한다. |
| `no_candidates` | `NO_SEAT_DOCUMENTS` | 문서가 있어도 `source_type=stadium_seat` 문서가 없음 | 좌석 목적 검색을 다시 수행하거나 한계를 설명한다. |

## 7. 예상 호출 흐름

```text
find_kbo_game
-> get_stadium_info
-> get_weather_context
-> search_baseball_knowledge
-> score_seat_candidates
-> final_answer
```

서버 보강 흐름:

```text
Agent가 좌석 추천 intent에서 score_seat_candidates를 누락
-> app/agent_loop.py::_apply_seat_scoring_fallback()
-> score_seat_candidates(fallback=server_enforced)
-> fallback_answer 또는 최종 답변 보강
```

## 8. Observability 체크포인트

- 좌석 추천 trace에서는 `score_seat_candidates`가 최종 답변 전에 호출되어야 한다.
- arguments에 전체 문서를 그대로 남기기보다 `game_id`, `seat_document_count`, fallback 여부처럼 요약된 값이 남을 수 있다.
- result의 `status=scored`와 recommendations가 최종 답변 근거로 사용되는지 확인한다.
- `NO_SEAT_DOCUMENTS` 발생 시 최종 답변에서 좌석 데이터 부족 한계를 설명해야 한다.
- `PRICE_DATA_LIMITED`가 limitations에 있으면 가격 확정 표현을 피해야 한다.

