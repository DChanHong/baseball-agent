# Fine-tuning Experiment Plan

## 1. 실험 목적

이번 fine-tuning의 목적은 야구 지식을 새로 학습시키는 것이 아니라, baseball-agent가 사용자 요청을 받았을 때 다음 행동을 안정적으로 결정하도록 만드는 것이다.

모델이 학습해야 하는 핵심 출력은 다음 JSON 구조다.

```json
{
  "intent": "schedule_lookup",
  "required_tools": ["find_kbo_game"],
  "needs_clarification": false,
  "missing_fields": [],
  "next_action": "call_tools"
}
```

따라서 이번 실험은 다음 질문에 답하는 것을 목표로 한다.

- base model은 agent routing JSON을 얼마나 잘 출력하는가?
- fine-tuning 이후 JSON 형식 준수율이 좋아지는가?
- intent 분류가 더 정확해지는가?
- 필요한 도구 선택이 더 안정적으로 되는가?
- 세션 정보가 있을 때 불필요한 도구 호출을 줄이는가?
- 추가 질문이 필요한 상황을 더 잘 판단하는가?

## 2. 전체 진행 순서

```text
1. dataset.jsonl 로드
2. intent별 샘플 2개씩 평가셋 추출
3. base model 응답 저장
4. SFT/LoRA 학습
5. fine-tuned model 응답 저장
6. intent별 비교표 출력
```

학습은 전체 데이터를 한 번에 사용하고, 평가는 intent별로 나누어 분석한다. 모델의 역할은 특정 intent 전용 응답 생성이 아니라 사용자 요청을 보고 intent를 구분하는 것이므로, 여러 intent를 함께 학습시키는 방식이 더 적합하다.

## 3. 데이터셋 현황

사용 데이터셋:

```text
dataset.jsonl
```

현재 데이터셋은 OpenAI messages 형식으로 구성되어 있다.

```json
{
  "messages": [
    {
      "role": "system",
      "content": "사용자 요청과 세션 정보를 분석하여 intent, required_tools, needs_clarification, missing_fields, next_action을 가진 JSON으로만 답변하라."
    },
    {
      "role": "user",
      "content": "사용자 요청: 2026년 5월 23일 롯데 경기 일정 알려줘\n세션 정보: {}"
    },
    {
      "role": "assistant",
      "content": "{\"intent\":\"schedule_lookup\",\"required_tools\":[\"find_kbo_game\"],\"needs_clarification\":false,\"missing_fields\":[],\"next_action\":\"call_tools\"}"
    }
  ]
}
```

확인된 데이터 규모:

```text
전체 샘플 수: 124개
```

intent 분포:

```text
schedule_lookup        12
stadium_info           16
seat_recommendation    25
weather_lookup         12
ticketing_guide        13
logistics_guide        12
multi_intent           15
casual_interaction      8
out_of_scope           11
```

## 4. 평가셋 추출 전략

전체 데이터셋을 학습에 사용하기 전에, intent별 대표 샘플을 2개씩 뽑아 고정 평가셋으로 사용한다.

평가셋 목적:

- fine-tuning 전후를 같은 질문으로 비교한다.
- intent별로 어떤 유형이 개선되는지 확인한다.
- 전체 124개를 매번 추론하지 않아 비용과 시간을 줄인다.

평가셋 구성:

```text
intent 9종 x 2개 = 총 18개 샘플
```

저장 후보:

```text
week-12/eval_samples.jsonl
```

각 평가 샘플에는 다음 정보를 함께 보관한다.

```json
{
  "sample_id": "schedule_lookup_001",
  "intent": "schedule_lookup",
  "messages": [],
  "expected": {
    "intent": "schedule_lookup",
    "required_tools": ["find_kbo_game"],
    "needs_clarification": false,
    "missing_fields": [],
    "next_action": "call_tools"
  }
}
```

## 5. Base Model 테스트

사용 모델:

```text
google/gemma-4-E4B-it
```

목적:

- fine-tuning 전 모델이 기본적으로 얼마나 잘하는지 확인한다.
- 이후 fine-tuned model과 같은 입력으로 비교한다.

진행 방식:

1. 평가셋의 `messages`에서 assistant 응답을 제거한다.
2. system + user 메시지만 prompt로 사용한다.
3. base model로 응답을 생성한다.
4. 생성 결과를 파일로 저장한다.

저장 후보:

```text
week-12/results/base_model_outputs.jsonl
```

저장 형식:

```json
{
  "sample_id": "schedule_lookup_001",
  "intent": "schedule_lookup",
  "prompt": "사용자 요청: ...",
  "expected": {},
  "base_output_raw": "...",
  "base_output_parsed": {},
  "base_parse_success": true
}
```

확인 기준:

- JSON만 출력했는가?
- JSON 파싱이 가능한가?
- `intent`가 정답과 같은가?
- `required_tools`가 정답과 같은가?
- `needs_clarification` 판단이 맞는가?
- `missing_fields`가 적절한가?
- `next_action`이 맞는가?

## 6. SFT/LoRA 학습

학습 방식:

```text
Supervised Fine-tuning + LoRA adapter
```

base model:

```text
google/gemma-4-E4B-it
```

학습 결과:

```text
base model 전체를 새로 만드는 것이 아니라, base model 위에 얹는 LoRA adapter를 만든다.
```

권장 첫 실험 설정:

```python
num_train_epochs = 1
per_device_train_batch_size = 4
gradient_accumulation_steps = 12
learning_rate = 1e-4
save_steps = 100
eval_steps = 100
```

첫 연습에서는 1 epoch로 시작한다. 결과가 충분히 빠르게 나오고 개선 경향이 보이면 3 epoch로 늘려 비교한다.

저장 후보:

```text
week-12/gemma4-e4b-baseball-agent-sft
```

주의할 점:

- 현재 `dataset.jsonl`은 이미 `messages` 형식이다.
- 기존 노트북의 `system_prompt`, `user_prompt`, `assistant` 변환 코드는 그대로 쓰면 맞지 않는다.
- 데이터 로딩 셀은 `messages` 컬럼을 그대로 사용하는 방식으로 수정해야 한다.
- 학습 loss는 assistant 응답 부분에만 계산되도록 유지한다.

## 7. Fine-tuned Model 테스트

목적:

- base model 테스트와 같은 평가셋으로 fine-tuned model을 평가한다.
- fine-tuning 이후 개선 여부를 직접 비교한다.

진행 방식:

1. 저장된 LoRA adapter를 로드한다.
2. base model 테스트와 동일한 18개 평가 샘플을 사용한다.
3. system + user 메시지만 입력한다.
4. fine-tuned model 응답을 생성한다.
5. 결과를 파일로 저장한다.

저장 후보:

```text
week-12/results/fine_tuned_outputs.jsonl
```

저장 형식:

```json
{
  "sample_id": "schedule_lookup_001",
  "intent": "schedule_lookup",
  "prompt": "사용자 요청: ...",
  "expected": {},
  "fine_tuned_output_raw": "...",
  "fine_tuned_output_parsed": {},
  "fine_tuned_parse_success": true
}
```

## 8. 비교표 작성

최종 결과는 intent별 비교표로 정리한다.

비교 항목:

```text
sample_id
intent
expected_intent
base_intent
fine_tuned_intent
base_json_valid
fine_tuned_json_valid
base_required_tools_match
fine_tuned_required_tools_match
base_next_action_match
fine_tuned_next_action_match
improved
notes
```

저장 후보:

```text
week-12/results/comparison.csv
week-12/results/comparison.md
```

예상 비교표:

| intent | 질문 요약 | base model 결과 | fine-tuned 결과 | 개선 여부 |
| --- | --- | --- | --- | --- |
| schedule_lookup | 특정 날짜 롯데 경기 일정 | JSON 형식 일부 깨짐 | 정상 JSON + find_kbo_game | 개선 |
| stadium_info | 사직야구장 정보 | tool 누락 | get_stadium_info 선택 | 개선 |
| seat_recommendation | 응원석 추천 | 일부 도구 누락 | 복합 도구 선택 | 개선 |
| out_of_scope | 야구 외 요청 | 억지 답변 | out_of_scope 분류 | 개선 |

## 9. 성공 기준

이번 실험의 성공 기준은 모델 성능을 완벽하게 만드는 것이 아니라, fine-tuning 전후의 차이를 관찰 가능하게 만드는 것이다.

최소 성공 기준:

- 평가셋 18개를 고정한다.
- base model 응답을 저장한다.
- LoRA fine-tuning을 1회 수행한다.
- fine-tuned model 응답을 저장한다.
- intent별 비교표를 만든다.
- 개선된 점과 한계를 문장으로 설명한다.

정량 지표 후보:

```text
JSON parse success rate
intent accuracy
required_tools exact match rate
needs_clarification accuracy
next_action accuracy
```

정성 분석 후보:

- base model은 설명 문장을 섞어 JSON-only 지시를 어기는가?
- fine-tuned model은 출력 형식을 더 잘 지키는가?
- 복합 intent에서 필요한 도구를 빠뜨리지 않는가?
- 세션 정보가 있을 때 이미 선택된 경기 정보를 활용하는가?
- out_of_scope 요청을 도구 호출로 잘못 넘기지 않는가?

## 10. 비용 절감 전략

처음부터 전체 자동 평가를 크게 돌리지 않는다.

권장 방식:

```text
1. intent별 2개, 총 18개만 base model 테스트
2. fine-tuning은 1 epoch로 먼저 실행
3. 같은 18개 샘플만 fine-tuned model 테스트
4. 개선 경향이 보이면 epoch 또는 데이터셋을 늘린다
```

추가 절감 방법:

- 전체 124개 추론 평가는 마지막에만 수행한다.
- checkpoint 저장 주기를 너무 짧게 잡지 않는다.
- GPU 인스턴스는 학습 종료 후 바로 중지한다.
- 첫 실험에서는 hyperparameter 탐색을 하지 않는다.

## 11. 과제 보고서에 넣을 핵심 해석

이번 작업은 baseball-agent의 기능을 새로 추가하는 개발 과제라기보다, agent routing 판단을 위한 fine-tuning 실험이다.

보고서에서 강조할 내용:

- 데이터셋은 야구 답변 자체가 아니라 agent의 다음 행동 결정을 학습시키기 위한 것이다.
- fine-tuning 대상은 전체 모델이 아니라 LoRA adapter다.
- 학습은 전체 intent를 함께 사용하고, 평가는 intent별로 분리해 비교한다.
- base model과 fine-tuned model을 같은 평가셋으로 비교해 개선 여부를 판단한다.
- 작은 데이터셋이므로 절대 성능보다 실험 과정과 전후 차이 분석이 중요하다.

## 12. 다음 작업 체크리스트

- [ ] `dataset.jsonl` 로딩 코드 작성
- [ ] intent별 2개 평가셋 추출 코드 작성
- [ ] `week-12/eval_samples.jsonl` 생성
- [ ] base model 테스트 코드 작성
- [ ] `week-12/results/base_model_outputs.jsonl` 저장
- [ ] 노트북 데이터 로딩 셀을 `messages` 형식에 맞게 수정
- [ ] SFT/LoRA 1 epoch 학습 실행
- [ ] fine-tuned model 테스트 코드 작성
- [ ] `week-12/results/fine_tuned_outputs.jsonl` 저장
- [ ] 비교표 생성 코드 작성
- [ ] `week-12/results/comparison.md` 작성
- [ ] 결과 분석 문장 정리
