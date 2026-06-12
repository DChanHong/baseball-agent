# 11주차 과제 진행 상태 및 다음 작업 인수인계

> 작성일: 2026-06-12
> 목적: 세션이 초기화되어도 새 세션이 이 문서만 읽으면 이어서 작업할 수 있도록 함

---

## 1. 현재 상태 한눈에

- **단계**: 사전 기획 완료 → 실제 산출물 생성 직전
- **확정 산출물**: `week-11-assignment-plan.md` (계획서, 모든 schema·규칙·예시 확정)
- **남은 산출물**: `week-11/{github-id}/data/dataset.jsonl`, `week-11/{github-id}/README.md`

---

## 2. 확정된 사전 기획 요약

세부 내용은 `week-11-assignment-plan.md`에 있습니다. 아래는 핵심만 요약.

### 2-1. 작업 정의 (계획서 2절)

- **작업 이름**: KBO 직관 가이드 Agent 다음 행동 판단
- **개선 목적**: 사용자 요청 + 세션 정보를 받아 의도 분류 / Tool 순서 결정 / 추가 질문 판단 / 부족 필드 식별 / 세션 활용 판단 다섯 가지를 일관된 JSON으로 출력
- **Fine-tuning 필요 이유** (3가지 일관성 문제):
  1. 표현 의존 가변성
  2. 세션 의존 판단 누락
  3. 출력 형식 파괴 위험
- **RAG/Prompt Engineering이 먼저 아닌 이유**:
  - RAG: 검색할 외부 지식이 없음 (Tool·Intent·세션 키는 모두 시스템 프롬프트 내부)
  - PE: 이미 하고 있으나 측정 도구(정답 dataset) 없이는 천장에 부딪힘

### 2-2. 출력 Schema (계획서 3절)

JSON 5개 필드:

| 필드 | 타입 | 핵심 규약 |
|------|------|----------|
| `intent` | string | Intent 9종 enum |
| `required_tools` | array[string] | 등록된 Tool 7종 이름만, 배열 순서 = 실행 순서, 계획된 happy path 시퀀스 (runtime 분기는 다음 턴에서 재결정) |
| `needs_clarification` | boolean | true면 `next_action == ask_clarification`, `missing_fields.length >= 1`, `required_tools == []` |
| `missing_fields` | array[string] | enum 5종만 |
| `next_action` | string | 4종 enum |

**Intent 9종**:
`schedule_lookup`, `stadium_info`, `weather_lookup`, `seat_recommendation`, `ticketing_guide`, `logistics_guide`, `multi_intent`, `casual_interaction`, `out_of_scope`

**Next Action 4종 + 매핑**:
- `call_tools` → 7개 기능 Intent에서, `required_tools.length >= 1`
- `ask_clarification` → 정보 부족 시
- `answer_without_tools` → `casual_interaction`
- `reject_request` → `out_of_scope`

**missing_fields enum 5종**:
`game_date`, `team`, `selected_game`, `origin_location`, `stadium`

### 2-3. Tool 7종 (계획서 4절, 변경 없음)

`find_kbo_game`, `get_stadium_info`, `get_weather_context`, `search_baseball_knowledge`, `score_seat_candidates`, `get_ticketing_guide`, `get_logistics_guide`

### 2-4. Dataset 구성 (계획서 5절)

- **최소 row 수: 17개** (과제 기준 15개 충족, casual_interaction·out_of_scope 학습 신호 확보 위해 +2)
- **데이터 출처**: AI 합성데이터 + 사람 검수
- **카테고리별 분포**:

  | 구분 | 최소 개수 |
  |------|-----------|
  | `schedule_lookup` | 2 |
  | `seat_recommendation` | 3 |
  | `weather_lookup` | 2 |
  | `ticketing_guide` | 2 |
  | `logistics_guide` | 2 |
  | `multi_intent` | 1 |
  | `casual_interaction` | 1 |
  | `out_of_scope` | 1 |
  | 정보 부족 및 모호한 요청 (`needs_clarification == true`) | 3 |
  | 합계 | 17 |

- **필수 엣지케이스 7개**: 계획서 Step 6 표 참조 (날짜 누락 좌석 추천, 후보 경기 모호, 세션 활용 후속 요청, 출발지 누락 원정, 복합 Intent, 인사·잡담, 야구 일반 지식)

### 2-5. Step 2 기본 판단 규칙 표 (계획서 5절 Step 2)

확장된 11행 표가 계획서에 있음. dataset row를 라벨링할 때 이 표가 정답의 기준.

---

## 3. 다음 작업: 실제 산출물 생성

### 3-1. 제출 구조

```
week-11/{github-id}/
├── README.md
└── data/
    └── dataset.jsonl
```

### 3-2. 산출물 1: `dataset.jsonl`

- 17개 row를 JSONL 형식으로 작성
- 각 row 한 줄 = 한 JSON 객체:
  ```
  {"messages": [
    {"role": "system", "content": "<schema 지시>"},
    {"role": "user", "content": "사용자 요청: ...\n세션 정보: {...}"},
    {"role": "assistant", "content": "<minified JSON 정답>"}
  ]}
  ```
- `system` 메시지 표준 문구는 계획서 Step 5 예시 참조
- `user` 메시지는 두 줄 형식 ("사용자 요청: ..." + "세션 정보: ...")
- `assistant` 메시지는 minified JSON 한 줄, 설명 없음

### 3-3. 산출물 2: `README.md`

- 과제 문서(`week-11-assignment-task.md`)의 README 템플릿 그대로 사용
- 계획서 1~4절 내용을 70% 재활용 가능
- 추가로 채워야 할 항목:
  - Dataset 개요 (row 수, 출처, 라이선스)
  - 좋은 샘플 1개 / 나쁜 샘플 1개 + 나쁜 이유 (Step 7)
  - 엣지케이스 표 (계획서 Step 6 그대로 옮기기)
  - 품질 점검 결과 (Step 8)

---

## 4. 다음 세션 시작 시 결정해야 할 3가지

### ① GitHub ID
디렉토리 이름 `week-11/{github-id}/`에 들어갈 ID 확정 필요.

### ② 작업 순서
- **A**: dataset.jsonl 먼저 → README.md 나중 (권장: row 작성 중 발견되는 빈틈을 README 작성 전 schema에 반영)
- **B**: README.md 먼저 → dataset.jsonl 나중

### ③ Row 작성 진행 방식
- **C**: 카테고리별 점진 작성 (1카테고리씩 토론하며 진행)
- **D**: 한 번에 17개 초안 → 통째로 검토
- **E**: 카테고리별 첫 row만 깊이 토론 → 나머지 패턴 따라가기 (권장: 토론 깊이와 속도 균형)

---

## 5. Row 작성 전 1회 확인 필요

`week-11-assignment-plan.md` 4절의 Tool 이름 7종이 **실제 Agent 코드의 Tool registry와 정확히 일치**하는지 한 번 grep으로 확인. 한 글자라도 다르면 모델이 출력하는 `required_tools`가 런타임에서 실패함.

확인 명령 예시:
```bash
grep -rn "find_kbo_game\|get_stadium_info\|get_weather_context\|search_baseball_knowledge\|score_seat_candidates\|get_ticketing_guide\|get_logistics_guide" --include="*.py"
```

---

## 6. 참고 파일 목록

| 파일 | 역할 |
|------|------|
| `week-11-assignment-task.md` | 원본 과제 정의 (수정 금지) |
| `week-11-assignment-plan.md` | 확정된 사전 기획 (모든 schema·규칙·예시) |
| `week-11-handoff.md` | 이 문서 (진행 상태 인수인계) |

---

## 7. 최근 커밋 흐름 (계획서 다듬기)

```
ea892a1 docs: cover new intents in Step 6 edge case examples
381e3c2 docs: align dataset composition table with 9 intents
72665cf docs: extend judgment rules and define missing_fields enum
c4f60f5 docs: split out_of_scope intent and enrich next_action table
fc6e758 docs: clarify why RAG and prompt engineering come second
0ffcea9 docs: refine week 11 fine-tuning task scope
689a029 docs: add week 11 fine-tuning assignment plan
```

---

## 8. 다음 세션 시작 프롬프트 예시

> "`week-11-handoff.md`와 `week-11-assignment-plan.md`를 읽고, dataset.jsonl 작성을 시작하자. GitHub ID는 `<여기 입력>`, 작업 순서 A, 진행 방식 E로 간다."

이 한 줄만 보내면 새 세션이 이어서 작업 가능합니다.
