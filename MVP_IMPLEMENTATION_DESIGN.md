# MVP 개발 설계서

## 1. 목표

이 프로젝트의 MVP는 KBO 직관 초심자와 원정 팬을 위한 챗봇형 Agent 서비스다.

사용자는 자연어로 다음과 같은 요청을 한다.

- "다음 주 토요일 잠실 롯데전 자리 추천해줘"
- "부산에서 잠실 원정 가는데 막차 괜찮아?"
- "한화 홈경기 예매는 어디서 하고 언제 열려?"

서버는 LangChain Agent가 필요한 Tool을 선택해 실행하고, 경기/구장/좌석/날씨/예매/동선 데이터를 조합해 답변한다.

## 2. MVP 범위

`ADD_POLICY.md` 기준으로 MVP는 6주차 설계의 Must-have 중 아래 3개를 우선 구현한다.

| 기능 | 구현 방식 | 데이터 |
| --- | --- | --- |
| 경기 및 날씨 기반 자동 좌석 추천 | LangChain Agent + RAG Tool + scoring Tool | KBO 일정, 구장 메타데이터, 좌석 인덱스, 날씨 mock/API |
| 원정 팬 맞춤 동선 설계 | LangChain Agent + RAG/static Tool | 출발지/구장별 동선 rule |
| 티켓 예매 일정 및 가이드 | LangChain Agent + RAG/static Tool | 팀별 예매처, 예매 난이도, 티켓팅 팁 |

MVP에서 제외하거나 2차로 미루는 항목:

- 실시간 교통 API
- 실시간 예매 가능 좌석 크롤링
- 관전 포인트/응원가/선수 기록 분석
- 맛집/먹거리 RAG

### 2.1 6주차 설계와의 연결

6주차 `6weekOriginDesign.md`의 문제 정의와 사용자 시나리오는 유지한다.

유지하는 설계:

- KBO 직관 초심자와 원정 팬을 대상으로 한다.
- 사용자는 자연어로 경기, 좌석, 예매, 이동 관련 요청을 한다.
- Agent는 단순 조회와 상황 판단을 분리한다.
- 우천, 폭염, 돔구장 여부, 막차 부족, 정보 부족처럼 판단이 필요한 상황은 Agent가 Tool 결과를 관찰한 뒤 다음 행동을 결정한다.

MVP에서 변경하거나 축소한 설계:

- 6주차 Must-have 4개 중 `관전 포인트 및 응원 가이드`는 MVP 이후로 미룬다.
- 선수/라인업 분석, 응원가, 맛집 추천은 2차 기능으로 둔다.
- 교통 실시간 API와 예매처 실시간 크롤링은 MVP에서 사용하지 않고 static/mock 또는 RAG 기반 안내로 처리한다.
- 구장 좌석/예매/동선 정보는 크롤링/정적 JSON을 FAISS에 인덱싱한 RAG로 검색한다.

변경 이유:

- 7주차 과제의 핵심 조건인 Tool 2개 이상, LLM의 Tool 선택, observation 기반 판단, 종료 조건, 실패 처리를 먼저 확실히 검증하기 위해 범위를 줄인다.
- 이미 확보한 KBO 일정, 전구단 좌석 데이터, 구장 메타데이터를 MVP의 핵심 근거 데이터로 사용한다.
- 실시간 교통/예매 데이터는 변동성과 실패 가능성이 높으므로 Agent 구조가 안정화된 뒤 2차로 연동한다.

## 3. 프레임워크 선택

### 서버

- FastAPI
- `/chat` 엔드포인트 중심
- `/health` 상태 확인
- `/` 간단 HTML 클라이언트 제공

### Agent 프레임워크

- LangChain
- `AgentExecutor` 기반으로 Tool 호출 흐름을 구성한다.
- 답변 생성 모델은 Gemini API를 사용한다.
- 크롤링/정적 데이터 검색은 FAISS Vector Store 기반 RAG로 처리한다.
- 임베딩 모델은 OpenAI Embeddings를 사용한다.
- LangGraph는 MVP에서는 사용하지 않는다. 상태 전이와 재시도 정책이 복잡해지면 2차 고도화에서 검토한다.

### 모델 구성

| 용도 | 선택 |
| --- | --- |
| 답변/Agent reasoning 모델 | Gemini API |
| Embedding 모델 | OpenAI Embeddings |
| Vector Store | FAISS |
| Retriever | LangChain FAISS retriever |

환경변수는 아래처럼 분리한다.

```text
GEMINI_API_KEY=
GEMINI_MODEL=
OPENAI_API_KEY=
OPENAI_EMBEDDING_MODEL=
```

Gemini는 최종 답변 생성과 Tool 선택 판단에 사용한다. OpenAI API key는 문서 임베딩 생성에만 사용한다.

### 클라이언트

MVP에서는 NextJS 대신 FastAPI의 Jinja2 템플릿을 사용한다.

- Spring Thymeleaf와 가장 유사한 방식
- 서버에서 `templates/index.html` 렌더링
- `static/app.js`에서 `/chat` 호출
- 프론트엔드 서버를 따로 띄우지 않아도 됨

NextJS는 UI 요구가 커지거나 별도 프론트엔드 배포가 필요해질 때 도입한다.

## 4. 폴더 구조

과제 권장 구조에서 크게 벗어나지 않는다.

```text
my-baseball-agent/
  README.md
  MVP_IMPLEMENTATION_DESIGN.md
  requirements.txt
  app/
    __init__.py
    main.py          # FastAPI 엔드포인트, HTML 렌더링
    agent_loop.py    # LangChain AgentExecutor 구성 및 실행
    tools.py         # LangChain tools + 내부 데이터 조회 함수
    prompts.py       # system prompt, agent prompt
    schemas.py       # Request/Response Pydantic 모델
  templates/
    index.html       # 간단 채팅 클라이언트
  static/
    app.js           # /chat 호출
    style.css        # 최소 스타일
  data/
    index/
      faiss/
        index.faiss
        index.pkl
    raw/
      kbo_schedule_2026_03.json
      kbo_schedule_2026_04.json
      ...
      stadium_seats/
        *_seats.json
        crawl_all_stadium_seats_summary.json
    static/
      stadium_metadata.json
      team_aliases.json
      ticketing_guides.json
      logistics_guides.json
  examples/
    input_1.json
    input_2.json
```

MVP에서는 `services/`, `repositories/`, `agent/` 하위 폴더를 만들지 않는다. 데이터 로딩과 Tool wrapper는 우선 `app/tools.py`에 둔다. 파일이 커지면 이후 분리한다.

## 5. 엔드포인트

MVP는 엔드포인트를 최소화한다.

| Method | Path | 역할 |
| --- | --- | --- |
| GET | `/health` | 서버 상태 확인 |
| GET | `/` | HTML 채팅 클라이언트 |
| POST | `/chat` | LangChain Agent 실행 |

`/recommend/seat`, `/guide/ticketing`, `/guide/logistics` 같은 세부 API는 MVP 이후 필요할 때 분리한다.

### `/chat` 요청 예시

```json
{
  "message": "다음 주 토요일 잠실 롯데전 자리 추천해줘",
  "user_context": {
    "favorite_team": "롯데",
    "origin": "부산",
    "preferences": ["그늘", "응원", "가성비"]
  }
}
```

### `/chat` 응답 예시

```json
{
  "answer": "5월 16일 잠실 롯데 원정 경기는 ...",
  "metadata": {
    "intent": "seat_recommendation",
    "tools_used": [
      "find_kbo_game",
      "get_stadium_info",
      "get_weather_context",
      "search_baseball_knowledge",
      "score_seat_candidates"
    ],
    "stadium": "잠실야구장",
    "recommendation_mode": "weather_based"
  }
}
```

## 6. RAG 및 LangChain Tool 목록

MVP의 지식 검색은 크롤링/정적 데이터를 FAISS에 인덱싱한 RAG를 기본으로 한다.

역할 분리:

```text
RAG = 공식/정적 데이터 근거 검색
Rule Scoring = 검색된 좌석 후보 정렬
Agent = 어떤 Tool을 어떤 순서로 쓸지 판단
```

즉, 좌석 추천은 JSON을 직접 훑어 바로 답하는 방식이 아니라 아래 흐름을 따른다.

```text
find_kbo_game
  -> get_weather_context
  -> search_baseball_knowledge
  -> score_seat_candidates
  -> 최종 답변
```

### 6.0 Tool 계약 설계 원칙

Tool은 단순 기능명만 두지 않는다. Agent가 안정적으로 판단할 수 있도록 각 Tool마다 아래 계약을 명확히 정의한다.

필수 계약:

- 언제 호출하는가
- 필수 입력은 무엇인가
- 선택 입력은 무엇인가
- 성공 시 `status`와 `data`는 어떤 구조인가
- 실패 시 `status`, `error.code`, `error.message`는 무엇인가
- 실패했을 때 Agent가 어떤 fallback 또는 되묻기를 해야 하는가

공통 반환 형식:

```json
{
  "ok": true,
  "status": "found",
  "data": {},
  "error": null
}
```

실패 반환 형식:

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

Agent 판단 기준:

- `status=missing_required_input`: Tool을 억지로 재호출하지 않고 사용자에게 필요한 정보를 되묻는다.
- `status=not_found`: 입력 조건을 완화하거나 사용자에게 날짜/팀/구장을 다시 확인한다.
- `status=index_not_ready`: FAISS index 생성 안내 또는 JSON fallback을 사용한다.
- `status=no_candidates`: RAG 검색 query를 바꾸거나 일반 좌석 가이드로 fallback한다.
- `status=external_api_failed`: mock/static/rule 기반 fallback을 사용한다.

예시 1: `find_kbo_game` 계약

```text
언제 호출:
- 좌석 추천, 예매 가이드, 원정 동선 요청 전에 실제 경기 일정을 확정해야 할 때 호출한다.
- 사용자가 날짜와 팀을 모두 제공한 경우 호출한다.
- 날짜가 없으면 호출하지 않고 먼저 사용자에게 되묻는다.

필수 입력:
- date: YYYY-MM-DD 또는 해석 가능한 자연어 날짜
- team_query: 사용자가 말한 팀명 또는 별칭

선택 입력:
- stadium_query
- opponent_query
```

성공 출력:

```json
{
  "ok": true,
  "status": "found",
  "data": {
    "game_id": "20260516LTDO0",
    "date": "2026-05-16",
    "time": "17:00",
    "home_team": "두산 베어스",
    "away_team": "롯데 자이언츠",
    "stadium_id": "jamsil",
    "stadium_name": "잠실야구장"
  },
  "error": null
}
```

실패 출력:

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

Agent 후속 행동:

- `MISSING_DATE`: "어느 날짜 경기인지 알려주세요."라고 되묻는다.
- `GAME_NOT_FOUND`: 팀명과 날짜를 다시 확인한다.
- `AMBIGUOUS_GAME`: 후보 경기 목록을 보여주고 사용자가 선택하게 한다.

예시 2: `search_baseball_knowledge` 계약

```text
언제 호출:
- 공식/정적 데이터 근거가 필요한 경우 호출한다.
- 좌석 후보, 예매처, 구장 정보, 원정 동선 rule을 검색할 때 호출한다.
- 최종 답변에 source_url 근거가 필요한 경우 호출한다.

필수 입력:
- query: 검색 문장
- purpose: seat_recommendation | ticketing | logistics | stadium_info

선택 입력:
- stadium_id
- team
- top_k
```

성공 출력:

```json
{
  "ok": true,
  "status": "found",
  "data": {
    "query": "잠실 롯데 원정 그늘 응원 좌석",
    "documents": [
      {
        "content": "잠실야구장 3루 네이비석은 원정 응원과 가성비 측면에서...",
        "metadata": {
          "source_type": "stadium_seat",
          "stadium_id": "jamsil",
          "team": "LG 트윈스",
          "source_url": "https://www.lgtwins.com/ticket/general"
        }
      }
    ]
  },
  "error": null
}
```

실패 출력:

```json
{
  "ok": false,
  "status": "index_not_ready",
  "data": null,
  "error": {
    "code": "FAISS_INDEX_NOT_FOUND",
    "message": "FAISS 인덱스가 아직 생성되지 않았습니다."
  }
}
```

Agent 후속 행동:

- `FAISS_INDEX_NOT_FOUND`: index 생성 안내 또는 JSON fallback Tool을 사용한다.
- `NO_DOCUMENTS_FOUND`: query를 넓혀 재검색하거나 일반 가이드로 fallback한다.

예시 3: `score_seat_candidates` 계약

```text
언제 호출:
- RAG로 좌석 후보 문서를 찾은 뒤 호출한다.
- 날씨, 경기 시간, 사용자 선호를 반영해 최종 추천 순위를 매길 때 호출한다.

필수 입력:
- game
- weather_context
- seat_documents
- preferences

선택 입력:
- budget
- cheering_team
```

성공 출력:

```json
{
  "ok": true,
  "status": "scored",
  "data": {
    "recommendations": [
      {
        "seat_name": "3루 네이비석",
        "score": 86,
        "reasons": ["원정 응원 접근성", "상단 시야", "가성비"]
      }
    ],
    "limitations": []
  },
  "error": null
}
```

실패 출력:

```json
{
  "ok": false,
  "status": "no_candidates",
  "data": null,
  "error": {
    "code": "NO_SEAT_DOCUMENTS",
    "message": "점수화할 좌석 후보가 없습니다."
  }
}
```

Agent 후속 행동:

- `NO_SEAT_DOCUMENTS`: RAG 검색을 다시 수행하거나 구장 일반 좌석 가이드로 fallback한다.
- `PRICE_DATA_LIMITED`: 가격 기준을 제외하고 좌석/시설/응원 기준으로 추천한다.

### 6.1 `find_kbo_game`

역할:

- 사용자 요청의 날짜, 팀명, 구장 힌트를 바탕으로 KBO 경기 일정을 찾는다.

데이터:

- `data/raw/kbo_schedule_2026_*.json`
- `data/static/team_aliases.json`

반환:

```json
{
  "ok": true,
  "data": {
    "game_id": "20260516LTDO0",
    "date": "2026-05-16",
    "time": "17:00",
    "home_team": "두산 베어스",
    "away_team": "롯데 자이언츠",
    "stadium_id": "jamsil",
    "stadium_name": "잠실야구장"
  },
  "error": null
}
```

### 6.2 `get_stadium_info`

역할:

- 구장 위치, 돔 여부, 홈팀, 좌표, 기상청 grid, 예매처 기본 정보를 조회한다.

데이터:

- `data/static/stadium_metadata.json`

계약:

```text
언제 호출:
- 경기 일정이 확정된 뒤 구장 정보를 확인할 때 호출한다.
- 날씨 판단, 좌석 추천, 원정 동선 설계 전에 stadium_id 또는 stadium_name을 정규화해야 할 때 호출한다.

필수 입력:
- stadium_id 또는 stadium_name

선택 입력:
- home_team
```

성공 출력:

```json
{
  "ok": true,
  "status": "found",
  "data": {
    "stadium_id": "jamsil",
    "stadium_name": "잠실야구장",
    "city": "서울",
    "is_dome": false,
    "home_teams": ["LG 트윈스", "두산 베어스"],
    "weather_grid": {"nx": 61, "ny": 126},
    "ticketing": {
      "platforms": ["티켓링크", "인터파크"]
    }
  },
  "error": null
}
```

실패 출력:

```json
{
  "ok": false,
  "status": "not_found",
  "data": null,
  "error": {
    "code": "STADIUM_NOT_FOUND",
    "message": "지원하는 구장 정보에서 찾지 못했습니다."
  }
}
```

Agent 후속 행동:

- `STADIUM_NOT_FOUND`: 사용자에게 구장명 또는 홈팀을 다시 확인한다.
- `AMBIGUOUS_STADIUM`: 후보 구장 목록을 제시하고 선택을 요청한다.

### 6.3 `get_weather_context`

역할:

- 경기 날짜와 구장 정보를 바탕으로 날씨 추천 모드를 결정한다.
- `ADD_POLICY.md`의 날씨 예보 범위 정책을 따른다.

정책:

| 경기 날짜 범위 | 추천 모드 |
| --- | --- |
| 오늘 ~ 3일 뒤 | `weather_based` |
| 4일 뒤 ~ 10일 뒤 | `weather_risk_based` |
| 11일 이후 | `preference_based` |

MVP 구현:

- 1차: mock/rule 기반
- 2차: 기상청 API 연동

계약:

```text
언제 호출:
- 경기 날짜, 시간, 구장 정보가 확정된 뒤 좌석 추천 전에 호출한다.
- 우천/폭염/돔구장 여부에 따라 추천 모드를 결정해야 할 때 호출한다.

필수 입력:
- game_date
- game_time
- stadium_id
- is_dome

선택 입력:
- weather_grid
```

성공 출력:

```json
{
  "ok": true,
  "status": "weather_based",
  "data": {
    "recommendation_mode": "weather_based",
    "forecast_level": "short_term",
    "forecast_reliability": "high",
    "risk_flags": ["heat"],
    "weather_summary": "낮 경기 기준 기온이 높아 햇빛과 탈수 리스크가 있습니다."
  },
  "error": null
}
```

예보 범위 초과 정상 출력:

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

실패 출력:

```json
{
  "ok": false,
  "status": "external_api_failed",
  "data": null,
  "error": {
    "code": "WEATHER_PROVIDER_FAILED",
    "message": "날씨 데이터 조회에 실패했습니다."
  }
}
```

Agent 후속 행동:

- `forecast_unavailable_by_policy`: 실패로 보지 않고 `preference_based` 좌석 추천으로 진행한다.
- `WEATHER_PROVIDER_FAILED`: mock/static weather context 또는 `preference_based` fallback을 사용한다.
- `is_dome=true`: 우천 리스크를 낮게 보고 좌석 추천에서 비 회피보다 시야/응원/가격을 우선한다.

### 6.4 `search_baseball_knowledge`

역할:

- FAISS에 인덱싱된 야구 직관 지식을 검색한다.
- 좌석, 구장, 예매, 동선 데이터의 근거 문서를 반환한다.

데이터:

- `data/raw/stadium_seats/*_seats.json`
- `data/static/stadium_metadata.json`
- `data/static/ticketing_guides.json`
- `data/static/logistics_guides.json`

검색 대상:

- 좌석명
- 가격
- 태그
- 추천 use case
- 공식 source_url
- 구장 돔 여부/위치/홈팀
- 예매처/예매 팁
- 원정 동선 rule
- 데이터 한계와 주의사항

반환:

```json
{
  "ok": true,
  "data": {
    "query": "잠실 롯데 원정 그늘 응원 좌석",
    "documents": [
      {
        "content": "잠실야구장 LG/두산 좌석 정보 ...",
        "metadata": {
          "source_type": "stadium_seat",
          "stadium_id": "jamsil",
          "team": "두산 베어스",
          "source_url": "https://www.doosanbears.com/bears/stadium?tabId=seoul"
        }
      }
    ]
  },
  "error": null
}
```

### 6.5 `score_seat_candidates`

역할:

- RAG 검색 결과와 날씨/사용자 선호를 바탕으로 좌석 후보를 점수화한다.
- 최종 추천 좌석 2~3개와 추천 이유를 만든다.

입력:

- 경기 정보
- 날씨 context
- RAG documents
- 사용자 선호

추천 기준:

- 가격대
- 응원석/원정석
- 중앙 시야
- 테이블석/편의성
- 상단석/가성비
- 돔 여부
- 낮 경기 햇빛/폭염 리스크
- 우천 리스크

주의:

- 두산, NC는 공식 가격표가 아니라 좌석/시설 데이터 중심이다.
- 해당 구단은 가격 점수화에 제한이 있음을 응답 metadata에 표시한다.

### 6.6 `get_ticketing_guide`

역할:

- 팀별 예매처, 공식 링크, 예매 난이도, 티켓팅 팁을 제공한다.
- 기본 데이터는 RAG에 들어가지만, 예매 가이드 intent가 명확할 때는 정형 Tool로도 조회한다.

데이터:

- `data/static/ticketing_guides.json`

MVP 구현:

- 정적 데이터 기반
- 예매 오픈 일시는 정확 실시간 크롤링이 아니라 일반 rule/안내 수준

계약:

```text
언제 호출:
- 사용자가 예매처, 예매 오픈, 티켓팅 난이도, 티켓팅 팁을 묻는 경우 호출한다.
- 좌석 추천 후 예매 행동까지 안내해야 하는 경우 호출한다.

필수 입력:
- team 또는 stadium_id

선택 입력:
- game_date
- opponent
- popularity_hint
```

성공 출력:

```json
{
  "ok": true,
  "status": "found",
  "data": {
    "team": "한화 이글스",
    "stadium_id": "daejeon",
    "platform": "티켓링크",
    "official_url": "https://www.ticketlink.co.kr/sports/137/63",
    "difficulty": "high",
    "open_rule": "일반적으로 경기 D-7 전후 오픈 여부를 확인합니다.",
    "tips": ["로그인과 본인인증을 미리 완료하세요.", "인기 경기는 오픈 직후 접속하세요."]
  },
  "error": null
}
```

실패 출력:

```json
{
  "ok": false,
  "status": "not_found",
  "data": null,
  "error": {
    "code": "TICKETING_GUIDE_NOT_FOUND",
    "message": "해당 팀 또는 구장의 예매 가이드를 찾지 못했습니다."
  }
}
```

Agent 후속 행동:

- `TICKETING_GUIDE_NOT_FOUND`: RAG 검색으로 예매처 관련 문서를 다시 찾는다.
- `team`이 없으면 사용자의 응원 팀 또는 홈팀을 되묻는다.
- 정확한 예매 오픈 일시가 없는 경우 일반 rule과 공식 예매처 확인 안내로 답한다.

### 6.7 `get_logistics_guide`

역할:

- 출발지와 구장을 기준으로 원정 이동 시나리오를 제공한다.
- 기본 데이터는 RAG에 들어가지만, 동선 intent가 명확할 때는 정형 Tool로도 조회한다.

데이터:

- `data/static/logistics_guides.json`

MVP 구현:

- static/mock rule
- 기차/버스/자차/숙박 대안 안내
- 실시간 막차 API는 2차 고도화

계약:

```text
언제 호출:
- 사용자가 원정 동선, 출발 시간, 이동 수단, 막차 가능성, 숙박 대안을 묻는 경우 호출한다.
- 좌석/예매 안내와 함께 원정 플랜을 묶어 달라는 요청이 있을 때 호출한다.

필수 입력:
- origin
- stadium_id 또는 stadium_name
- game_date
- game_time

선택 입력:
- preferred_transport
- return_same_day
```

성공 출력:

```json
{
  "ok": true,
  "status": "planned",
  "data": {
    "origin": "부산",
    "stadium_id": "jamsil",
    "recommended_routes": [
      {
        "mode": "KTX+지하철",
        "summary": "부산역에서 서울역 이동 후 지하철로 잠실 이동",
        "estimated_duration_minutes": 210,
        "risk": "medium"
      }
    ],
    "return_plan": {
      "same_day_possible": "conditional",
      "note": "연장전 또는 늦은 종료 시 당일 복귀가 어려울 수 있습니다."
    }
  },
  "error": null
}
```

실패 출력:

```json
{
  "ok": false,
  "status": "missing_required_input",
  "data": null,
  "error": {
    "code": "MISSING_ORIGIN",
    "message": "원정 동선을 계산하려면 출발지가 필요합니다."
  }
}
```

Agent 후속 행동:

- `MISSING_ORIGIN`: 출발지를 되묻는다.
- `LOGISTICS_GUIDE_NOT_FOUND`: 일반 원정 준비 가이드와 숙박 fallback을 제공한다.
- `same_day_possible=conditional`: 경기 종료 지연 리스크와 숙박 대안을 함께 안내한다.

## 7. 데이터 준비 계획

현재 확보된 데이터:

- 2026 KBO 일정: `data/raw/kbo_schedule_2026_03~09.json`
- 전구단 좌석 데이터: `data/raw/stadium_seats/*.json`
- 구장 메타데이터: `data/static/stadium_metadata.json`

추가 작성할 정적 데이터:

| 파일 | 목적 |
| --- | --- |
| `data/static/team_aliases.json` | 사용자 입력 팀명과 KBO 일정 팀명 매칭 |
| `data/static/ticketing_guides.json` | 팀별 예매처, 공식 링크, 난이도, 팁 |
| `data/static/logistics_guides.json` | 출발지/구장별 원정 동선 rule |

인덱싱 방식:

- FAISS Vector Store를 사용한다.
- OpenAI Embeddings로 문서를 임베딩한다.
- 크롤링/정적 JSON을 LangChain `Document`로 변환한다.
- `data/index/faiss/`에 로컬 인덱스를 저장한다.
- Agent 실행 시 FAISS index를 로드해 Retriever Tool로 사용한다.
- 좌석 추천은 RAG 검색 결과를 기반으로 rule scoring을 적용한다.

RAG 문서 변환 단위:

| 데이터 | 문서 단위 |
| --- | --- |
| `stadium_seats/*.json` | 좌석 zone 1개당 1문서 |
| `stadium_metadata.json` | 구장 1개당 1문서 |
| `ticketing_guides.json` | 팀/구장 1개당 1문서 |
| `logistics_guides.json` | 출발지-구장 시나리오 1개당 1문서 |

RAG index 생성 스크립트는 MVP 구조를 크게 늘리지 않기 위해 `app/tools.py`에 먼저 구현할 수 있다. 필요하면 이후 `utils/build_rag_index.py`로 분리한다.

## 8. Agent 동작 설계

LangChain Agent가 자연어 요청을 해석하고 필요한 Tool을 선택한다.

기본 흐름:

```text
사용자 입력
  -> AgentExecutor
  -> Tool 선택
  -> Tool 실행
  -> Observation 확인
  -> 추가 Tool 선택 또는 최종 응답
```

주요 intent:

| Intent | 필요한 Tool |
| --- | --- |
| 좌석 추천 | `find_kbo_game`, `get_stadium_info`, `get_weather_context`, `search_baseball_knowledge`, `score_seat_candidates` |
| 티켓 예매 가이드 | `find_kbo_game`, `search_baseball_knowledge`, `get_ticketing_guide` |
| 원정 동선 | `find_kbo_game`, `get_stadium_info`, `search_baseball_knowledge`, `get_logistics_guide` |
| 복합 요청 | 위 Tool 조합 |

정보 부족 시:

- 날짜가 없으면 날짜를 묻는다.
- 팀이 없으면 응원 팀 또는 경기 팀을 묻는다.
- 원정 동선 요청에서 출발지가 없으면 출발지를 묻는다.

Tool 실패 시:

- 일정 조회 실패: 날짜/팀 재입력 요청
- 날씨 조회 실패: `preference_based` 좌석 추천으로 fallback
- RAG index 없음: 인덱스 생성 안내 또는 JSON fallback
- RAG 검색 결과 부족: 정형 JSON lookup fallback
- 좌석 가격 부재: 가격 점수 제외 후 좌석/시설 기준 추천
- 동선 데이터 부재: 일반 원정 준비 가이드로 fallback

종료 조건:

- `max_iterations=6`
- `max_execution_time=30`초
- `tool_failure_limit=2`
- `same_tool_same_args_limit=2`
- `handle_parsing_errors=true`
- `early_stopping_method="generate"`

종료 상태값:

| stop_reason | 의미 | Agent 응답 |
| --- | --- | --- |
| `final_answer` | 정상 최종 답변 생성 | 답변과 사용한 Tool metadata 반환 |
| `missing_required_input` | 필수 입력 부족 | 사용자에게 필요한 입력을 되묻기 |
| `max_iterations_exceeded` | 최대 반복 횟수 초과 | 현재까지 확인한 정보와 한계를 설명 |
| `max_execution_time_exceeded` | 시간 제한 초과 | 시간 초과 안내와 재시도 제안 |
| `tool_failure_limit_exceeded` | Tool 실패 횟수 초과 | fallback 가능 여부와 실패 원인 설명 |
| `repeated_tool_call_detected` | 같은 Tool/argument 반복 | 반복 중단 후 현재 정보 기준으로 답변 |

같은 Tool 반복 감지 기준:

- 직전 Tool 이름과 argument JSON이 동일한 호출이 2회 연속 발생하면 반복으로 본다.
- 반복 감지 시 Agent는 같은 Tool을 다시 호출하지 않고 `repeated_tool_call_detected`로 종료한다.

Tool 실패 횟수 기준:

- `ok=false` 결과가 전체 실행 중 2회 발생하면 `tool_failure_limit_exceeded`로 종료한다.
- 단, `forecast_unavailable_by_policy`처럼 `ok=true`인 정책 fallback은 실패 횟수에 포함하지 않는다.

### 8.1 Observation 및 로그 metadata

과제 검증을 위해 `/chat` 응답에는 Agent 실행 흐름을 확인할 수 있는 metadata를 포함한다.

`/chat` metadata 구조:

```json
{
  "intent": "seat_recommendation",
  "agent_mode": "langchain_agent_executor",
  "model": {
    "chat": "gemini",
    "embedding": "openai"
  },
  "tools_used": ["find_kbo_game", "search_baseball_knowledge"],
  "observations": [
    {
      "step": 1,
      "tool": "find_kbo_game",
      "arguments": {
        "date": "2026-05-16",
        "team_query": "롯데"
      },
      "result": {
        "ok": true,
        "status": "found"
      }
    }
  ],
  "stop_reason": "final_answer",
  "iterations": 3,
  "elapsed_ms": 1840,
  "fallback_used": false
}
```

metadata 필수 필드:

- `intent`
- `agent_mode`
- `tools_used`
- `observations`
- `stop_reason`
- `iterations`
- `elapsed_ms`
- `fallback_used`

Observation 필수 필드:

- `step`
- `tool`
- `arguments`
- `result.ok`
- `result.status`
- `result.error.code`

파일 로그:

- MVP에서는 별도 로그 파일 저장은 필수가 아니다.
- 우선 `/chat` 응답 metadata로 실행 흐름을 확인한다.
- README의 실행 로그 분석은 이 metadata를 복사해 작성한다.

### 8.2 성공 판정 기준과 테스트 매핑

과제 제출 시 최소 3개 성공 판정 기준을 실제 실행 결과로 확인한다.

| 기준 | 테스트 입력 | 확인할 것 |
| --- | --- | --- |
| 정상 Tool 조합 | "2026년 5월 16일 잠실 롯데전 자리 추천해줘" | `find_kbo_game -> get_stadium_info -> get_weather_context -> search_baseball_knowledge -> score_seat_candidates` 흐름이 metadata에 남는지 확인 |
| RAG 검색 동작 | "잠실 롯데 원정 응원석이랑 가격 근거 찾아줘" | `search_baseball_knowledge`가 FAISS 문서를 반환하고 `source_url` metadata가 포함되는지 확인 |
| Tool 실패/fallback | "잠실 롯데전 자리 추천해줘" | 날짜가 없어 Tool을 무리하게 호출하지 않고 `missing_required_input`으로 되묻는지 확인 |
| 예보 범위 정책 | "2026년 9월 20일 사직 롯데전 자리 추천해줘" | 11일 이후 경기면 `forecast_unavailable_by_policy`, `preference_based`로 처리되는지 확인 |
| 종료 조건 | FAISS index를 임시로 비활성화하거나 실패 Tool을 2회 발생시키는 테스트 | `tool_failure_limit_exceeded` 또는 `index_not_ready` fallback이 metadata에 남는지 확인 |

README에 기록할 최소 성공 판정 3개:

1. 정상 Tool 조합으로 좌석 추천 생성
2. Tool 실패 또는 정보 부족 시 fallback/되묻기
3. 종료 조건 또는 실패 횟수 제한 동작

가능하면 추가로 기록할 항목:

- FAISS RAG 검색 결과와 source_url
- 날씨 예보 범위 정책 동작
- 예매 가이드 또는 원정 동선 Tool 호출 흐름

## 9. 구현 순서

### 1단계: 의존성 정리

`requirements.txt`에 추가:

```text
langchain
langchain-openai
langchain-google-genai
faiss-cpu
python-dotenv
jinja2
```

환경변수:

```text
GEMINI_API_KEY=
GEMINI_MODEL=
OPENAI_API_KEY=
OPENAI_EMBEDDING_MODEL=
```

`GEMINI_MODEL`은 답변/Agent reasoning용이다. `OPENAI_EMBEDDING_MODEL`은 FAISS index 생성과 검색 query embedding용이다.

### 2단계: 스키마 추가

`app/schemas.py`

- `ChatRequest`
- `ChatResponse`
- `UserContext`
- `ToolObservation`

### 3단계: 정적 데이터 작성

추가 파일:

- `data/static/team_aliases.json`
- `data/static/ticketing_guides.json`
- `data/static/logistics_guides.json`

### 4단계: RAG Document builder 구현

`app/tools.py`

- 좌석 JSON을 Document로 변환
- 구장 metadata를 Document로 변환
- 예매/동선 static JSON을 Document로 변환
- 문서 metadata에 `source_type`, `stadium_id`, `team`, `source_url`, `data_limitations` 저장

### 5단계: FAISS index 생성/로드 구현

`app/tools.py`

- OpenAI Embeddings 초기화
- FAISS index 생성
- `data/index/faiss/`에 저장
- 기존 index 로드
- index가 없을 때 명확한 에러 또는 생성 안내 반환

### 6단계: Tool 구현

`app/tools.py`

- JSON 로더
- alias 정규화
- 일정 검색
- 구장 검색
- RAG 검색
- 좌석 후보 scoring
- 예매 가이드 조회
- 동선 가이드 조회
- LangChain `StructuredTool` wrapper

### 7단계: Agent 구성

`app/agent_loop.py`

- Gemini chat model 초기화
- prompt 구성
- tools 등록
- AgentExecutor 생성
- `max_iterations` 설정
- intermediate steps를 metadata로 반환

### 8단계: FastAPI 엔드포인트 갱신

`app/main.py`

- `/health`
- `/`
- `/chat`
- Jinja2 templates mount
- static files mount

### 9단계: 간단 클라이언트 구현

- `templates/index.html`
- `static/app.js`
- `static/style.css`

기능:

- 채팅 입력
- 답변 표시
- metadata/tools_used 접기 영역 표시

### 10단계: 예시 입력 작성

`examples/input_1.json`

- 좌석 추천 정상 케이스

`examples/input_2.json`

- 티켓 예매 또는 원정 동선 케이스

추가로 가능하면 실패/fallback 케이스도 README에 기록한다.

### 11단계: 검증

필수 검증:

```bash
venv/bin/python -m py_compile app/*.py
uvicorn app.main:app --reload
```

테스트할 요청:

1. "다음 주 토요일 잠실 롯데전 자리 추천해줘"
2. "부산에서 대전 한화 원정 가는데 동선 알려줘"
3. "삼성 홈경기 예매 어디서 해?"
4. "팀명 없이 자리 추천해줘" 같은 정보 부족 케이스

성공 기준:

- Tool 2개 이상 호출 가능
- FAISS RAG 검색 가능
- Agent가 Tool 결과를 observation으로 사용
- `/chat` 응답 정상
- Tool 실패 또는 정보 부족 처리
- 종료 조건 설정
- README에 실행 방법과 예시 결과 기록

## 10. 개발 원칙

- MVP에서는 파일과 구조를 늘리지 않는다.
- 크롤링한 데이터는 RAG 인덱싱 대상으로 사용한다.
- RAG는 근거 검색, scoring Tool은 추천 정렬, Agent는 실행 순서 판단을 담당한다.
- Tool 반환은 항상 `{ok, data, error}` 구조를 따른다.
- 실제 API 실패 시 mock/static fallback을 제공한다.
- 좌석/예매/동선 데이터 출처와 한계를 metadata에 남긴다.
- 두산/NC처럼 가격표가 없는 데이터는 추천에서 가격 점수화 제한을 명시한다.
- NextJS는 MVP 이후 UI 고도화 단계에서 검토한다.
