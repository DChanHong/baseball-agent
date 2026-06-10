# 11주차 Fine-tuning 참고 내용 정리

## 문서 목적

이 문서는 11주차 Fine-tuning 사전 학습 내용을 프로젝트에 적용하기 전에 검토하기 쉽도록 다시 정리한 자료입니다.

핵심 메시지는 다음과 같습니다.

> Fine-tuning은 최신 지식을 모델에 주입하는 방법이라기보다, 반복되는 판단 기준과 출력 행동을 안정적으로 학습시키는 방법에 가깝다.

---

## 참고 링크

### 과제 및 데이터 소스

- [11주차 블로그: LLM Fine-tuning Preview](https://blog.aibox.today/ai-agent-llm-fine-tuning-preview/)
- [Hugging Face Datasets](https://huggingface.co/datasets)
- [AI Hub](https://www.aihub.or.kr/)
- 프로젝트 과제 안내: [`week-11-assignment-task.md`](../week-11-assignment-task.md)

### Tokenization 및 Chat Template

- [OpenAI Tokenizer](https://platform.openai.com/tokenizer)
- [Hugging Face Tokenizer 문서](https://huggingface.co/docs/transformers/main_classes/tokenizer)
- [Hugging Face Chat Template 문서](https://huggingface.co/docs/transformers/chat_templating)
- [Hugging Face TRL SFTTrainer 문서](https://huggingface.co/docs/trl/sft_trainer)

### 주요 학습 방법 및 논문

- [Domain-Adaptive 및 Task-Adaptive Pre-training 논문](https://arxiv.org/abs/2004.10964)
- [InstructGPT: 사람의 피드백을 활용한 지시 따르기 학습](https://arxiv.org/abs/2203.02155)
- [DPO: Direct Preference Optimization](https://arxiv.org/abs/2305.18290)
- [LoRA: Low-Rank Adaptation](https://arxiv.org/abs/2106.09685)

---

## 1. 전체 개요

지금까지 프로젝트에서 사용한 RAG, Advanced RAG, AI Agent는 주로 모델의 가중치를 바꾸지 않고 모델 외부의 입력과 시스템 구조를 개선하는 접근입니다. 최신 문서 검색, 외부 도구 호출, 추가 문맥 제공에는 이런 방식이 적합합니다.

그러나 모든 문제를 RAG나 Prompt Engineering만으로 안정적으로 해결할 수 있는 것은 아닙니다. 같은 입력을 항상 같은 기준으로 분류하거나, 정해진 JSON schema를 지키거나, 일관된 말투와 업무 절차를 유지해야 하는 경우에는 Fine-tuning을 검토할 수 있습니다.

Fine-tuning을 준비하려면 Pre-training과 Post-training의 차이뿐 아니라, 실제 학습 데이터가 처리되는 방식인 Tokenization, Chat Template, Assistant Label Masking을 이해해야 합니다.

---

## 2. Pre-training

Pre-training은 모델이 대규모 텍스트, 코드, 이미지 데이터에서 기본 패턴과 지식을 익히는 단계입니다. 언어 생성 능력, 일반 지식, 기초 추론 능력은 주로 이 단계에서 형성됩니다. 비용과 시간이 많이 들기 때문에 일반적으로 foundation model 또는 base model을 만들 때 사용합니다.

### Pre-training 유형

| 유형 | 설명 | 주요 목적 |
|------|------|-----------|
| Pre-training | 대규모 데이터로 base model을 처음 학습 | 일반 언어 능력과 지식 형성 |
| Continued Pre-training | 기존 base model에 추가 데이터를 학습 | 지식과 표현 보강 |
| Domain-Adaptive Pre-training, DAPT | 법률, 의료, 금융 등 특정 도메인 데이터로 추가 학습 | 도메인 용어와 문맥 이해 향상 |
| Task-Adaptive Pre-training, TAPT | 특정 작업과 가까운 입력 데이터로 추가 학습 | 분류, 검색, 요약 등 작업 관련 패턴 보강 |

Pre-training은 모델이 `환불`, `배송`, `불만`, `요청` 같은 표현의 일반적인 의미와 문맥을 이해하게 만드는 과정에 가깝습니다.

---

## 3. Post-training

Post-training은 이미 만들어진 base model을 실제 사용 목적에 맞게 다듬는 단계입니다. 모델이 지시를 잘 따르도록 만들고, 답변 형식, 스타일, 안전성, 특정 작업 수행 능력을 조정합니다.

### Post-training 유형

| 유형 | 설명 | 주요 목적 |
|------|------|-----------|
| Supervised Fine-tuning, SFT | 입력과 정답 응답 예시를 학습 | 원하는 형식과 행동 모방 |
| Instruction Tuning | 다양한 지시문과 응답 예시를 학습 | 사용자 명령 수행 능력 향상 |
| Fine-tuning | 특정 작업, 말투, 출력 형식에 맞게 조정 | 반복 행동의 안정성 향상 |
| Preference Tuning | 좋은 답변과 덜 좋은 답변의 차이를 학습 | 품질, 선호도, 안전성 조정 |
| RLHF | 사람의 피드백으로 보상 모델을 만들고 모델을 조정 | 사람의 선호와 안전 기준 반영 |
| RLAIF | 사람 대신 AI 피드백을 활용 | 피드백 비용 절감 |
| DPO | 선호 응답과 비선호 응답 쌍을 직접 학습 | 비교적 단순한 선호 학습 |
| Safety Alignment | 위험하거나 유해한 응답을 줄이도록 학습 | 정책 준수와 안전한 응답 |

예를 들어 `환불하고 싶어요`라는 문장을 고객지원 업무 기준의 `refund` 카테고리로 분류하거나, 모든 답변을 존댓말로 생성하게 만드는 작업은 Post-training에 해당합니다.

---

## 4. Fine-tuning의 목적

Fine-tuning은 Post-training 안에서 특정 작업, 말투, 응답 규칙을 학습시키는 방법입니다. 새로운 사실을 대량으로 외우게 하기보다, 모델이 이미 이해하고 있는 내용을 정해진 방식으로 판단하고 출력하게 만드는 데 적합합니다.

### Fine-tuning에 적합한 행동

- 입력을 정해진 카테고리로 분류하기
- 답변을 항상 동일한 JSON schema로 출력하기
- 서비스에 맞는 말투를 유지하기
- 긍정, 부정, 중립을 같은 기준으로 판단하기
- 특정 업무 절차에 따라 응답 순서를 지키기

따라서 Fine-tuning의 목표는 `모델이 무엇을 알게 할 것인가`보다 `모델이 반복적으로 어떻게 행동하게 할 것인가`로 정의하는 편이 좋습니다.

---

## 5. Tokenization

Tokenization은 텍스트를 모델이 처리할 수 있는 token 단위로 나누는 과정입니다. 같은 문장도 tokenizer에 따라 token 수가 달라질 수 있으며, token 수가 많아지면 연산량과 비용도 증가합니다.

모델이 한 번에 입력받고 출력할 수 있는 token 범위를 context length 또는 context window라고 합니다. Fine-tuning 데이터도 최종적으로 token으로 변환되므로, 사람이 읽기 좋은 문서가 아니라 모델이 반복해서 볼 `입력과 정답의 묶음`으로 설계해야 합니다.

---

## 6. Chat Template

Chat Template은 `system`, `user`, `assistant` 메시지 목록을 모델이 읽을 수 있는 하나의 문자열로 변환하는 규칙입니다.

```json
[
  {
    "role": "system",
    "content": "당신은 친절하고 정확한 인공지능 어시스턴트입니다."
  },
  {
    "role": "user",
    "content": "은행의 기준 금리를 설명해줘."
  }
]
```

실제 학습과 추론에서는 이 메시지가 모델별 special token 규칙에 맞춰 하나의 텍스트로 변환됩니다. 모델마다 사용하는 turn token과 형식이 다르므로, Fine-tuning 대상 모델의 Chat Template을 먼저 확인해야 합니다.

데이터가 `messages` 구조로 잘 작성되어 있어도 대상 모델의 Chat Template과 맞지 않으면 학습 품질이 저하될 수 있습니다.

---

## 7. Assistant Label Masking

SFT에서는 모델이 `system`과 `user` 메시지를 입력 조건으로 보고 `assistant` 응답을 생성하도록 학습합니다.

| 메시지 구간 | 학습에서의 역할 |
|-------------|-----------------|
| system | 역할, 출력 규칙, 판단 기준을 제공하는 입력 |
| user | 분류하거나 처리해야 할 실제 입력 |
| assistant | 모델이 생성해야 하는 정답 |

Assistant Label Masking은 `system`과 `user` 구간을 손실 계산에서 제외하고, `assistant` 응답만 학습 대상으로 남기는 처리입니다.

이 방식을 사용하면 모델은 대화 전체를 정답처럼 외우는 대신, 주어진 지시와 입력에 맞는 assistant 응답을 생성하는 패턴을 학습합니다.

---

## 8. Fine-tuning 데이터 설계

Fine-tuning에서 가장 중요한 일은 모델에게 반복해서 보여줄 행동을 정하는 것입니다. LoRA의 `r`, `alpha`, `target_modules` 같은 학습 설정도 중요하지만, 데이터 형식과 판단 기준이 흔들리면 원하는 결과를 얻기 어렵습니다.

기본 학습 row는 다음과 같은 `messages` 구조로 만들 수 있습니다.

```json
{
  "messages": [
    {
      "role": "system",
      "content": "모델이 따라야 할 역할, 출력 형식, 판단 기준"
    },
    {
      "role": "user",
      "content": "실제 사용자가 입력할 질문이나 문장"
    },
    {
      "role": "assistant",
      "content": "모델이 생성해야 하는 정답 응답"
    }
  ]
}
```

JSONL에서는 `assistant.content`가 문자열로 저장되는 경우가 많습니다. 구조화 출력을 학습시킬 때는 따옴표, 중괄호, 리스트, 빈 값이 실제 저장 파일에서도 올바르게 유지되는지 검증해야 합니다.

assistant 응답에는 실제 서비스가 최종적으로 필요로 하는 결과만 포함해야 합니다. 불필요한 reasoning, 중간 생각, 데이터 생성 지시가 포함되면 모델이 그 내용까지 출력 행동으로 학습할 수 있습니다.

---

## 9. 데이터 설계 예시

### 고객 문의 분류

고객 문의 분류는 모델이 이미 알고 있는 `배송`, `환불`, `불만` 등의 의미를 업무 기준에 맞는 카테고리와 JSON 응답으로 변환하도록 학습하는 예시입니다.

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

이 데이터는 업무 카테고리 판단, 고정된 JSON 형식, 일관된 고객 응답 톤을 함께 학습시킵니다.

### 금융 뉴스 구조화

금융 뉴스 구조화 예시는 복잡한 지시, 긴 사용자 입력, 구조화된 assistant 응답을 하나의 학습 row로 묶는 방식을 보여줍니다.

중요한 것은 뉴스 자체보다 역할 구분입니다. `system`에는 판단 기준과 출력 schema를 넣고, `user`에는 실제 입력을 넣으며, `assistant`에는 서비스에서 필요한 최종 결과만 넣습니다.

---

## 10. 좋은 학습 데이터의 기준

### 형식 일관성

모든 샘플은 같은 key, 타입, 출력 구조를 사용해야 합니다. 어떤 샘플은 `category`, 다른 샘플은 `type`을 사용하면 모델은 두 형식을 모두 가능한 정답으로 학습할 수 있습니다.

```json
{"category": "delivery", "reply": "배송 상태를 확인해드리겠습니다."}
```

Fine-tuning에서는 형식 자체도 모델이 배워야 하는 행동입니다.

### 판단 기준 일관성

같은 의미의 입력은 같은 기준으로 분류되어야 합니다. 하나의 입력이 여러 카테고리에 해당할 수 있다면 우선순위 규칙을 먼저 정의해야 합니다.

예를 들어 배송 지연에 대한 불만이 포함되어 있더라도, 사용자의 핵심 요청이 환불이라면 `refund`로 분류한다는 식의 반복 가능한 기준이 필요합니다.

### 엣지케이스 포함

쉬운 예시만으로는 실제 서비스의 판단 경계를 학습하기 어렵습니다. 다음과 같은 엣지케이스를 포함해야 합니다.

- 여러 카테고리에 동시에 해당하는 입력
- 핵심 의도가 간접적으로 표현된 입력
- 판단하기 어려운 짧거나 모호한 입력
- 빈 문자열이나 빈 리스트를 반환해야 하는 입력
- 관련 대상이 없거나 도구 실행이 불필요한 입력

엣지케이스는 모델이 실제 서비스에서 자주 흔들리는 경계를 배우도록 돕습니다.

---

## 11. Fine-tuning 선택 기준

### Fine-tuning을 검토하기 좋은 경우

- 같은 작업을 반복적으로 수행해야 하는 경우
- 출력 형식이 자주 깨지는 경우
- 카테고리 판단 기준을 일관되게 유지해야 하는 경우
- 서비스 말투나 응답 패턴을 유지해야 하는 경우
- prompt가 너무 길어지고 few-shot 예시 유지 비용이 커지는 경우

### 다른 방법을 먼저 검토할 경우

| 요구사항 | 우선 검토할 방법 |
|----------|------------------|
| 최신 정보나 외부 문서 참조 | RAG |
| 간단한 지시 개선으로 해결 가능 | Prompt Engineering |
| 외부 작업 실행과 단계별 판단 | Agent 및 Tool 설계 |
| 정답 기준이 합의되지 않음 | 데이터 및 정책 기준 정리 |
| 학습 후 평가 기준이 없음 | 평가 dataset과 metric 설계 |

Fine-tuning은 모델을 무조건 더 똑똑하게 만드는 방법이 아닙니다. 정답 행동을 데이터로 정리하고, 그 행동을 더 안정적으로 따르게 만드는 방법입니다.

---

## 12. 현재 프로젝트에 적용할 때의 관점

이 프로젝트는 KBO 일정, 구장, 날씨, 좌석, 예매, 이동 정보를 Tool과 RAG로 조회합니다. 이 정보들은 변경 가능성이 있거나 외부 데이터 조회가 필요하므로 Fine-tuning으로 학습시키기보다 현재의 Tool 및 RAG 구조를 유지하는 편이 적합합니다.

반면, 기존 관측 로그에 기록된 Agent 실행 결과를 일정한 기준으로 분류하는 작업은 Fine-tuning 후보로 적합합니다. 프로젝트에 이미 정상 실행 trace와 실패 trace가 있고, 반복 가능한 출력 schema를 정의하기 쉽기 때문입니다.

### 추천 후보 작업

**Agent 실행 trace를 읽고 실패 원인과 다음 조치를 구조화된 JSON으로 분류하기**

예상 assistant 출력:

```json
{
  "failure_type": "game_not_found",
  "failed_tool": "find_kbo_game",
  "next_action": "ask_for_another_date",
  "retryable": false
}
```

이 작업은 최신 KBO 지식을 모델에 외우게 하는 것이 아니라, trace를 정해진 운영 기준에 따라 일관되게 분류하는 행동을 학습시킵니다. 또한 프로젝트의 기존 observability 자료를 익명화해 데이터로 재활용할 수 있습니다.

### 적용 전 결정할 사항

1. Fine-tuning으로 안정화할 행동을 한 문장으로 정의한다.
2. 출력 JSON schema와 허용 label을 확정한다.
3. 여러 실패 원인이 함께 나타날 때의 우선순위를 정한다.
4. 정상, 실패, 모호한 trace를 포함해 최소 15개 row를 만든다.
5. 엣지케이스를 최소 3개 포함한다.
6. JSON 파싱, key, 타입, label 유효성을 자동 검증한다.
7. 개인정보, API key, 내부정보가 제거됐는지 확인한다.

---

## 핵심 정리

- Pre-training은 모델의 기본 지식과 언어 능력을 형성합니다.
- Post-training은 모델이 실제 목적에 맞게 말하고 행동하도록 조정합니다.
- Fine-tuning은 새로운 지식 주입보다 반복 행동과 출력 규칙 안정화에 적합합니다.
- 학습 데이터에서는 Chat Template과 Assistant Label Masking을 확인해야 합니다.
- 좋은 데이터는 형식, 판단 기준, 엣지케이스가 일관되어야 합니다.
- 현재 프로젝트에서는 KBO 지식 자체보다 Agent trace 실패 원인 분류가 Fine-tuning 후보로 더 적합합니다.
