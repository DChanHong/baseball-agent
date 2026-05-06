# 데이터 처리 프롬프트

## 1. 경기 일정 저장 프롬프트

### 목적

KBO 공식 경기 일정 크롤링 결과를 Agent가 안정적으로 조회할 수 있는 JSON 데이터셋으로 저장한다. 이 데이터는 MVP에서 `game_data_provider` Tool의 1차 입력으로 사용되며, 이후 날씨 API와 결합해 직관 가능 여부와 좌석 추천 판단에 활용한다.

### 입력 데이터

- 출처: KBO 공식 일정/결과 페이지
- 수집 방식: 월 단위 크롤링
- 저장 위치: `data/raw/kbo_schedule_{YYYY}_{MM}.json`
- 대상 기간: MVP에서는 2026년 KBO 정규시즌 월별 일정

### 저장 원칙

1. 원본 HTML 또는 화면 텍스트를 그대로 저장하지 말고, Agent가 바로 사용할 수 있는 정규화 JSON으로 저장한다.
2. 경기 단위로 하나의 객체를 만들고, 날짜/시간/팀/구장/상태를 필수 필드로 둔다.
3. 구장명은 KBO 원문 약칭과 서비스 내부 표준명을 함께 저장한다.
4. 돔구장 여부는 경기 일정 크롤링 결과가 아니라 내부 구장 메타데이터와 결합해 저장한다.
5. 우천 취소, 경기 종료, 더블헤더 같은 상태는 `status`와 `note`에 명확히 남긴다.
6. 크롤링 실패 또는 파싱 실패 시 빈 배열을 성공처럼 저장하지 말고 실패 상태를 별도로 반환한다.

### 정규화 스키마

```json
{
  "metadata": {
    "source": "KBO Official Schedule",
    "year": 2026,
    "month": 5,
    "updated_at": "2026-05-06T12:00:00+09:00"
  },
  "games": [
    {
      "game_id": "20260515SSGLG0",
      "date": "2026-05-15",
      "time": "18:30",
      "status": "SCHEDULED",
      "teams": {
        "away": "SSG",
        "home": "LG",
        "away_score": null,
        "home_score": null
      },
      "stadium": {
        "short_name": "잠실",
        "name": "잠실야구장",
        "city": "서울",
        "is_dome": false
      },
      "broadcast": "KBS N SPORTS",
      "note": "",
      "source": {
        "name": "KBO Official Schedule",
        "url": "https://www.koreabaseball.com/Schedule/Schedule.aspx"
      }
    }
  ]
}
```

### 필수 필드

| 필드 | 설명 | MVP 사용처 |
| --- | --- | --- |
| `date` | 경기 날짜 | 사용자 요청 날짜 매칭 |
| `time` | 경기 시작 시간 | 낮/저녁 경기 판단 |
| `status` | `SCHEDULED`, `PRE_GAME`, `FINAL`, `CANCELLED` 등 | 취소/진행 가능 여부 판단 |
| `teams.home` | 홈 팀 | 대진 확인 |
| `teams.away` | 원정 팀 | 응원 팀/상대 팀 매칭 |
| `stadium.name` | 표준 구장명 | 좌석/날씨 Tool 입력 |
| `stadium.is_dome` | 돔구장 여부 | 우천/폭염 영향 판단 |

### Agent 사용 규칙

- 사용자가 날짜와 팀을 입력하면, 먼저 월별 경기 일정 JSON에서 해당 날짜와 팀이 포함된 경기를 찾는다.
- 같은 날짜에 여러 경기가 있으면 사용자의 응원 팀 또는 구장 조건으로 필터링한다.
- `status`가 `CANCELLED`이면 날씨/좌석 추천으로 진행하지 말고 취소 안내와 대안 제시로 전환한다.
- `stadium.is_dome`이 `true`이면 우천 리스크 판단을 낮추고, 좌석 추천은 시야/응원 중심으로 전환한다.
- `time`이 17시 이전이면 낮 경기로 보고 폭염/햇빛 판단을 강화한다.

### 실패 처리

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "KBO_SCHEDULE_CRAWL_FAILED",
    "message": "KBO 경기 일정을 불러오거나 정규화하지 못했습니다."
  }
}
```

### 검증 기준

- 월별 JSON에 `metadata`와 `games`가 모두 존재한다.
- 각 경기 객체에 `date`, `time`, `teams`, `stadium`, `status`가 존재한다.
- `stadium.is_dome` 값이 boolean으로 저장된다.
- 경기 취소 데이터는 `status: "CANCELLED"`로 구분된다.
- Agent가 일정 조회 후 날씨 Tool 호출 여부를 판단할 수 있다.
