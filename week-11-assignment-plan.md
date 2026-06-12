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

KBO 직관 가이드 Agent 다음 행동 판단

### 개선하려는 행동

사용자 요청과 현재 세션 정보를 입력으로 받았을 때, KBO 직관 가이드 Agent가 다음 행동을 일관된 JSON으로 결정하도록 개선하기 위한 목적입니다.

- 사용자 의도를 사전 정의된 카테고리 중 하나로 일관되게 분류하기 위함입니다.
- 필요한 Tool을 누락 없이, 불필요한 Tool 호출 없이, 올바른 실행 순서대로 결정하기 위함입니다.
- Tool 호출 전에 사용자에게 추가 질문이 필요한지 일관된 기준으로 판단하기 위함입니다.
- 정보가 부족할 때 어떤 필드가 부족한지 사전 정의된 이름으로 정확히 식별하기 위함입니다.
- 세션 상태(`selected_game`, `candidate_games` 등)에 따라 Tool 호출을 생략하거나 재해석하는 판단을 일관되게 내리기 위함입니다.

### Fine-tuning이 필요한 이유

현재 Agent는 Gemini가 시스템 프롬프트의 Tool 설명만 참고하여 자연어 요청을 그때그때 해석해 Tool을 선택합니다. 이 구조는 다음 세 가지 일관성 문제를 가집니다.

- **표현 의존 가변성**: 같은 의도라도 표현이 달라지면("좌석 추천해줘" vs "어디 앉아야 좋아?" vs "1루쪽 어때?") 필수 Tool을 누락하거나 불필요한 Tool을 호출할 가능성이 있습니다.
- **세션 의존 판단 누락**: 입력 문장이 동일해도 세션 상태(`selected_game`, `candidate_games` 유무)에 따라 정답 Tool 순서가 달라지는데, 이 분기를 프롬프트 규칙만으로 안정적으로 따르기 어렵습니다.
- **출력 형식 파괴 위험**: 모델이 JSON 외 설명 텍스트를 덧붙이거나 필드 이름·타입을 미묘하게 바꾸면 다운스트림 파서가 실패합니다. 프롬프트 지시만으로는 형식 안정성을 보장하기 어렵습니다.

이러한 문제는 새로운 지식이 필요한 작업이 아니라 유한한 카테고리 안에서의 반복 분류·라우팅 판단이므로, 사람이 검수한 정답 예시를 dataset으로 정의하여 학습 가능한 형태로 만드는 것이 적절한 해결책입니다.

### RAG나 Prompt Engineering이 먼저가 아닌 이유

현재 작업은 외부 문서를 검색해 답변을 생성하는 문제가 아니라, 사용자 입력과 세션 상태를 바탕으로 intent, required_tools, next_action을 일관되게 판단하는 라우팅 문제입니다. 필요한 기준은 외부 지식이 아니라 이미 정의된 tool, intent, session 규칙이므로, RAG를 구축하기보다 정답 예시를 체계적으로 수집·정리하여 Fine-tuning 및 평가에 사용할 수 있는 dataset을 만드는 것을 우선합니다.

Prompt Engineering은 기본적인 지시와 형식 제어에는 효과적이지만, 다양한 사용자 표현과 세션 상태에 따른 라우팅 판단을 항상 일관되게 보장하기는 어렵습니다. 또한 정답 dataset이 없으면 프롬프트를 수정해도 실제로 성능이 개선되었는지, 기존 케이스에 회귀가 생겼는지 측정하기 어렵습니다. 따라서 프롬프트를 계속 보완하기 전에 정답 예시를 dataset으로 정리해 판단 기준을 명확히 하고, 이를 Fine-tuning과 향후 프롬프트 개선 평가의 공통 기준으로 활용하고자 합니다.

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
| `casual_interaction` | 인사, 감사, Agent 자기 설명 등 Tool 없이 응답할 수 있는 비기능 요청 |
| `out_of_scope` | 야구 일반 지식, 다른 리그·도메인, 부적절한 요청 등 Agent가 처리할 수 없어 거절해야 하는 요청 |

### Next Action 후보

| 값 | 의미 | 선택되는 Intent | 다른 필드 제약 |
|----|------|--------------|--------------|
| `call_tools` | Intent를 처리하기 위해 `required_tools`에 명시된 Tool을 순서대로 호출합니다 | `schedule_lookup`, `stadium_info`, `weather_lookup`, `seat_recommendation`, `ticketing_guide`, `logistics_guide`, `multi_intent` | `required_tools.length >= 1`, `needs_clarification == false` |
| `ask_clarification` | 정보 부족이나 모호함으로 Tool 호출 전 사용자에게 추가 질문이 필요합니다 | 위 7종 중 정보가 부족한 경우 | `needs_clarification == true`, `missing_fields.length >= 1`, `required_tools == []` |
| `answer_without_tools` | 인사, 감사, Agent 자기 설명 등 비기능 상호작용에 대해 Tool 없이 직접 응답합니다 | `casual_interaction` | `required_tools == []`, `needs_clarification == false`, `missing_fields == []` |
| `reject_request` | 야구 일반 지식, 타 리그·도메인, 부적절·위험 요청 등 Agent가 처리할 수 없는 요청을 거절합니다 | `out_of_scope` | `required_tools == []`, `needs_clarification == false`, `missing_fields == []` |

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
