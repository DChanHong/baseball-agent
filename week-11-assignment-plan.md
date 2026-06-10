# 11주차 Fine-tuning Dataset 과제 작업 계획

## 1. 과제 목표

현재 KBO 직관 가이드 Agent가 사용자 요청과 세션 정보를 바탕으로 다음 행동을 일관되게 판단하도록 Fine-tuning용 dataset을 준비한다.

- 사용자 의도 분류
- 필요한 Tool과 호출 순서 선택
- 추가 질문 필요 여부 판단
- 부족한 정보 식별

이번 과제에서는 실제 Fine-tuning을 실행하지 않는다. 사람이 검수한 정답 행동을 `messages` 기반 JSONL dataset으로 만드는 것을 목표로 한다.

## 2. Fine-tuning 후보 작업

### 작업 이름

KBO 직관 가이드 Agent의 사용자 요청 라우팅 및 Tool 선택 판단

### 개선하려는 행동

사용자 요청과 현재 세션 정보를 분석하여 의도, 필요한 Tool 순서, 추가 질문 필요 여부, 부족한 정보를 일관된 JSON으로 출력한다.

### Fine-tuning이 필요한 이유

현재 Agent는 Gemini가 자연어 요청을 직접 해석하여 Tool을 선택한다. 요청 표현이나 세션 상태에 따라 필수 Tool을 누락하거나, 불필요한 Tool을 호출하거나, 필요한 정보를 묻지 않고 실행할 가능성이 있다.

Fine-tuning용 dataset을 준비하여 올바른 Tool 선택과 추가 질문 판단 기준을 반복 가능한 정답 행동으로 정의한다.

### RAG나 Prompt Engineering이 먼저가 아닌 이유

이 작업은 최신 KBO 지식이나 외부 문서를 검색하는 문제가 아니다. 동일한 사용자 의도와 세션 조건에서 일관된 Tool 선택과 다음 행동을 결정하는 분류 및 라우팅 문제다.

현재 시스템 프롬프트에도 Tool 선택 규칙이 정의되어 있지만, 규칙을 안정적으로 따르는지 평가하고 개선하기 위한 정답 dataset이 필요하다.

## 3. 출력 Schema 초안

Assistant는 설명 없이 다음 JSON 형식으로만 응답한다.

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
|------|------|------|
| `intent` | string | 사용자의 주요 요청 의도 |
| `required_tools` | array[string] | 호출해야 하는 Tool을 실행 순서대로 기록 |
| `needs_clarification` | boolean | Tool 호출 전에 추가 질문이 필요한지 여부 |
| `missing_fields` | array[string] | 사용자 또는 세션 정보에서 부족한 필드 |
| `next_action` | string | Agent가 다음에 수행해야 하는 행동 |

### Intent 후보

| 값 | 의미 |
|----|------|
| `schedule_lookup` | 경기 일정 조회 |
| `stadium_info` | 구장 정보 조회 |
| `weather_lookup` | 경기 날씨 확인 |
| `seat_recommendation` | 좌석 추천 |
| `ticketing_guide` | 예매 안내 |
| `logistics_guide` | 원정 이동 및 동선 안내 |
| `multi_intent` | 둘 이상의 기능을 함께 요청 |
| `out_of_scope` | Agent 지원 범위 밖의 요청 |

### Next Action 후보

| 값 | 의미 |
|----|------|
| `call_tools` | 필요한 Tool 호출 시작 |
| `ask_clarification` | 부족하거나 모호한 정보를 사용자에게 질문 |
| `answer_without_tools` | Tool 없이 직접 답변 |
| `reject_request` | 지원 범위 밖 또는 위험 요청 거절 |

## 4. 현재 사용 Tool

| Tool | 역할 |
|------|------|
| `find_kbo_game` | 날짜와 팀 조건으로 KBO 경기 검색 |
| `get_stadium_info` | 구장 위치, 돔 여부, 날씨 좌표 조회 |
| `get_weather_context` | 경기 날씨와 날씨 위험 판단 |
| `search_baseball_knowledge` | 좌석, 예매, 동선 관련 RAG 근거 검색 |
| `score_seat_candidates` | 날씨, 예산, 선호 기반 좌석 순위 계산 |
| `get_ticketing_guide` | 예매처, 공식 링크, 티켓팅 팁 조회 |
| `get_logistics_guide` | 원정 이동과 당일 복귀 가능성 안내 |

## 5. 필수 범위 작업 순서

### Step 1. 후보 작업과 범위 확정

- [ ] Fine-tuning 후보 작업을 한 문장으로 확정한다.
- [ ] 학습 대상이 최신 지식이 아닌 반복 판단 행동인지 확인한다.
- [ ] 하나의 dataset에서 다룰 Intent와 Tool 범위를 확정한다.
- [ ] Fine-tuning이 필요한 이유를 2~3줄로 정리한다.
- [ ] RAG나 Prompt Engineering만으로 해결하지 않는 이유를 정리한다.

완료 기준:

- README의 `Fine-tuning 후보 작업` 항목을 작성할 수 있다.
- 학습시킬 행동을 한 문장으로 설명할 수 있다.

### Step 2. 정답 판단 규칙 정의

- [ ] Intent별 필수 입력 정보를 정의한다.
- [ ] Intent별 기대 Tool 순서를 정의한다.
- [ ] 세션에 `selected_game`이 있을 때 생략할 Tool을 정의한다.
- [ ] 세션에 `candidate_games`가 있을 때 경기 선택 판단 규칙을 정의한다.
- [ ] 정보 부족 또는 모호한 요청의 추가 질문 규칙을 정의한다.
- [ ] 여러 Intent가 함께 있는 요청의 Tool 실행 순서를 정의한다.

기본 판단 규칙:

| 상황 | 기대 행동 |
|------|-----------|
| 특정 팀의 일정 조회 | `find_kbo_game` 호출 |
| 날짜 없는 좌석 추천 | 날짜를 추가 질문 |
| 선택된 경기 기반 좌석 추천 | `find_kbo_game`을 생략하고 좌석 추천 Tool 호출 |
| 좌석 추천 | 경기, 구장, 날씨, 좌석 검색, 좌석 점수화 순서 유지 |
| 예매 안내 | 팀 또는 구장 확인 후 `get_ticketing_guide` 호출 |
| 원정 동선 안내 | 출발지, 구장, 경기 날짜와 시간 확인 |
| 여러 후보 경기가 존재 | 특정 경기 선택을 사용자에게 질문 |

완료 기준:

- 같은 입력 조건을 다시 검토해도 동일한 정답을 부여할 수 있다.

### Step 3. 출력 JSON Schema 확정

- [ ] Assistant 응답의 필수 key를 확정한다.
- [ ] 각 key의 타입을 확정한다.
- [ ] 허용 가능한 Intent 값을 확정한다.
- [ ] 허용 가능한 Tool 이름을 확정한다.
- [ ] 허용 가능한 `next_action` 값을 확정한다.
- [ ] `required_tools`가 실행 순서를 의미한다는 규칙을 명시한다.
- [ ] 추가 질문이 필요한 경우 `required_tools`를 어떻게 기록할지 확정한다.

권장 규칙:

- 추가 질문이 먼저 필요하면 `required_tools`는 빈 배열로 둔다.
- `needs_clarification`이 `true`이면 `next_action`은 `ask_clarification`이다.
- `missing_fields`에는 사전에 정의한 필드 이름만 사용한다.
- Tool 이름은 실제 등록된 이름만 사용한다.

완료 기준:

- 모든 dataset row를 하나의 schema로 검증할 수 있다.

### Step 4. 데이터 출처와 생성 방식 확정

- [ ] 데이터 출처 하나를 선택한다.
- [ ] 데이터 생성 또는 재가공 방법을 기록한다.
- [ ] 데이터 제외 기준을 정의한다.
- [ ] 개인정보, 내부정보, API key 포함 여부를 확인한다.
- [ ] 사용 데이터의 라이선스 위험을 확인한다.

권장 데이터 출처:

> AI 합성데이터를 직접 작성하고 프로젝트의 Tool 정책과 기존 요청 예시를 기준으로 사람이 검수한다.

권장 제외 기준:

- 정답 Tool 흐름을 명확히 결정할 수 없는 요청
- 현재 Agent가 지원하지 않는 기능을 정상 Intent처럼 요구하는 요청
- API key, 내부 로그 원문, 개인정보가 포함된 요청
- 동일한 표현과 정답이 반복되는 중복 데이터

완료 기준:

- README의 `Dataset 개요`와 `데이터 생성 또는 전처리 방법`을 작성할 수 있다.

### Step 5. 최소 15개 Dataset Row 작성

- [ ] `messages` 기반 JSONL row를 최소 15개 작성한다.
- [ ] 각 row에 `system`, `user`, `assistant` 메시지를 포함한다.
- [ ] `assistant.content`에는 정답 JSON 문자열만 넣는다.
- [ ] 정상 요청과 정보 부족 요청을 모두 포함한다.
- [ ] 세션 정보가 있는 후속 요청을 포함한다.
- [ ] 모든 row를 사람이 검수한다.

권장 데이터 구성:

| 구분 | 최소 개수 |
|------|-----------|
| 경기 일정 조회 | 2 |
| 좌석 추천 | 3 |
| 날씨 확인 | 2 |
| 예매 안내 | 2 |
| 원정 동선 | 2 |
| 복합 Intent | 1 |
| 정보 부족 및 모호한 요청 | 3 |
| 합계 | 15 |

Dataset row 기본 형식:

```json
{
  "messages": [
    {
      "role": "system",
      "content": "사용자 요청과 세션 정보를 분석하여 intent, required_tools, needs_clarification, missing_fields, next_action을 가진 JSON으로만 답변하라."
    },
    {
      "role": "user",
      "content": "사용자 요청: 2026년 5월 23일 롯데 경기 좌석 추천해줘\n세션 정보: {}"
    },
    {
      "role": "assistant",
      "content": "{\"intent\":\"seat_recommendation\",\"required_tools\":[\"find_kbo_game\",\"get_stadium_info\",\"get_weather_context\",\"search_baseball_knowledge\",\"score_seat_candidates\"],\"needs_clarification\":false,\"missing_fields\":[],\"next_action\":\"call_tools\"}"
    }
  ]
}
```

완료 기준:

- `dataset.jsonl`에 JSONL row가 최소 15개 존재한다.

### Step 6. 엣지케이스 최소 3개 포함

- [ ] 날짜가 없는 좌석 추천 요청을 포함한다.
- [ ] 여러 후보 경기 중 어떤 경기인지 불명확한 요청을 포함한다.
- [ ] `selected_game`이 있는 짧은 후속 요청을 포함한다.
- [ ] 필요하면 복합 Intent 또는 지원 범위 밖 요청도 추가한다.

권장 엣지케이스:

| 번호 | 입력 상황 | 기대 행동 |
|------|-----------|-----------|
| 1 | `롯데 경기 좌석 추천해줘` | 날짜 추가 질문 |
| 2 | 여러 후보 경기 이후 `두 번째 경기 좌석 알려줘` | 후보 경기 선택 후 좌석 Tool 호출 |
| 3 | `selected_game`이 있는 상태에서 `날씨는 어때?` | 일정 재검색 없이 구장·날씨 Tool 호출 |
| 4 | `서울에서 원정 가고 싶어` | 경기와 목적 구장 정보 추가 질문 |
| 5 | 좌석 추천과 예매 방법을 함께 요청 | 좌석 추천 후 예매 Tool까지 호출 |

완료 기준:

- README의 `엣지케이스` 표에 최소 3개를 설명할 수 있다.

### Step 7. 좋은 샘플과 나쁜 샘플 작성

- [ ] 좋은 샘플 1개를 선택한다.
- [ ] 같은 요청에 대한 나쁜 샘플 1개를 작성한다.
- [ ] 나쁜 샘플이 잘못된 이유를 설명한다.

좋은 샘플 기준:

- 실제 사용자 의도를 올바르게 분류한다.
- 필수 Tool을 빠뜨리지 않는다.
- 불필요한 Tool을 호출하지 않는다.
- 세션에 있는 정보를 재조회하지 않는다.
- 추가 질문 필요 여부가 올바르다.

나쁜 샘플 예시:

```json
{
  "intent": "seat_recommendation",
  "required_tools": ["search_baseball_knowledge"],
  "needs_clarification": false,
  "missing_fields": [],
  "next_action": "call_tools"
}
```

나쁜 이유:

- 경기와 구장이 확정되지 않았다.
- 날씨 정보를 확인하지 않았다.
- 좌석 후보를 점수화하는 `score_seat_candidates`가 누락됐다.

완료 기준:

- README에 좋은 샘플, 나쁜 샘플, 나쁜 이유가 기록되어 있다.

### Step 8. 품질 및 데이터 위험 점검

- [ ] 모든 JSONL row가 JSON으로 파싱되는지 확인한다.
- [ ] 모든 Assistant 응답이 같은 key와 타입을 사용하는지 확인한다.
- [ ] Intent와 Tool 이름이 허용 목록에 포함되는지 확인한다.
- [ ] `needs_clarification`과 `next_action`의 조합이 일관적인지 확인한다.
- [ ] 비슷한 입력이 서로 다른 정답으로 분류되지 않았는지 확인한다.
- [ ] 개인정보, API key, 내부정보가 포함되지 않았는지 확인한다.
- [ ] 데이터 출처와 라이선스 위험을 기록한다.

완료 기준:

- README의 품질 점검 표를 모두 작성할 수 있다.
- 자가 점검 체크리스트를 모두 통과한다.

### Step 9. 제출 파일 구성

- [ ] GitHub ID를 확인한다.
- [ ] 제출 경로에 README를 작성한다.
- [ ] 제출 경로에 dataset을 배치한다.
- [ ] 필수 범위가 모두 포함됐는지 최종 확인한다.

예상 제출 구조:

```text
week-11/{github-id}/
├── README.md
└── data/
    └── dataset.jsonl
```

완료 기준:

- 과제 문서의 필수 범위를 모두 충족한다.

## 6. 필수 범위 체크리스트

- [ ] Fine-tuning 후보 작업 1개 선정
- [ ] Fine-tuning이 필요한 이유 2~3줄 작성
- [ ] 데이터 출처 선택
- [ ] 출력 JSON schema 정의
- [ ] `messages` 기반 JSONL row 최소 15개 작성
- [ ] 엣지케이스 최소 3개 포함
- [ ] 좋은 샘플 1개와 나쁜 샘플 1개 비교
- [ ] 개인정보, 내부정보, 라이선스 위험 확인
- [ ] `week-11/{github-id}/README.md` 작성

## 7. 권장 작업 순서 요약

```text
학습 목표 확정
→ 정답 판단 규칙 정의
→ 출력 Schema 확정
→ 데이터 출처와 생성 방식 확정
→ Dataset 15개 작성
→ 엣지케이스 추가
→ 좋은 샘플과 나쁜 샘플 비교
→ 품질 및 데이터 위험 점검
→ 제출 README 작성
```

## 8. 이번 단계에서 제외할 작업

다음 작업은 필수 범위를 완료한 후 선택적으로 진행한다.

- 실제 Gemini 또는 오픈소스 LLM Fine-tuning 실행
- 기존 Agent trace 대량 생성
- train/validation dataset 분리
- 자동 JSON 검증 스크립트 작성
- 현재 Agent와 Fine-tuned 모델의 성능 비교
- 실제 Agent 라우팅 구조에 Fine-tuned 모델 연결
