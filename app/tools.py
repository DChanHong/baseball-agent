def get_game_data(message: str) -> dict:
    """Mock game data provider. Replace with KBO/Naver integration later."""
    if not message.strip():
        return {
            "ok": False,
            "data": None,
            "error": {
                "code": "EMPTY_INPUT",
                "message": "사용자 요청이 비어 있습니다.",
            },
        }

    return {
        "ok": True,
        "data": {
            "game_id": "mock-20260515-lotte-jamsil",
            "teams": {
                "home": {"name": "두산 베어스", "code": "OB"},
                "away": {"name": "롯데 자이언츠", "code": "LT"},
            },
            "stadium": {
                "name": "잠실야구장",
                "is_dome": False,
            },
            "schedule": {
                "date": "2026-05-15",
                "time": "14:00",
            },
            "status": "PRE_GAME",
        },
        "error": None,
    }


def get_stadium_environment(stadium_name: str) -> dict:
    """Mock stadium environment tool. Replace with weather/API/RAG later."""
    if stadium_name != "잠실야구장":
        return {
            "ok": False,
            "data": None,
            "error": {
                "code": "STADIUM_NOT_FOUND",
                "message": "지원하지 않는 구장입니다.",
            },
        }

    return {
        "ok": True,
        "data": {
            "weather": {
                "temp": 31,
                "condition": "sunny",
                "precipitation_probability": 10,
            },
            "recommended_zone": "3루 네이비석 상단",
            "weather_tip": "낮 경기라 햇빛 노출이 커서 선크림과 모자를 챙기는 편이 좋습니다.",
            "fallback_used": False,
        },
        "error": None,
    }
