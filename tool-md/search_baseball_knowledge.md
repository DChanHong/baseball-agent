# search_baseball_knowledge

## 1. Tool 개요

| 항목 | 내용 |
| --- | --- |
| Tool 이름 | `search_baseball_knowledge` |
| 구현 위치 | `app/tools.py` |
| LangChain 등록 | `get_langchain_tools()`에서 `StructuredTool`로 등록 |
| 역할 | FAISS RAG 인덱스에서 좌석, 구장, 예매, 동선 관련 근거 문서를 검색한다. |
| 주요 데이터 | `data/raw/stadium_seats/*_seats.json`, `data/static/stadium_metadata.json`, `data/static/ticketing_guides.json`, `data/static/logistics_guides.json`, `data/index/faiss/` |
| 공통 반환 | `{ok, status, data, error}` |

## 2. 언제 호출하는가

- 최종 답변에 공식/정적 근거 문서가 필요할 때 호출한다.
- 좌석 추천에서 좌석 후보 문서를 찾기 위해 호출한다.
- 예매 가이드 또는 원정 동선에서 RAG 기반 문서를 찾기 위해 호출한다.
- `get_ticketing_guide`, `get_logistics_guide` 내부에서도 이 함수를 사용한다.

## 3. 입력 조건

| 입력 | 필수 | 타입 | 설명 |
| --- | --- | --- | --- |
| `query` | 필수 | `str` | 검색 문장. 예: `잠실 롯데 원정 그늘 응원 좌석`. |
| `purpose` | 필수 | `str` | 검색 목적. 예: `seat_recommendation`, `ticketing`, `logistics`, `stadium_info`. |
| `stadium_id` | 선택 | `str \| None` | 구장 필터. 문서 metadata의 `stadium_id`와 비교한다. |
| `team` | 선택 | `str \| None` | 팀 필터. `team_aliases.json` 기준으로 정규화 후 문서 metadata의 `team`과 비교한다. |
| `top_k` | 선택 | `int` | 검색 문서 수. 기본값은 4. |

필수 조건:

- `query.strip()`이 비어 있으면 안 된다.
- FAISS 인덱스 파일 `data/index/faiss/index.faiss`, `data/index/faiss/index.pkl`이 존재해야 한다.
- 검색 시 query embedding 생성을 위해 `OPENAI_API_KEY`가 필요하다.

## 4. 내부 처리 과정

1. `query`가 비어 있으면 `MISSING_QUERY`를 반환한다.
2. `query`, `purpose`, `stadium_id`, `team`을 합쳐 enriched query를 만든다.
3. `search_faiss_documents()`를 호출한다.
4. FAISS index가 없거나 OpenAI API key가 없으면 해당 실패를 그대로 반환한다.
5. 검색된 문서가 있으면 `stadium_id`, `team` 조건으로 후필터링한다.
6. 필터링 결과가 있으면 필터링된 문서를 사용하고, 없으면 원 검색 결과를 유지한다.
7. `found` 상태로 문서 목록을 반환한다.

## 5. 성공 출력

```json
{
  "ok": true,
  "status": "found",
  "data": {
    "query": "잠실 롯데 원정 그늘 응원 좌석",
    "purpose": "seat_recommendation",
    "documents": [
      {
        "content": "좌석 정보: 잠실야구장 두산 베어스 3루 네이비석...",
        "metadata": {
          "source_type": "stadium_seat",
          "source_file": "data/raw/stadium_seats/jamsil_doosan_bears_seats.json",
          "source_url": "https://www.doosanbears.com/...",
          "stadium_id": "jamsil",
          "stadium_name": "잠실야구장",
          "team": "두산 베어스",
          "seat_name": "3루 네이비석",
          "document_unit": "seat_zone",
          "data_limitations": "좌석/가격 데이터는 크롤링 시점 기준이며 실시간 잔여석을 반영하지 않는다."
        }
      }
    ]
  },
  "error": null
}
```

## 6. 실패 출력

| status | error.code | 발생 조건 | Agent 후속 행동 |
| --- | --- | --- | --- |
| `missing_required_input` | `MISSING_QUERY` | 검색 query가 비어 있음 | 더 구체적인 검색 문장을 만들거나 사용자에게 의도를 되묻는다. |
| `index_not_ready` | `FAISS_INDEX_NOT_FOUND` | FAISS 인덱스 파일이 없음 | 인덱스 생성 안내 또는 일반 가이드 fallback을 사용한다. |
| `missing_required_input` | `MISSING_OPENAI_API_KEY` | 검색용 embedding API key가 없음 | 검색 불가 한계를 설명하고 정적/fallback 답변으로 전환한다. |
| `auth_failed` | `INVALID_OPENAI_API_KEY` | OpenAI API key가 유효하지 않음 | 설정 오류를 설명하고 fallback한다. |
| `index_load_failed` | `FAISS_INDEX_LOAD_FAILED` | FAISS 로드 실패 | 인덱스 재생성 안내 또는 fallback한다. |
| `search_failed` | `FAISS_SEARCH_FAILED` | similarity search 실행 실패 | query를 넓히거나 fallback한다. |
| `no_documents_found` | `NO_DOCUMENTS_FOUND` | 검색 결과가 없음 | query를 넓혀 재검색하거나 일반 가이드로 답한다. |

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

### 예매

```text
get_ticketing_guide
  -> search_baseball_knowledge
-> final_answer
```

### 원정 동선

```text
get_logistics_guide
  -> search_baseball_knowledge
-> final_answer
```

## 8. Observability 체크포인트

- arguments의 `query`가 사용자 요청, 경기, 구장, 팀, 목적을 충분히 포함하는지 확인한다.
- `purpose`가 의도와 맞는지 확인한다.
- 좌석 추천에서는 반환 documents의 `metadata.source_type`이 `stadium_seat`인지 확인한다.
- 예매에서는 `ticketing_guide`, 동선에서는 `logistics_guide` 문서가 검색되는지 확인한다.
- `index_not_ready`가 발생하면 Agent가 같은 검색을 반복하지 않고 fallback 또는 설정 안내로 종료해야 한다.

