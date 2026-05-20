# 8주차 제출용 LangSmith Trace 계획

## 목적

8주차 Observability 과제 제출 README에 사용할 LangSmith trace를 미리 고정한다.

제출 README에서는 trace를 많이 나열하기보다, 정상 케이스와 실패 케이스를 명확히 비교한다.

## 제출용 골든 트레이스

### 1. 정상 일정 조회

입력:

```text
다음주 롯데 경기 알려줘
```

기대 Tool 흐름:

```text
find_kbo_game
```

확인할 포인트:

- 경기 일정은 RAG가 아니라 deterministic lookup으로 처리한다.
- `find_kbo_game`이 `ambiguous_game`을 반환한다.
- 후보 경기 수가 6개인지 확인한다.
- 최종 답변은 후보 경기 목록을 보여주고 추가 선택을 요청해야 한다.
- 불필요하게 구장, 날씨, RAG, 좌석 점수화 Tool을 호출하지 않아야 한다.

기록할 항목:

```text
trace id 또는 LangSmith URL:
session id:
tool 호출 순서:
find_kbo_game arguments:
find_kbo_game result_summary:
find_kbo_game latency_ms:
전체 latency_ms:
stop_reason:
최종 답변:
```

### 2. 정상 좌석 추천

입력:

```text
2026년 5월 23일 롯데 경기 좌석 추천해줘. 가성비 좋고 응원하기 좋은 자리로 알려줘
```

기대 Tool 흐름:

```text
find_kbo_game
-> get_stadium_info
-> get_weather_context
-> search_baseball_knowledge
-> score_seat_candidates
```

확인할 포인트:

- 일정 확정 후 구장, 날씨, RAG 검색, 좌석 점수화 순서로 진행한다.
- `search_baseball_knowledge`는 좌석 후보 검색에 사용한다.
- `score_seat_candidates` observation을 본 뒤 최종 좌석 추천을 생성한다.
- 추천 답변에 경기, 구장, 날씨/돔 여부, 추천 이유, 데이터 한계가 포함되는지 확인한다.
- 각 Tool의 latency를 비교해 병목 step을 확인한다.

기록할 항목:

```text
trace id 또는 LangSmith URL:
session id:
tool 호출 순서:
각 tool arguments:
각 tool result_summary:
각 tool latency_ms:
전체 latency_ms:
stop_reason:
최종 답변:
```

### 3. 실패/예외 케이스

입력:

```text
2026년 2월 1일 롯데 좌석 추천해줘
```

기대 Tool 흐름:

```text
find_kbo_game
```

확인할 포인트:

- `find_kbo_game`이 `ok=false`, `status=not_found`, `error.code=GAME_NOT_FOUND`를 반환한다.
- 경기 확정 실패 후 구장, 날씨, RAG, 좌석 점수화 Tool을 호출하지 않아야 한다.
- 최종 답변은 다른 날짜를 요청하는 fallback 성격이어야 한다.
- 실패 trace지만 Agent 실행 자체는 정상 종료되어야 한다.

기록할 항목:

```text
trace id 또는 LangSmith URL:
session id:
tool 호출 순서:
find_kbo_game arguments:
find_kbo_game result_summary:
find_kbo_game latency_ms:
전체 latency_ms:
stop_reason:
최종 답변:
```

## 선택 보강 Trace

예매/동선 흐름까지 보여주고 싶으면 아래 케이스를 추가한다. 필수는 아니다.

입력:

```text
2026년 5월 23일 롯데 경기 보러 서울에서 갈 건데 예매랑 당일 이동도 알려줘
```

기대 Tool 흐름:

```text
find_kbo_game
-> get_stadium_info
-> get_ticketing_guide
-> get_logistics_guide
-> search_baseball_knowledge
```

확인할 포인트:

- 정확한 예매처/정적 rule은 `get_ticketing_guide`, `get_logistics_guide`에서 가져온다.
- 설명, 주의사항, 근거 보강은 RAG 검색으로 처리한다.
- 실시간 잔여석이나 실시간 교통은 확정적으로 말하지 않아야 한다.

## 내일 이어서 할 일

진행 상태:

- LangSmith trace 3개를 기준으로 개인 repo README의 8주차 섹션을 1차 작성했다.
- 제출 템플릿에 맞춘 초안은 `docs/week8_observability_submission_readme.md`에 작성했다.
- 정상 일정 조회, 단일턴 좌석 추천, 실패/예외 trace id와 latency는 확보했다.
- 단일턴 좌석 추천 골든 케이스가 기대 Tool 흐름대로 실행되는 것을 확인했다.

남은 일:

1. 필요하면 LangSmith tracing 환경 변수를 다시 켠다.

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY="..."
export LANGSMITH_PROJECT="kbo-game-day-agent-week8"
```

2. 단일턴 좌석 추천 골든 케이스는 아래 trace를 사용한다.

```text
2026년 5월 23일 롯데 경기 좌석 추천해줘. 가성비 좋고 응원하기 좋은 자리로 알려줘
```

```text
trace id: kbo_2749677030f342458c2eecf42d95d30e
session id: codex-week8-seat-recheck
tool 호출 순서: find_kbo_game -> get_stadium_info -> get_weather_context -> search_baseball_knowledge -> score_seat_candidates
tool latency_ms: 74 -> 1 -> 1125 -> 2350 -> 3
전체 latency_ms: 27267
stop_reason: final_answer
```

3. 단일턴 trace의 기대 흐름은 확인 완료했다.

```text
find_kbo_game
-> get_stadium_info
-> get_weather_context
-> search_baseball_knowledge
-> score_seat_candidates
```

4. 각 trace에서 아래 정보를 수집한다.

```text
입력:
trace id 또는 LangSmith URL:
최종 답변:
tool 호출 순서:
각 tool arguments:
각 tool result_summary 또는 status/error:
각 tool latency_ms:
전체 latency_ms:
stop_reason:
```

5. 수집한 `/chat` 응답 metadata 또는 LangSmith trace 요약을 제출 초안에 반영한다.

6. 제출용 README에 다음 항목을 최종 점검한다.

- 구현한 Observability 방식
- Agent 실행 흐름
- 정상 케이스 Trace
- 실패 또는 예외 케이스 Trace
- Trace 분석
- 민감정보 처리 정책

## 분석할 질문

- 예상한 Tool 호출 흐름과 실제 흐름이 일치했는가?
- 누락된 Tool 또는 불필요한 반복 호출이 있었는가?
- Tool argument가 충분히 구체적이었는가?
- 실패 시 fallback 또는 종료가 적절했는가?
- latency가 큰 step은 어디였는가?
- 최종 답변이 Tool 결과를 벗어나지 않았는가?
