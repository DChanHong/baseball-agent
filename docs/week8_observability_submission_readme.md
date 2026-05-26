# 8주차 AI Agent Observability

## 프로젝트 링크

- Repository: https://github.com/DChanHong/baseball-agent
- 7주차 제출 README: https://github.com/DChanHong/baseball-agent/blob/main/README.md

## 구현한 Observability

- 사용한 방식: LangSmith managed tracing + `/chat` 응답 metadata 요약
- trace 저장 위치: LangSmith project `kbo-game-day-agent`
- trace 단위: `/chat` 요청 1건을 trace 1건으로 기록
- trace id: 서버에서 `kbo_{uuid}` 형식으로 생성하고 LangSmith metadata와 `/chat` 응답 metadata에 함께 저장
- prompt version: `kbo-game-day-agent-v1`
- LangSmith run name: `kbo_game_day_agent`
- LangSmith tags: `kbo-agent`, `week8-observability`, `prompt:kbo-game-day-agent-v1`

기록하는 항목:

| 영역 | 항목 |
|------|------|
| Request | 사용자 입력, session id, trace id, 시작/종료 시각 |
| Prompt | prompt version, LangChain prompt 실행 흐름 |
| Model | Gemini chat model, OpenAI embedding model |
| Usage | LLM call count, input/output/total tokens, estimated cost |
| Tool | tool name, arguments, result, error, result_summary, sanitized observation_excerpt |
| Agent Step | step number, observation, step latency |
| Output | final answer, stop reason |
| Summary | trace_summary의 Tool 호출 수, 실패 Tool, Tool 순서, token/cost |
| Latency | 전체 elapsed_ms, tool별 latency_ms |

## Agent 실행 흐름

- Agent 이름: KBO 직관 가이드 Agent
- 실행 방식: LangChain `AgentExecutor` 기반 tool-calling agent
- 종료 조건: 최종 답변 생성, 최대 반복 횟수 8회, 최대 실행 시간 30초
- 주요 Tool:

| Tool | 역할 |
|------|------|
| `find_kbo_game` | 2026 KBO 일정 JSON에서 날짜, 팀, 구장 조건에 맞는 경기 조회 |
| `get_stadium_info` | 구장 위치, 돔 여부, 홈팀, 날씨 좌표 조회 |
| `get_weather_context` | Open-Meteo 또는 fallback 규칙으로 날씨 context 생성 |
| `search_baseball_knowledge` | FAISS RAG 기반 좌석, 예매, 동선 근거 문서 검색 |
| `score_seat_candidates` | 좌석 후보를 선호도, 날씨, 예산, 응원 기준으로 점수화 |
| `get_ticketing_guide` | 홈팀/구장 기준 예매처와 예매 팁 조회 |
| `get_logistics_guide` | 출발지/구장/경기 시간 기준 원정 동선 조회 |

## 정상 케이스 Trace 1: 일정 조회

입력:

```text
다음주 롯데 경기 알려줘
```

실행 요약:

| Step | Type | Name | 주요 입력 | 결과 |
|------|------|------|-----------|------|
| 1 | tool_call | `find_kbo_game` | `team_query=롯데`, `date_query=다음주` | `status=ambiguous_game`, 후보 6경기 |

Trace 정보:

| 항목 | 값 |
|------|----|
| session id | `codex-week8-normal-check` |
| trace id | `kbo_8f16708cde1346a0a742824b2dfb715a` |
| tool 호출 순서 | `find_kbo_game` |
| 전체 latency | 5574ms |
| stop reason | `final_answer` |

최종 답변 요약:

```text
다음주 롯데 후보 경기 6개를 제시하고, 어떤 경기를 더 자세히 볼지 추가 선택을 요청했다.
```

분석:

- 경기 일정은 RAG가 아니라 `find_kbo_game`의 deterministic lookup으로 처리됐다.
- 후보 경기 수가 6개로 반환됐다.
- 구장, 날씨, RAG, 좌석 점수화 Tool은 호출되지 않았다.

## 정상 케이스 Trace 2: 좌석 추천

입력:

```text
2026년 5월 23일 롯데 경기 좌석 추천해줘. 가성비 좋고 응원하기 좋은 자리로 알려줘
```

실행 요약:

| Step | Type | Name | 주요 입력 | 결과 |
|------|------|------|-----------|------|
| 1 | tool_call | `find_kbo_game` | `team_query=롯데`, `date=2026년 5월 23일` | `status=found`, 2026-05-23 사직 경기 확정 |
| 2 | tool_call | `get_stadium_info` | `stadium_id=sajik` | 사직야구장, 비돔 구장 |
| 3 | tool_call | `get_weather_context` | `game_date=2026-05-23`, `game_time=17:00`, `stadium_id=sajik` | `status=weather_based`, `risk_flags=[]` |
| 4 | tool_call | `search_baseball_knowledge` | `purpose=seat_recommendation`, 사직 가성비/응원 좌석 query | 좌석 후보 문서 4개 반환 |
| 5 | tool_call | `score_seat_candidates` | 선호도, 날씨 context, 좌석 후보, 경기 정보 | 좌석 추천 3개 반환, 1순위 `1루내야상단석` |

Trace 정보:

| 항목 | 값 |
|------|----|
| session id | `codex-week8-seat-recheck` |
| trace id | `kbo_2749677030f342458c2eecf42d95d30e` |
| tool 호출 순서 | `find_kbo_game` -> `get_stadium_info` -> `get_weather_context` -> `search_baseball_knowledge` -> `score_seat_candidates` |
| tool latency | 74ms -> 1ms -> 1125ms -> 2350ms -> 3ms |
| 전체 latency | 27267ms |
| stop reason | `final_answer` |

최종 답변 요약:

```text
2026-05-23 사직 롯데-삼성 경기 기준으로 맑은 날씨와 비돔 구장 조건을 설명하고,
가성비와 롯데 응원 선호를 반영해 1루내야상단석을 우선 추천했다.
좌석 가격은 크롤링 시점 기준이며 실시간 잔여석을 반영하지 않는다는 한계를 함께 안내했다.
```

분석:

- 단일턴 입력에서 경기 확정, 구장 조회, 날씨 조회, RAG 검색, 좌석 점수화가 모두 실행됐다.
- 좌석 추천 답변은 `score_seat_candidates` observation 이후에 생성됐다.
- tool latency 기준 병목은 `search_baseball_knowledge` 2350ms였고, 전체 latency에는 LLM reasoning 시간이 크게 포함됐다.

## 실패 또는 예외 케이스 Trace

입력:

```text
2026년 2월 1일 롯데 좌석 추천해줘
```

실행 요약:

| Step | Type | Name | 주요 입력 | 결과 |
|------|------|------|-----------|------|
| 1 | tool_call | `find_kbo_game` | `team_query=롯데`, `date_query=2026년 2월 1일` | `ok=false`, `status=not_found`, `error.code=GAME_NOT_FOUND` |

Trace 정보:

| 항목 | 값 |
|------|----|
| session id | `codex-week8-failure-check` |
| trace id | `kbo_86b9b90aa04b4dac85a1043eb4411bd0` |
| tool 호출 순서 | `find_kbo_game` |
| 전체 latency | 3679ms |
| stop reason | `final_answer` |

실패 처리:

- 경기 확정에 실패한 뒤 `get_stadium_info`, `get_weather_context`, `search_baseball_knowledge`, `score_seat_candidates`를 호출하지 않았다.
- Agent 실행 자체는 실패하지 않고 정상 종료됐다.
- 최종 답변은 해당 날짜에 롯데 경기를 찾을 수 없으니 다른 날짜나 조건을 입력해 달라는 fallback 성격으로 생성됐다.

## Trace 분석

- 예상한 흐름: 일정 조회는 `find_kbo_game`만 호출하고, 좌석 추천은 경기 확정 후 구장 정보, 날씨, RAG 검색, 좌석 점수화 순서로 진행해야 한다.
- 실제 흐름: 일정 조회, 좌석 추천, 실패 케이스 모두 예상 흐름과 일치했다.
- 잘 동작한 부분: 단일턴 좌석 추천에서도 `find_kbo_game`으로 경기를 확정한 뒤 필요한 Tool을 순서대로 호출했다. 실패 케이스에서는 불필요한 후속 Tool 호출 없이 fallback 답변으로 종료했다.
- 개선할 부분: 좌석 추천 trace의 전체 latency 27267ms 중 tool latency 합계보다 LLM reasoning 시간이 더 크므로, prompt 축약이나 deterministic pre-routing으로 지연을 줄일 수 있다.

## Metrics

| 항목 | 정상 일정 조회 | 정상 좌석 추천 | 실패 케이스 |
|------|----------------|----------------|-------------|
| total latency | 5574ms | 27267ms | 3679ms |
| step count | 1 | 5 | 1 |
| tool error count | 0 | 0 | 1 structured not_found |
| stop reason | `final_answer` | `final_answer` | `final_answer` |

## 민감정보 처리

- `.env`, API key, LangSmith API key는 commit하지 않는다.
- LangSmith metadata에는 전체 `user_context`를 저장하지 않고 `selected_game_id`, `selected_stadium_id`, 후보 경기 수처럼 재현에 필요한 요약값만 남긴다.
- Tool argument masking 규칙에서 `api_key`, `token`, `password`, `secret`, `payment_info`, `phone`, `email`, `address`는 `[excluded]`로 기록한다.
- `origin` 값이 긴 문자열이면 앞 2글자만 남기고 나머지는 마스킹한다.
- 제출용 trace에는 개인정보가 없는 예시 입력만 사용한다.
- RAG 문서 전문, API key, 로컬 `.env` 값은 README에 붙이지 않는다.

## 고도화 평가

| 평가 항목 | 구현 여부 | 결과 |
|-----------|-----------|------|
| correctness | 미구현 | trace 수동 분석으로 대체 |
| groundedness | 미구현 | Tool observation 기반 답변 여부를 수동 확인 |
| tool completeness | 미구현 | 정상/실패 골든 trace에서 수동 확인 |

## 배운 점

- 최종 답변만 저장하면 Agent가 어떤 근거로 답했는지 확인하기 어렵고, Tool argument와 observation이 함께 있어야 문제 원인을 추적할 수 있다.
- 일정 조회처럼 정확성이 중요한 단계는 RAG보다 구조화된 JSON lookup이 더 적합했다.
- 좌석 추천처럼 여러 Tool을 거치는 흐름은 tool latency와 전체 latency를 함께 봐야 병목을 제대로 구분할 수 있다.
