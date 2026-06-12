# 좋은 샘플과 나쁜 샘플 비교

## 선정 요청

```text
사용자 요청: 2026년 5월 23일 롯데 경기 좌석 추천하고 예매 방법도 알려줘
세션 정보: {"favorite_team":"롯데","preferences":["응원","가성비"]}
```

이 요청은 좌석 추천과 예매 안내를 함께 요구합니다. 하나의 요청에서 복수 Intent를 식별하고, 공통 정보 조회 후 기능별 Tool을 올바른 순서로 선택하는지 확인할 수 있어 비교 샘플로 선정했습니다.

## 좋은 샘플

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

### 좋은 이유

- 좌석 추천과 예매 안내를 함께 요청했으므로 `multi_intent`로 정확히 분류합니다.
- 날짜와 팀 정보가 있어 추가 질문 없이 대상 경기를 검색할 수 있습니다.
- `find_kbo_game`으로 경기와 구장을 확정한 뒤 구장, 날씨, 좌석 후보, 좌석 점수화 순서로 실행합니다.
- 좌석 추천에 필요한 `score_seat_candidates`를 누락하지 않습니다.
- 경기의 홈팀 또는 구장이 확정된 후 `get_ticketing_guide`를 호출합니다.
- Tool 호출이 필요하므로 `next_action`을 `call_tools`로 지정하고, 다른 필드 제약도 일관되게 지킵니다.

## 나쁜 샘플

```text
사용자 요청: 그거 괜찮은 걸로 알려줘
세션 정보: {}
```

### 나쁜 이유

- `그거`가 가리키는 이전 대화나 세션 정보가 없어 요청 대상을 식별할 수 없습니다.
- 일정, 구장, 날씨, 좌석, 예매, 원정 동선 중 어떤 Intent인지 일관되게 결정할 수 없습니다.
- 현재 정의된 `missing_fields`는 기능별 필수 정보 부족을 표현하지만, 요청 목적 자체가 불명확한 상황을 표현하기 어렵습니다.
- 검수자마다 서로 다른 Intent와 정답 행동을 부여할 가능성이 높습니다.
- 명확한 단일 정답을 학습해야 하는 Fine-tuning Dataset에 포함하면 판단 기준의 일관성을 해칠 수 있으므로 제외해야 합니다.

## 비교 결론

좋은 샘플은 사용자 요청과 세션 정보만으로 의도, Tool 순서, 추가 질문 여부에 명확한 정답을 부여할 수 있습니다. 나쁜 샘플은 요청 목적 자체를 결정할 근거가 없어 일관된 정답 라벨을 만들 수 없습니다. 정보가 부족하더라도 부족한 필드와 기대 행동을 명확히 정의할 수 있는 요청은 엣지케이스로 포함하고, 정답 기준 자체가 흔들리는 요청은 Dataset에서 제외합니다.
