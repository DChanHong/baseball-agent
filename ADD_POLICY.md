# 추가 정책 메모

## 2026-05-06 날씨 예보 범위별 좌석 추천 정책

### 배경

야구 직관 좌석 추천은 경기 날짜가 가까울수록 날씨 데이터를 적극 반영할 수 있지만, 먼 미래 경기에는 정확한 경기 시간대 예보를 사용할 수 없다. 따라서 날씨 API 조회 가능 범위에 따라 추천 모드를 분리한다.

### 정책

| 경기 날짜 범위 | 사용 데이터 | 추천 모드 | 처리 방식 |
| --- | --- | --- | --- |
| 오늘 ~ 3일 뒤 | 기상청 단기예보/초단기예보 | `weather_based` | 경기 시간대 날씨를 기준으로 우천, 폭염, 바람 리스크를 판단하고 좌석을 추천한다. |
| 4일 뒤 ~ 10일 뒤 | 기상청 중기예보 | `weather_risk_based` | 오전/오후 단위 날씨 경향만 참고하고, 리스크 완화 좌석을 추천한다. 경기 시간대 정확 예보가 아님을 안내한다. |
| 11일 이후 | 날씨 예보 미사용 | `preference_based` | 날씨 기반 추천을 하지 않고, 응원 열기/시야/가격/원정팬/음식 접근성/초보자 편의 등 사용자 성향 기반으로 좌석을 추천한다. |

### Tool 응답 정책

`stadium_env_expert` 또는 별도 `weather_provider`는 날씨 조회 실패와 예보 범위 초과를 구분한다. 11일 이후 경기는 실패가 아니라 정상 응답으로 처리하고, 아래 상태를 반환한다.

```json
{
  "forecast_level": "unavailable",
  "forecast_reliability": "none",
  "recommendation_mode": "preference_based"
}
```

### Agent 동작

1. `game_data_provider`로 경기 날짜, 시간, 구장, 돔 여부를 조회한다.
2. 경기 날짜와 오늘 날짜의 차이를 계산한다.
3. 날짜 차이에 따라 날씨 조회 모드를 결정한다.
4. 돔구장인 경우 우천 리스크를 낮게 보고, 오픈 구장인 경우 우천/폭염/바람 리스크를 좌석 추천에 반영한다.
5. 예보 범위가 11일을 넘으면 날씨 Tool에 의존하지 않고 성향 기반 좌석 추천으로 전환한다.

## 2026-05-06 MVP 구현 범위 확정 메모

### 목표

최소 Agent MVP는 6주차 설계서의 Must-have 중 아래 3개 기능을 우선 제대로 구현한다. 모든 기능을 한 번에 실시간 API로 완성하기보다, 핵심 판단이 필요한 부분은 실데이터를 사용하고 변동성이 크거나 범위가 큰 부분은 정적 데이터 또는 mock/rule 기반으로 처리한다.

### 포함 기능

| 기능 | 구현 방식 | 데이터 기준 |
| --- | --- | --- |
| 경기 및 날씨 기반 자동 좌석 추천 | Plan-and-Execute | KBO 일정 실데이터, 기상청 날씨 API, 구장/좌석 static rule |
| 원정 팬 맞춤 동선 설계 | ReAct | 출발지/구장별 이동 시나리오 static 또는 mock rule |
| 티켓 예매 일정 및 가이드 | ReAct | 팀별 예매처 static, 예매 난이도 rule, 예매 오픈 일시는 mock 또는 안내 수준 |

### 2차 목표 (MVP 이후 고도화)

MVP 3개 기능과 같은 도메인을 다루지만, MVP에서는 static/mock으로 처리하고 실시간화는 2차 확장에서 진행한다.

- 교통 실시간 API: MVP #2 "원정 팬 동선"이 static/mock rule로 다루는 영역의 실시간 버전.
- 예매처 실시간 크롤링: MVP #3 "티켓 예매 가이드"가 static + mock으로 다루는 영역의 실시간 버전.

### 추가로 준비할 데이터

| 파일 | 목적 |
| --- | --- |
| `data/static/team_aliases.json` | 사용자 입력 팀명과 KBO 일정 팀명 매칭 |
| `data/static/stadium_seat_guides.json` | 구장별 좌석 추천 rule 저장 |
| `data/static/ticketing_guides.json` | 팀별 예매처, 예매 난이도, 티켓팅 팁 저장 |
| `data/static/logistics_guides.json` | 출발지별 원정 동선, 막차 리스크, 대안 시나리오 저장 |

### 구현 순서

1. 팀명 alias 데이터 작성
2. 경기 일정 조회 Tool 구현
3. 구장 메타데이터 매칭 Tool 구현
4. 날씨 조회 Tool 구현
5. 구장별 좌석 추천 rule 작성 및 Tool 구현
6. 티켓 예매 가이드 static 데이터 및 Tool 구현
7. 원정 동선 static/mock 데이터 및 Tool 구현
8. Agent loop에서 3개 Must-have 흐름을 연결한다.

## 2026-05-07 Workflow/RAG vs Agent 영역 구분

### 배경

MVP 3개 기능을 구현할 때, 결정 흐름을 사전에 고정할 수 있는 부분은 Workflow 또는 RAG로 처리하고, 상황 의존적 판단·재계획·되묻기가 필요한 부분만 Agent loop로 처리한다. 두 영역을 명확히 분리해야 Agent의 책임 범위가 비대해지지 않는다.

### Workflow/RAG 영역

정형 처리 또는 검색 기반 응답으로 충분한 작업.

| 항목 | 처리 방식 | MVP 매핑 |
| --- | --- | --- |
| 티켓 예매처 안내 | Workflow + static | MVP #3 티켓 예매 가이드 |
| 구장 좌석 정보 조회 | RAG + static rule | MVP #1 좌석 추천의 후보 좌석 후처리 |
| 기본 직관 일정 생성 | Workflow | MVP #1, #3에서 일정·날짜 정렬 |

### Agent 영역

상황 판단, 재계획, 사용자 확인이 필요한 작업. Plan-and-Execute 또는 ReAct 루프에서 처리한다.

| 항목 | 처리 방식 | MVP 매핑 |
| --- | --- | --- |
| 우천/폭염 대응 | Plan-and-Execute | MVP #1 (날씨 정책의 weather_based / weather_risk_based 모드) |
| 돔구장 여부에 따른 직관 판단 | Plan-and-Execute | MVP #1 (Agent 동작 4번) |
| 막차 부족 시 동선 재계획 | ReAct | MVP #2 원정 동선 |
| 경기 취소 / Tool 실패 시 대안 제시 | Plan-and-Execute + ReAct | MVP 공통 (resilience) |
| 입력 정보 부족 시 사용자에게 되묻기 | Agent loop 공통 | MVP 공통 (HCI) |
