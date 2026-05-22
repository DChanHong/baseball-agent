# Tool 계약 문서

이 디렉터리는 8주차 Observability 과제에서 trace를 분석하기 전에, 각 Tool의 예상 입출력 조건과 호출 흐름을 명확히 정의하기 위한 문서 모음이다.

기준 자료:

- `docs/design/mvp_implementation_design.md`
- `app/tools.py`
- `app/agent_loop.py`
- `app/main.py`
- `data/static/*.json`
- `data/raw/**/*.json`

## LangChain 등록 Tool

| Tool | 문서 | 역할 |
| --- | --- | --- |
| `find_kbo_game` | [find_kbo_game.md](find_kbo_game.md) | 2026 KBO 일정 조회 |
| `get_stadium_info` | [get_stadium_info.md](get_stadium_info.md) | 구장 메타데이터 조회 |
| `get_weather_context` | [get_weather_context.md](get_weather_context.md) | 날씨 리스크 및 추천 모드 판단 |
| `search_baseball_knowledge` | [search_baseball_knowledge.md](search_baseball_knowledge.md) | FAISS RAG 근거 문서 검색 |
| `score_seat_candidates` | [score_seat_candidates.md](score_seat_candidates.md) | 좌석 후보 점수화 |
| `get_ticketing_guide` | [get_ticketing_guide.md](get_ticketing_guide.md) | 예매 가이드 조회 |
| `get_logistics_guide` | [get_logistics_guide.md](get_logistics_guide.md) | 원정 동선 가이드 조회 |

## 공통 반환 규칙

모든 public Tool은 다음 구조를 반환한다.

```json
{
  "ok": true,
  "status": "found",
  "data": {},
  "error": null
}
```

실패 시에는 다음 구조를 반환한다.

```json
{
  "ok": false,
  "status": "missing_required_input",
  "data": null,
  "error": {
    "code": "MISSING_DATE",
    "message": "경기 날짜가 필요합니다."
  }
}
```

## 대표 예상 흐름

### 좌석 추천

```text
find_kbo_game
-> get_stadium_info
-> get_weather_context
-> search_baseball_knowledge
-> score_seat_candidates
-> final_answer
```

### 예매 안내

```text
find_kbo_game
-> get_stadium_info
-> get_ticketing_guide
-> final_answer
```

### 원정 동선

```text
find_kbo_game
-> get_stadium_info
-> get_logistics_guide
-> final_answer
```

## trace 분석 시 공통 확인 항목

- 예상한 Tool 순서와 실제 `metadata.observations` 순서가 일치하는가.
- 각 Tool arguments가 필수 입력을 충분히 포함하는가.
- 각 Tool result에 `ok`, `status`, `error`가 남는가.
- 실패 시 같은 Tool과 같은 arguments를 반복 호출하지 않는가.
- 최종 답변이 Tool result 또는 RAG documents를 벗어나지 않는가.
- 실시간 잔여석, 실시간 교통, 정확한 예매 오픈 시각처럼 MVP 범위 밖 정보를 확정적으로 말하지 않는가.
