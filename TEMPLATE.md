# 7주차 AI Agent 구현 프로젝트

## 프로젝트 링크

- Repository: https://github.com/DChanHong/baseball-agent
- 6주차 설계 PR 또는 design.md: https://github.com/DChanHong/baseball-agent/blob/main/design.md

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

# FAISS 인덱스가 없을 경우 생성
python -c "from app.tools import build_faiss_index; print(build_faiss_index())"

# 실행
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

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

- ...

## 주의사항

- API key, `.env`, 개인 token은 절대 commit하지 않습니다.
- 실제 결제, 환불, 이메일 발송, 삭제 등 side effect가 있는 Tool은 mock으로 대체합니다.
- 실제 개인정보가 포함된 DB를 사용하지 않습니다.
- 공개 API를 사용할 경우 rate limit과 실패 응답을 처리합니다.
- 6주차 설계와 달라진 부분은 반드시 README에 적습니다.
