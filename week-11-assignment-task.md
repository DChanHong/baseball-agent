# 11주차 실습 과제: LLM Fine-tuning Dataset 준비

## 배경

이번 주에는 Fine-tuning을 실행하지 않습니다. 대신 Fine-tuning에 쓸 수 있는 작은 텍스트 dataset 초안을 만듭니다.

Fine-tuning은 최신 지식을 모델에 외우게 하는 작업보다, 반복되는 판단과 출력 형식을 안정적으로 맞추는 데 더 잘 맞습니다.

예시는 다음과 같습니다.

- 고객 문의를 정해진 카테고리로 분류하고 JSON으로 답하기
- 뉴스나 리뷰를 정해진 schema로 구조화하기
- Agent 실행 trace를 보고 실패 원인을 분류하기
- prompt injection 위험 입력을 정해진 label로 분류하기

## 과제 목표

본인 Agent나 LLM 서비스에서 Fine-tuning 후보 작업 하나를 고르고, 작은 학습용 dataset을 만듭니다.

데이터 출처는 하나만 고르면 됩니다.

| 방식 | 설명 |
|------|------|
| AI 합성데이터 | LLM으로 예시를 만들고 직접 검수 |
| Hugging Face dataset | 공개 dataset을 가져와 목적에 맞게 재가공 |
| AI Hub dataset | AI Hub의 한국어 텍스트 dataset을 가져와 목적에 맞게 재가공 |
| 기존 로그 | 7~10주차 Agent 로그나 실패 trace를 익명화해 재가공 |

텍스트 데이터를 사용합니다. 이미지, 음성, 영상 dataset은 이번 과제 범위에서 제외합니다.

## 참고 자료

- 11주차 블로그: https://blog.aibox.today/ai-agent-llm-fine-tuning-preview/
- Hugging Face Datasets: https://huggingface.co/datasets
- AI Hub: https://www.aihub.or.kr

## 제출 방식

본 `ai-agent-repo`에 다음 경로로 제출합니다.

```text
week-11/{github-id}/README.md
week-11/{github-id}/data/dataset.jsonl
```

데이터 원본을 PR에 올릴 수 없다면 `dataset.jsonl` 대신 샘플 5개만 담은 `sample.jsonl`을 제출합니다. 이 경우 README에 원본 링크와 전처리 방법을 적습니다.

```text
week-11/{github-id}/README.md
week-11/{github-id}/data/sample.jsonl
```

## 제출 기한

PR은 늦어도 금요일 18:00 전까지 올립니다.

완성하지 못했더라도 Fine-tuning 후보 작업, schema, 샘플 일부, 막힌 지점을 README에 적어 제출합니다.

## 필수 범위

직장인이 하루 이틀 안에 끝낼 수 있는 범위로 잡았습니다.

- Fine-tuning 후보 작업 1개 선정
- Fine-tuning이 필요한 이유 2~3줄 작성
- 데이터 출처 선택
- 출력 JSON schema 또는 응답 형식 정의
- `messages` 기반 JSONL row 최소 15개 작성
- 엣지케이스 최소 3개 포함
- 좋은 샘플 1개와 나쁜 샘플 1개 비교
- 개인정보, 내부정보, 라이선스 위험 확인
- `week-11/{github-id}/README.md` 제출

선택 사항:

- 데이터 생성 prompt 첨부
- 간단한 전처리 코드 첨부
- train / validation 분리
- JSON 파싱 검증 스크립트 첨부

## Dataset 형식

기본 row는 다음 형식으로 작성합니다.

```json
{
  "messages": [
    {
      "role": "system",
      "content": "고객 문의를 읽고 category와 reply를 가진 JSON으로만 답변하라. category는 delivery, refund, complaint, product_question 중 하나를 사용하라."
    },
    {
      "role": "user",
      "content": "주문한 상품이 아직 안 왔는데 배송이 어디까지 됐나요?"
    },
    {
      "role": "assistant",
      "content": "{\"category\": \"delivery\", \"reply\": \"배송 상태를 확인해드리겠습니다.\"}"
    }
  ]
}
```

역할은 이렇게 나눕니다.

- `system`: 역할, 판단 기준, 출력 형식
- `user`: 실제 입력 텍스트
- `assistant`: 모델이 생성해야 할 정답

`assistant.content`에는 실제 서비스에서 모델이 출력해야 하는 결과만 넣습니다. 중간 추론, 설명, 데이터 생성 지시는 넣지 않습니다.

## 주제 예시

| 주제 | 출력 예시 |
|------|-----------|
| 고객 문의 분류 | `{"category": "refund", "reply": "환불 절차를 안내해드리겠습니다."}` |
| 리뷰 감성 분류 | `{"sentiment": "negative", "reason": "배송 지연"}` |
| 보안 입력 분류 | `{"risk": "prompt_injection", "action": "block"}` |
| Agent 실패 원인 분류 | `{"failure_type": "tool_error", "next_action": "retry_with_fallback"}` |
| 뉴스 구조화 | `{"is_stock_related": true, "impact": "negative", "keywords": ["파업"]}` |

최신 지식 답변, 문서 검색, 자유형 Q&A는 이번 주제로 적합하지 않습니다. 이런 문제는 Fine-tuning보다 RAG나 Prompt Engineering을 먼저 검토합니다.

## 품질 점검 기준

제출 전에는 네 가지만 확인합니다.

| 항목 | 확인할 것 |
|------|-----------|
| 형식 일관성 | 모든 row의 assistant 응답이 같은 key와 타입을 쓰는가 |
| 판단 기준 일관성 | 비슷한 입력이 서로 다른 label로 흔들리지 않는가 |
| 엣지케이스 | 애매한 입력이나 빈 값이 필요한 입력이 최소 3개 있는가 |
| 데이터 위험 | 개인정보, 내부정보, 라이선스 문제가 없는가 |

## README 템플릿

`week-11/{github-id}/README.md`에는 다음 템플릿을 사용합니다.

~~~md
# 11주차 LLM Fine-tuning Dataset 준비

## Fine-tuning 후보 작업

- 작업 이름:
- 개선하려는 행동:
- Fine-tuning이 필요한 이유:
- RAG나 Prompt Engineering이 먼저가 아닌 이유:

## Dataset 개요

- 데이터 출처: AI 합성데이터 / Hugging Face / AI Hub / 기존 로그 / 기타
- 원본 링크:
- 라이선스:
- 최종 row 수:
- 출력 형식:

## Schema

Assistant 응답 형식:

```json
{
  "category": "string",
  "reply": "string"
}
```

Label 또는 category 정의:

| 값 | 의미 | 판단 기준 |
|----|------|-----------|
| ... | ... | ... |

## 데이터 생성 또는 전처리 방법

- 사용한 방식:
- 생성 prompt 또는 전처리 규칙:
- 제외한 데이터 기준:

## 샘플

좋은 샘플:

```json
...
```

나쁜 샘플:

```json
...
```

나쁜 이유:

- ...

## 엣지케이스

| 번호 | 입력 요약 | 기대 출력 | 포함 이유 |
|------|-----------|-----------|-----------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

## 품질 점검

| 항목 | 확인 결과 |
|------|-----------|
| 형식 일관성 | |
| 판단 기준 일관성 | |
| JSON 파싱 가능 여부 | |
| 개인정보 포함 여부 | |
| 내부정보 포함 여부 | |
| 라이선스 확인 | |

~~~

## 자가 점검 체크리스트

1. Fine-tuning으로 학습시킬 행동이 한 문장으로 설명되는가
2. `messages`의 system, user, assistant 역할이 분리됐는가
3. 모든 row의 JSON이 파싱 가능한가
4. 엣지케이스가 최소 3개 포함됐는가
5. 개인정보, 내부정보, 라이선스 위험을 확인했는가
