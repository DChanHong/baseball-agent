# 11주차 LLM Fine-tuning Dataset 준비

## Fine-tuning 후보 작업

- 작업 이름: KBO 직관 가이드 Agent 다음 행동 판단
- 개선하려는 행동: 사용자 요청과 세션 정보를 바탕으로 Intent, 필요한 Tool과 실행 순서, 추가 질문 필요 여부, 부족한 정보를 일관된 JSON으로 판단하도록 개선합니다.
- Fine-tuning이 필요한 이유: 같은 목적의 요청도 사용자 표현과 세션 상태에 따라 Tool 선택 결과가 달라질 수 있습니다. 또한 JSON 형식이 깨지거나 필요한 Tool이 누락되면 Agent 실행이 실패할 수 있으므로, 사람이 검수한 정답 행동을 학습 데이터로 정의할 필요가 있습니다.
- RAG나 Prompt Engineering이 먼저가 아닌 이유: 이 작업은 최신 외부 지식을 검색하는 문제가 아니라, 사전에 정의된 Intent와 Tool 안에서 반복적인 분류와 라우팅 판단을 수행하는 문제입니다. Prompt Engineering만으로는 다양한 표현과 세션 상태에 대한 일관성을 측정하기 어려우므로, 정답 Dataset을 먼저 구축했습니다.

## Dataset 개요

- 데이터 출처: AI 합성데이터 + 사람 검수
- Dataset 경로: [`dataset.jsonl`](dataset.jsonl)
- 검수용 Pretty JSON 경로: [`dataset.pretty.json`](dataset.pretty.json)
- 원본 링크: 별도 외부 원본 없음
- 라이선스: 직접 작성한 합성데이터로 외부 저작물 라이선스 위험이 낮습니다.
- 최종 row 수: 19개
- 출력 형식: `messages` 기반 JSONL이며, `assistant.content`는 다음 행동 판단 JSON 문자열입니다.

### Dataset 구성

| Intent | Row 수 |
|---|---:|
| `schedule_lookup` | 2 |
| `stadium_info` | 1 |
| `seat_recommendation` | 5 |
| `weather_lookup` | 2 |
| `ticketing_guide` | 3 |
| `logistics_guide` | 2 |
| `multi_intent` | 2 |
| `casual_interaction` | 1 |
| `out_of_scope` | 1 |

추가 질문이 필요한 요청은 3개이며, Tool 호출 정상 사례, 세션 기반 후속 요청, 복합 Intent, Tool 없는 응답과 거절 사례를 함께 포함했습니다.

## Schema

Assistant 응답 형식:

```json
{
  "intent": "seat_recommendation",
  "required_tools": [
    "find_kbo_game",
    "get_stadium_info",
    "get_weather_context",
    "search_baseball_knowledge",
    "score_seat_candidates"
  ],
  "needs_clarification": false,
  "missing_fields": [],
  "next_action": "call_tools"
}
```

### 필드 정의

| 필드 | 타입 | 설명 |
|---|---|---|
| `intent` | string | 사용자 요청의 주요 의도입니다. |
| `required_tools` | array[string] | 호출할 Tool을 실행 순서대로 기록합니다. |
| `needs_clarification` | boolean | Tool 호출 전에 추가 질문이 필요한지를 나타냅니다. |
| `missing_fields` | array[string] | 사용자 또는 세션 정보에서 부족한 필드를 기록합니다. |
| `next_action` | string | Agent가 다음에 수행할 행동입니다. |

### Intent 정의

| 값 | 의미 | 판단 기준 |
|---|---|---|
| `schedule_lookup` | 경기 일정 조회 | 특정 날짜나 기간의 KBO 경기를 찾는 요청입니다. |
| `stadium_info` | 구장 정보 조회 | 구장의 위치, 돔 여부 등 구장 정보를 묻는 요청입니다. |
| `weather_lookup` | 경기 날씨 확인 | 특정 경기의 날씨와 관람 위험을 묻는 요청입니다. |
| `seat_recommendation` | 좌석 추천 | 경기, 날씨, 선호를 반영한 좌석 추천 요청입니다. |
| `ticketing_guide` | 예매 안내 | 예매처, 예매 방법, 티켓팅 팁을 묻는 요청입니다. |
| `logistics_guide` | 원정 동선 안내 | 출발지에서 경기장까지 이동과 복귀 동선을 묻는 요청입니다. |
| `multi_intent` | 복합 요청 | 둘 이상의 기능을 함께 요청합니다. |
| `casual_interaction` | 일반 상호작용 | 인사, 감사, Agent 기능 설명 등 Tool이 필요 없는 요청입니다. |
| `out_of_scope` | 지원 범위 밖 요청 | 야구 일반 지식이나 다른 리그 등 현재 Agent가 지원하지 않는 요청입니다. |

### 허용 값

- Tool: `find_kbo_game`, `get_stadium_info`, `get_weather_context`, `search_baseball_knowledge`, `score_seat_candidates`, `get_ticketing_guide`, `get_logistics_guide`
- `missing_fields`: `game_date`, `team`, `selected_game`, `origin_location`, `stadium`
- `next_action`: `call_tools`, `ask_clarification`, `answer_without_tools`, `reject_request`

## 데이터 생성 또는 전처리 방법

- 사용한 방식: 프로젝트의 실제 Tool 정책과 세션 구조를 기준으로 AI 합성데이터 초안을 작성하고, 각 Row를 사람이 순서대로 검수했습니다.
- 생성 규칙:
  - 각 Row에 `system`, `user`, `assistant` 메시지를 포함했습니다.
  - `assistant.content`에는 설명 없이 정답 JSON 문자열만 기록했습니다.
  - `required_tools`는 계획된 실행 순서대로 기록했습니다.
  - `selected_game`이 있으면 불필요한 일정 검색을 생략했습니다.
  - 추가 질문이 필요하면 `required_tools`를 빈 배열로 기록했습니다.
- 제외한 데이터 기준:
  - 요청 목적 자체를 식별할 수 없어 일관된 정답을 부여할 수 없는 요청
  - 현재 Agent가 지원하지 않는 기능을 정상 Intent처럼 요구하는 요청
  - 개인정보, API key, 내부 로그 원문이 포함된 요청
  - 동일한 표현과 정답이 반복되는 중복 요청

## 샘플

### 좋은 샘플

입력:

```text
사용자 요청: 2026년 5월 23일 롯데 경기 좌석 추천하고 예매 방법도 알려줘
세션 정보: {"favorite_team":"롯데","preferences":["응원","가성비"]}
```

정답:

```json
{
  "intent": "multi_intent",
  "required_tools": [
    "find_kbo_game",
    "get_stadium_info",
    "get_weather_context",
    "search_baseball_knowledge",
    "score_seat_candidates",
    "get_ticketing_guide"
  ],
  "needs_clarification": false,
  "missing_fields": [],
  "next_action": "call_tools"
}
```

좌석 추천과 예매 안내를 함께 요청한 복합 의도를 보존하고, 필요한 Tool을 의존 관계에 맞는 순서로 호출하므로 좋은 샘플입니다.

### 나쁜 샘플

```text
사용자 요청: 그거 괜찮은 걸로 알려줘
세션 정보: {}
```

나쁜 이유:

- `그거`가 가리키는 대상이 없어 요청 목적을 식별할 수 없습니다.
- 일정, 좌석, 예매, 동선 중 어떤 Intent인지 일관되게 결정할 수 없습니다.
- 검수자마다 다른 정답을 부여할 가능성이 있어 Fine-tuning Dataset에서 제외해야 합니다.

## 엣지케이스

| 번호 | 입력 요약 | 기대 출력 | 포함 이유 |
|---:|---|---|---|
| 1 | 날짜 없이 롯데 경기 좌석 추천 요청 | `game_date` 추가 질문 | 필수 정보가 부족하면 Tool을 호출하지 않는지 확인합니다. |
| 2 | 후보 경기가 여러 개인 상태에서 “그 경기”라고 요청 | `selected_game` 추가 질문 | 모호한 후보를 임의로 선택하지 않는지 확인합니다. |
| 3 | `selected_game`이 있는 상태에서 “날씨는 어때?”라고 요청 | 일정 검색 없이 구장·날씨 Tool 호출 | 세션 정보를 활용하여 불필요한 Tool 호출을 생략하는지 확인합니다. |
| 4 | 선택된 경기는 있지만 원정 출발지가 없음 | `origin_location` 추가 질문 | 경기 정보가 있어도 동선 필수 정보가 부족할 수 있음을 확인합니다. |
| 5 | 요일과 시간으로 후보 경기 선택 | 선택된 후보 기준 좌석 Tool 호출 | 자연어 표현으로 특정 후보를 식별하는지 확인합니다. |

## 품질 점검

| 항목 | 확인 결과 |
|---|---|
| 형식 일관성 | 모든 Row가 동일한 메시지 구조와 Assistant 응답 필드를 사용합니다. |
| 판단 기준 일관성 | Intent, Tool 순서, clarification 판단 기준을 계획서와 사람 검수로 확인했습니다. |
| JSON 파싱 가능 여부 | 19개 JSONL Row와 모든 `assistant.content` JSON의 파싱을 확인했습니다. |
| 엣지케이스 | 정보 부족, 후보 모호성, 세션 기반 후속 요청 등 5개 이상의 엣지케이스를 포함했습니다. |
| 개인정보 포함 여부 | 개인정보가 포함되지 않았습니다. |
| 내부정보 포함 여부 | API key, 내부 로그 원문, 비공개 정보가 포함되지 않았습니다. |
| 라이선스 확인 | 직접 작성한 AI 합성데이터로 외부 데이터 라이선스 위험이 낮습니다. |

## 자가 점검 체크리스트

- [x] Fine-tuning으로 학습시킬 행동을 한 문장으로 설명했습니다.
- [x] `messages`의 system, user, assistant 역할을 분리했습니다.
- [x] 모든 Row와 Assistant 정답 JSON의 파싱을 확인했습니다.
- [x] 엣지케이스를 최소 3개 이상 포함했습니다.
- [x] 좋은 샘플과 나쁜 샘플을 비교했습니다.
- [x] 개인정보, 내부정보, 라이선스 위험을 확인했습니다.
