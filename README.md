# 7주차 AI Agent 구현 프로젝트

## 프로젝트 링크

- Repository: https://github.com/DChanHong/baseball-agent
- 6주차 설계 PR 또는 design.md: https://github.com/DChanHong/baseball-agent/blob/main/6weekOriginDesign.md

### 문서 구성

| 문서 | 설명 |
|------|------|
| `README.md` | 7주차 과제 제출용 README입니다. 구현한 Agent, 실행 방법, Tool 목록, 예시 실행, 성공 판정 기준을 정리했습니다. |
| `assignment.md` | 7주차 과제 안내와 제출 템플릿 원문을 보관한 문서입니다. |
| `6weekOriginDesign.md` | 6주차에 작성한 원본 Agent 설계서입니다. |
| `MVP_IMPLEMENTATION_DESIGN.md` | 6주차 설계를 실제 MVP로 구현하기 위한 개발 설계서입니다. 구현 범위, Tool 설계, 데이터 구조, 검증 기준을 정리했습니다. |
| `ADD_POLICY.md` | MVP 구현 중 추가한 정책과 범위 조정 내용을 정리한 문서입니다. |
| `docs/data_generation_notes.md` | KBO 일정, 구장 메타데이터, 좌석 데이터 등 수집/정규화 기준을 정리한 작업 노트입니다. |

## 구현한 Agent

- Agent 이름: KBO 직관 가이드 Agent
- 해결하려는 문제: KBO 직관 초심자와 원정 팬이 경기 일정, 구장, 날씨, 좌석, 예매, 이동 동선을 따로 찾아야 하는 번거로움을 줄이고 상황에 맞는 직관 계획을 제공합니다.
- 타깃 사용자: KBO 직관이 처음이거나 익숙하지 않은 구장으로 원정 관람을 계획하는 야구 팬

## 6주차 설계와의 연결

- 유지한 설계: 자연어 요청을 Agent가 해석하고, 경기 일정 조회 -> 구장/날씨 확인 -> 좌석 추천 또는 예매/동선 안내 Tool을 선택적으로 호출하는 구조를 유지했습니다. 사용자 입력이 부족하면 후보 경기 목록을 제시하고 후속 질문에서 세션 상태를 이어받는 흐름도 유지했습니다.
- 변경한 설계: 관전 포인트, 선수 정보, 맛집 추천, 실시간 교통/예매 잔여석 조회는 현재 MVP에서 미구현 상태입니다. 예매와 원정 동선은 실시간 API 대신 FAISS RAG에 인덱싱한 정적 가이드 문서를 기반으로 안내합니다.
- 변경 이유: 7주차 과제의 핵심인 Tool 2개 이상 구현, LLM의 Tool 선택, observation 기반 판단, 종료 조건, 실패 처리를 우선 검증하기 위해 범위를 줄였습니다. 실시간 예매/교통 API는 안정적인 데이터 확보와 예외 처리가 추가로 필요하여 현재 미구현 상태입니다.

## 사용한 Tool

| Tool 이름 | 실제/API/mock | 역할 |
|-----------|---------------|------|
| find_kbo_game | 실제 함수/크롤링 일정 데이터 | FAISS 인덱싱 없이 크롤링한 2026 KBO 일정 JSON을 직접 필터링하여 날짜, 팀, 상대팀, 구장 조건에 맞는 경기를 조회합니다. |
| get_stadium_info | 실제 함수/정적 구장 데이터 | 정적 구장 메타데이터를 기준으로 구장 위치, 돔 여부, 날씨 좌표, 예매 정보를 조회합니다. |
| get_weather_context | 실제 API/규칙 기반 fallback | Open-Meteo 예보 또는 날짜/돔구장 규칙을 바탕으로 날씨 리스크와 좌석 추천 모드를 판단합니다. |
| search_baseball_knowledge | 실제 RAG/FAISS | 크롤링한 구장 좌석 데이터와 정적 구장/예매/동선 가이드 문서를 FAISS에 인덱싱한 뒤 관련 근거 문서를 검색합니다. |
| score_seat_candidates | 실제 함수/RAG 결과 점수화 | FAISS에서 검색된 좌석 후보 문서를 날씨, 선호도, 예산, 응원 팀 기준으로 점수화합니다. |
| get_ticketing_guide | 실제 RAG/정적 가이드 | FAISS에 인덱싱한 예매 가이드 문서를 기반으로 홈 팀과 구장 기준의 예매처, 링크, 티켓팅 팁을 안내합니다. |
| get_logistics_guide | 실제 RAG/정적 가이드 | FAISS에 인덱싱한 원정 동선 가이드 문서를 기반으로 출발지, 구장, 경기 시간 기준의 이동 동선과 당일 복귀 리스크를 안내합니다. |

## 실행 패턴

- 선택한 패턴: LangChain AgentExecutor 기반 Tool-calling Agent 패턴을 사용했습니다. 실행 흐름은 ReAct와 유사하게 decide -> tool call -> observe -> decide -> final 구조로 동작합니다.
- 이유: 사용자의 자연어 요청에 따라 일정 조회, 구장 정보 조회, 날씨 확인, RAG 검색, 좌석 점수화, 예매/동선 안내 중 필요한 Tool 조합과 순서가 달라지기 때문입니다.
- 간단한 흐름: 사용자 입력을 FastAPI `/chat`에서 받고, 세션 전처리로 후보 경기 또는 선택 경기를 보강한 뒤 AgentExecutor가 필요한 Tool을 선택합니다. Tool 결과는 observation으로 기록되며, Agent는 observation을 바탕으로 추가 Tool을 호출하거나 최종 답변을 생성합니다. 종료 조건은 최대 반복 횟수와 최대 실행 시간으로 제한했습니다.

## 실행 방법

```bash
# 설치
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 환경 변수 설정
# .env 파일에 GEMINI_API_KEY, OPENAI_API_KEY를 설정합니다.
# 선택: GEMINI_MODEL, OPENAI_EMBEDDING_MODEL
# 선택: LangSmith trace를 남기려면 LANGSMITH_TRACING=true, LANGSMITH_API_KEY, LANGSMITH_PROJECT를 설정합니다.

# FAISS 인덱스가 없을 경우 생성
python -c "from app.tools import build_faiss_index; print(build_faiss_index())"

# 실행
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## 필요한 환경 변수

`.env.example`을 참고해 로컬에 `.env` 파일을 생성합니다. `.env` 파일은 API key가 포함되므로 commit하지 않습니다.

| 변수명 | 필수 여부 | 설명 |
|--------|-----------|------|
| GEMINI_API_KEY | 필수 | LangChain AgentExecutor에서 Gemini 모델을 호출하기 위한 API key입니다. |
| GEMINI_MODEL | 선택 | Agent reasoning과 최종 답변 생성에 사용할 Gemini 모델명입니다. 기본값은 `gemini-2.5-flash`입니다. |
| OPENAI_API_KEY | 필수 | FAISS 인덱스 생성과 RAG 검색 query embedding 생성을 위한 OpenAI API key입니다. |
| OPENAI_EMBEDDING_MODEL | 선택 | 임베딩 생성에 사용할 OpenAI embedding 모델명입니다. 기본값은 `text-embedding-3-small`입니다. |
| LANGSMITH_TRACING | 선택 | `true`로 설정하면 LangChain AgentExecutor 실행 trace를 LangSmith에 전송합니다. 기본값은 비활성입니다. |
| LANGSMITH_API_KEY | 선택 | LangSmith trace 전송에 사용하는 API key입니다. |
| LANGSMITH_PROJECT | 선택 | LangSmith에서 trace를 모을 project 이름입니다. 예: `kbo-game-day-agent-week8` |

## 8주차 Observability

- 사용한 방식: LangSmith managed tracing
- trace 단위: `/chat` 요청 1건을 LangSmith trace 1건으로 기록합니다.
- trace 식별자: 서버에서 `kbo_{uuid}` 형식의 `trace_id`를 만들고 LangSmith metadata와 `/chat` 응답 metadata에 함께 남깁니다.
- prompt version: `kbo-game-day-agent-v1`
- LangSmith run name: `kbo_game_day_agent`
- LangSmith tags: `kbo-agent`, `week8-observability`, `intent:{intent}`, `prompt:kbo-game-day-agent-v1`

LangSmith 활성화 예시:

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY="..."
export LANGSMITH_PROJECT="kbo-game-day-agent"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

기록되는 주요 항목:

| 영역 | 항목 |
|------|------|
| Request | 원문 사용자 요청, 전처리된 Agent 입력, session id, trace id |
| Prompt | prompt version, LangChain prompt 실행 흐름 |
| Model | Gemini chat model, OpenAI embedding model |
| Tool | LangChain tool call, tool arguments, tool output/error |
| Agent Step | AgentExecutor intermediate step, `/chat` 응답 metadata의 observation |
| Output | 최종 답변, stop reason |
| Latency | LangSmith run/span latency, `/chat` 응답의 전체 elapsed_ms |

Trace 실행 결과:

| 케이스 | 입력 | session id | trace id | 주요 Tool 흐름 | 결과 | latency |
|--------|------|------------|----------|----------------|------|---------|
| 정상 일정 조회 | `다음주 롯데 경기 알려줘` | `week8-normal-trace` | `kbo_4b07d3c7ce2e4d299c532352ecad1a7e` | `find_kbo_game` | 다음주 롯데 후보 경기 6개를 제시하고 추가 선택을 요청 | 4494ms |
| 정상 좌석 추천 | `다음주 롯데 경기 알려줘` -> `토요일 경기 좌석 추천해줘` | `week8-seat-flow-trace` | `kbo_627726ce282c416bbebbbca7aa3dcc77` | `select_game_from_session_state` -> `get_stadium_info` -> `get_weather_context` -> `search_baseball_knowledge` -> `score_seat_candidates` | 2026-05-23 사직 롯데 경기 기준 좌석 3개 추천 | 23569ms |
| 실패/예외 | `2026년 2월 1일 롯데 좌석 추천해줘` | `week8-not-found-trace` | `kbo_3814ca60b57f4209a888780841aa85f4` | `find_kbo_game` | `GAME_NOT_FOUND`를 확인하고 다른 날짜 입력을 요청 | 3413ms |

Trace 분석:

- 예상 흐름: 일정 조회는 `find_kbo_game`만 호출하고, 좌석 추천은 경기 선택 후 구장 정보, 날씨, RAG 검색, 좌석 점수화 순서로 진행해야 합니다.
- 실제 흐름: 좌석 추천 trace에서 session 후보 6개 중 토요일 경기를 먼저 선택한 뒤 `get_stadium_info`, `get_weather_context`, `search_baseball_knowledge`, `score_seat_candidates`가 순서대로 호출됐습니다.
- 잘 동작한 부분: 후속 요청의 짧은 입력인 `토요일 경기 좌석 추천해줘`에서도 session state를 사용해 2026-05-23 사직 경기를 확정했습니다.
- 실패 처리: 2026-02-01 롯데 경기 조회는 `find_kbo_game`이 `ok=false`, `status=not_found`, `error.code=GAME_NOT_FOUND`를 반환했고, Agent는 다른 날짜를 요청하는 답변으로 종료했습니다.
- 개선할 부분: 일부 단일턴 좌석 추천에서는 `score_seat_candidates`까지 가지 못하고 최종 답변 생성에 실패할 수 있어, 좌석 추천 intent에서는 경기 확정 여부를 더 엄격히 확인하는 보강이 필요합니다.

민감정보 처리:

- `.env`, API key, LangSmith API key는 commit하지 않습니다.
- 현재 MVP는 실제 사용자 DB, 결제정보, 주소, 전화번호를 받지 않습니다.
- LangSmith metadata에는 전체 `user_context`를 넣지 않고 `selected_game_id`, `selected_stadium_id`, 후보 경기 수처럼 재현에 필요한 요약값만 넣습니다.
- 사용자 입력 원문은 LangSmith에 기록되므로, 제출용 trace를 공유할 때는 개인정보가 포함되지 않은 예시 입력만 사용합니다.
- RAG 문서 전문, API key, 로컬 `.env` 값은 README나 제출 README에 붙이지 않습니다.

## 예시 실행

### 예시 1

입력:

```text
다음주 롯데 경기 보고싶다
```

출력:

```text
다음 주 롯데 자이언츠 경기는 다음과 같습니다.

* 5월 12일 (화) 18:30 NC vs 롯데 (부산 사직야구장)
* 5월 13일 (수) 18:30 NC vs 롯데 (부산 사직야구장)
* 5월 14일 (목) 18:30 NC vs 롯데 (부산 사직야구장)
* 5월 15일 (금) 18:30 롯데 vs 두산 (잠실야구장)
* 5월 16일 (토) 17:00 롯데 vs 두산 (잠실야구장)
* 5월 17일 (일) 14:00 롯데 vs 두산 (잠실야구장)

어떤 경기에 대해 더 자세히 알려드릴까요?
```

### 예시 2

입력:

```text
토요일 경기 좌석 추천해줘
```

출력:

```text
2026년 5월 16일 토요일 17:00 롯데와 두산의 잠실야구장 경기 좌석을 추천해 드립니다.

현재 날씨와 구장 정보를 함께 고려하여 좌석 후보를 추천합니다.

추천 좌석:
1. 레드석
2. 테이블석
3. 네이비석

좌석 추천은 FAISS에 인덱싱된 좌석 문서와 날씨 context를 바탕으로 score_seat_candidates Tool이 점수화한 결과를 사용했습니다.
```

## 실행 로그 분석 
-> 생략

## 성공 판정 기준 확인

| 기준 | 결과 | 근거 |
|------|------|------|
| Tool 2개 이상 구현 | 통과 | `find_kbo_game`, `get_weather_context`, `search_baseball_knowledge`, `score_seat_candidates`, `get_ticketing_guide`, `get_logistics_guide` 등 2개 이상의 Tool을 구현했습니다. |
| LLM이 Tool 사용 여부와 순서를 판단 | 통과 | LangChain AgentExecutor가 사용자 요청에 따라 구장 정보, 날씨, RAG 검색, 좌석 점수화, 예매/동선 Tool을 선택적으로 호출합니다. |
| Tool observation 기반 최종 답변 생성 | 통과 | `/chat` 응답 metadata의 `observations`에 Tool 결과가 기록되고, Agent는 해당 결과를 바탕으로 좌석 추천, 예매 안내, 동선 안내 답변을 생성합니다. |
| Tool 실패 처리 | 통과 | 모든 Tool은 `ok`, `status`, `data`, `error` 구조를 반환하며, 필수 입력 누락이나 검색 실패 시 구조화된 실패 응답을 반환합니다. |
| 종료 조건 | 통과 | AgentExecutor에 `MAX_ITERATIONS=6`, `MAX_EXECUTION_TIME=30`을 설정했습니다. |

## 구현하며 배운 점

(1) Agent가 사용할 수 있는 데이터는 단순히 많이 모으는 것보다, Tool이 안정적으로 조회할 수 있는 형태로 수집하는 것이 중요하다는 점을 확인했습니다. KBO 일정 데
이터는 경기 날짜, 시간, 홈/원정 팀, 구장명처럼 필터링에 필요한 필드가 명확해야 했고, 좌석 데이터는 이후 RAG 검색과 점수화에 사용할 수 있도록 좌석명, 가격, 특징, 출처 정보를 함께 보
존해야 했습니다.

(2) 일정 조회처럼 정확한 필터링이 필요한 기능은 FAISS 검색보다 구조화된 JSON을 직접 조회하는 방식이 더 적합했습니다.

(3) 개발 과정에서 Agent 패턴에 대한 의문도 정리할 수 있었습니다.
 처음에는 Plan-and-Execute 패턴을 생각했지만, 실제 구현은 별도의 planner가 전체 계획을 먼저 세우는 구조가 아니라
LangChain AgentExecutor가 매 단계마다 필요한 Tool을 선택하는 Tool-calling Agent 구조에 가까웠습니다. 설계전 생각과는 다른 방향으로 흘러가기도 한 것을 확인했습니다.



- ...

## 주의사항

- API key, `.env`, 개인 token은 절대 commit하지 않습니다.
- 실제 결제, 환불, 이메일 발송, 삭제 등 side effect가 있는 Tool은 mock으로 대체합니다.
- 실제 개인정보가 포함된 DB를 사용하지 않습니다.
- 공개 API를 사용할 경우 rate limit과 실패 응답을 처리합니다.
- 6주차 설계와 달라진 부분은 반드시 README에 적습니다.
