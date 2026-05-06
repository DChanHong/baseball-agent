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

## 2. 구장 정적 메타데이터 저장 프롬프트

### 목적

KBO 경기 일정 데이터에 포함된 구장 약칭을 Agent가 실제 판단에 사용할 수 있는 표준 구장 정보로 확장한다. 이 데이터는 크롤링 데이터가 아니라, MVP 구현을 위해 수동으로 정리한 정적 데이터이며 `stadium_metadata_provider`, `weather_provider`, `seat_recommender`의 공통 참조 데이터로 사용한다.

### 입력 데이터

- 데이터 성격: 수동 정리한 static seed
- 저장 위치: `data/static/stadium_metadata.json`
- 대상 구장: KBO 1군 경기에서 사용하는 9개 구장
- 포함 범위: 구장명, 홈팀, 돔 여부, 주소, 위도/경도, 기상청 격자, 수용인원, 예매처 기본값

### 저장 원칙

1. 이 파일에는 크롤링으로 가져온 구단 사무실 주소나 홈페이지 정보를 저장하지 않는다.
2. Agent 판단에 필요한 구장 단위 정보만 저장한다.
3. `id`는 코드에서 안정적으로 참조할 수 있는 영문 slug로 저장한다.
4. `short_name`은 KBO 일정 크롤링 결과의 구장 약칭과 매칭할 수 있어야 한다.
5. `is_dome`은 우천/폭염 판단 분기의 핵심 필드이므로 반드시 boolean으로 저장한다.
6. `coordinates`는 카카오 API를 호출하지 않고 고정 위도/경도 값을 수동 저장한다.
7. `weather_grid`는 기상청 단기예보 API 호출에 바로 사용할 수 있도록 `nx`, `ny`로 저장한다.
8. `ticketing`은 MVP에서 예매처 안내용 기본값으로만 사용하고, 실시간 예매 오픈 일시는 이 파일에 저장하지 않는다.

### 정규화 스키마

```json
{
  "ok": true,
  "data": {
    "stadium_count": 9,
    "stadiums": [
      {
        "id": "jamsil",
        "short_name": "잠실",
        "name": "잠실야구장",
        "city": "서울",
        "home_teams": ["LG 트윈스", "두산 베어스"],
        "is_dome": false,
        "address": "서울특별시 송파구 올림픽로 25",
        "coordinates": {
          "lat": 37.5122,
          "lng": 127.0719
        },
        "weather_grid": {
          "nx": 61,
          "ny": 126
        },
        "capacity": 23750,
        "ticketing": {
          "platforms": ["티켓링크", "인터파크"],
          "note": "LG 홈경기는 티켓링크, 두산 홈경기는 인터파크 예매를 기본값으로 사용한다."
        },
        "source": {
          "data_type": "manual_static_seed",
          "coordinate_type": "manual_static_wgs84",
          "weather_grid_type": "computed_from_coordinate"
        }
      }
    ]
  },
  "error": null,
  "metadata": {
    "source": "manual_static_stadium_metadata",
    "updated_at": "2026-05-06T00:00:00+09:00",
    "fallback_used": false
  }
}
```

### 필수 필드

| 필드 | 설명 | MVP 사용처 |
| --- | --- | --- |
| `id` | 내부 참조용 구장 ID | Tool 간 공통 key |
| `short_name` | 경기 일정 데이터의 구장 약칭 | KBO 일정과 구장 메타데이터 매칭 |
| `name` | 표준 구장명 | 사용자 응답 및 Tool 입력 |
| `home_teams` | 해당 구장을 홈으로 쓰는 팀 | 예매처/응원석 기준 판단 |
| `is_dome` | 돔구장 여부 | 우천/폭염 영향 판단 |
| `coordinates.lat` | 위도 | 기상청 격자 산출 근거 |
| `coordinates.lng` | 경도 | 기상청 격자 산출 근거 |
| `weather_grid.nx` | 기상청 X 격자 | 날씨 API 필수 입력 |
| `weather_grid.ny` | 기상청 Y 격자 | 날씨 API 필수 입력 |
| `ticketing.platforms` | 기본 예매처 | 예매처 안내 |

### Agent 사용 규칙

- 경기 일정 Tool이 반환한 `stadium.short_name` 또는 `stadium.name`으로 이 파일의 구장 데이터를 찾는다.
- 매칭 성공 시 `is_dome`, `weather_grid`, `ticketing`을 다음 Tool 호출에 전달한다.
- `is_dome`이 `true`이면 우천 취소 가능성을 낮게 보고 좌석 추천은 시야/응원/가격 중심으로 전환한다.
- `is_dome`이 `false`이면 날짜 범위별 날씨 정책에 따라 우천/폭염/바람 리스크를 좌석 추천에 반영한다.
- `weather_grid`가 없으면 날씨 API를 호출하지 않고 정적 좌석 추천으로 fallback한다.

### 실패 처리

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "STADIUM_METADATA_NOT_FOUND",
    "message": "경기 일정의 구장명을 정적 구장 메타데이터와 매칭하지 못했습니다."
  }
}
```

### 검증 기준

- `stadium_count`가 9인지 확인한다.
- 모든 구장 객체에 `id`, `short_name`, `name`, `is_dome`, `weather_grid`가 존재한다.
- `is_dome`은 boolean 값이어야 한다.
- `weather_grid.nx`, `weather_grid.ny`는 정수여야 한다.
- 크롤링 기반 필드인 `office_address`, `homepage`, `kbo_team_refs`는 포함하지 않는다.
