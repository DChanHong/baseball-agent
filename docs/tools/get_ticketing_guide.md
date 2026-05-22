# get_ticketing_guide

## 1. Tool 개요

| 항목 | 내용 |
| --- | --- |
| Tool 이름 | `get_ticketing_guide` |
| 구현 위치 | `app/tools.py` |
| LangChain 등록 | `get_langchain_tools()`에서 `StructuredTool`로 등록 |
| 역할 | 팀 또는 구장 기준으로 예매처, 공식 링크, 난이도, 티켓팅 팁 문서를 조회한다. |
| 주요 데이터 | `data/static/ticketing_guides.json`, FAISS RAG 인덱스 |
| 공통 반환 | `{ok, status, data, error}` |

## 2. 언제 호출하는가

- 사용자가 예매처, 예매 방법, 티켓팅, 예매 오픈, 공식 링크를 묻는 경우 호출한다.
- 좌석 추천 후 예매 행동까지 안내해야 하는 경우 호출한다.
- 경기 일정이 확정된 경우 `team`, `stadium_id`, `game_date`, `opponent`를 함께 넘겨 더 구체적인 예매 문서를 찾는다.

## 3. 입력 조건

| 입력 | 필수 | 타입 | 설명 |
| --- | --- | --- | --- |
| `team` | 조건부 필수 | `str \| None` | 예매 안내가 필요한 팀. 팀 alias로 정규화된다. |
| `stadium_id` | 조건부 필수 | `str \| None` | 구장 기준 예매 가이드 검색에 사용한다. |
| `game_date` | 선택 | `str \| None` | 경기일. 검색 query 보강에 사용한다. |
| `opponent` | 선택 | `str \| None` | 상대팀. 인기 경기/상대전 맥락 보강에 사용한다. |
| `popularity_hint` | 선택 | `str \| None` | 인기 경기, 주말 경기 같은 힌트. 반환 data에 포함된다. |

필수 조건:

- `team` 또는 `stadium_id` 중 하나는 있어야 한다.
- 내부적으로 `search_baseball_knowledge()`를 사용하므로 FAISS 인덱스와 `OPENAI_API_KEY`가 필요하다.

## 4. 내부 처리 과정

1. `team`과 `stadium_id`가 모두 없으면 `MISSING_TEAM`을 반환한다.
2. `team`이 있으면 `_normalize_team()`으로 정규화한다.
3. `예매 가이드`, `티켓팅`, `공식 예매처`, 팀명, 구장 ID, 상대팀, 경기일을 조합해 검색 query를 만든다.
4. `search_baseball_knowledge()`를 `purpose=ticketing`, `top_k=5`로 호출한다.
5. 검색 성공 시 `metadata.source_type == ticketing_guide` 문서를 우선 사용한다.
6. ticketing 문서가 없으면 검색된 문서 전체를 fallback 근거로 사용한다.
7. `lookup_mode: rag`, 실시간 예매 오픈/잔여석 미조회 한계를 포함해 반환한다.
8. 검색 실패 시 `TICKETING_GUIDE_NOT_FOUND`를 반환한다.

## 5. 성공 출력

```json
{
  "ok": true,
  "status": "found",
  "data": {
    "team": "두산 베어스",
    "stadium_id": "jamsil",
    "game_date": "2026-05-16",
    "opponent": "롯데 자이언츠",
    "popularity_hint": "주말 경기",
    "documents": [
      {
        "content": "예매 가이드: 두산 베어스...",
        "metadata": {
          "source_type": "ticketing_guide",
          "source_file": "data/static/ticketing_guides.json",
          "source_url": "https://tickets.interpark.com/contents/genre/sports",
          "stadium_id": "jamsil",
          "team": "두산 베어스",
          "platform": "인터파크",
          "difficulty": "high",
          "document_unit": "team_ticketing_guide",
          "data_limitations": "실시간 예매 오픈 시각과 잔여석은 조회하지 않는다."
        }
      }
    ],
    "lookup_mode": "rag",
    "data_limitations": "예매 오픈 시각과 잔여석은 실시간 조회하지 않고 인덱싱된 안내 문서를 근거로 답합니다."
  },
  "error": null
}
```

## 6. 실패 출력

| status | error.code | 발생 조건 | Agent 후속 행동 |
| --- | --- | --- | --- |
| `missing_required_input` | `MISSING_TEAM` | `team`, `stadium_id`가 모두 없음 | 응원 팀, 홈팀, 구장을 되묻는다. |
| `not_found` | `TICKETING_GUIDE_NOT_FOUND` | RAG 검색 실패 또는 인덱스/API 문제 | RAG 검색 오류 원인을 설명하고 일반 예매 가이드로 fallback한다. |

내부 검색에서 발생 가능한 주요 원인:

- `FAISS_INDEX_NOT_FOUND`
- `MISSING_OPENAI_API_KEY`
- `INVALID_OPENAI_API_KEY`
- `NO_DOCUMENTS_FOUND`
- `FAISS_SEARCH_FAILED`

## 7. 예상 호출 흐름

### 예매 단독 질문

```text
find_kbo_game 또는 get_stadium_info
-> get_ticketing_guide
-> final_answer
```

### 좌석 추천과 예매를 함께 묻는 경우

```text
find_kbo_game
-> get_stadium_info
-> get_weather_context
-> search_baseball_knowledge
-> score_seat_candidates
-> get_ticketing_guide
-> final_answer
```

## 8. Observability 체크포인트

- arguments에 `team` 또는 `stadium_id`가 반드시 있어야 한다.
- 정확한 예매 오픈 시각이나 잔여석을 확정적으로 말하지 않아야 한다.
- result의 `lookup_mode`가 `rag`인지 확인한다.
- documents의 `metadata.source_type`이 `ticketing_guide`인지 확인한다.
- `MISSING_TEAM`이면 팀/구장 정보를 되묻고 반복 호출하지 않아야 한다.

