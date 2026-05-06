from app.prompts import SYSTEM_PROMPT
from app.tools import get_game_data, get_stadium_environment


MAX_STEPS = 5


def run_agent(message: str) -> dict:
    """Minimal rule-based loop placeholder for the first FastAPI skeleton."""
    observations = []

    game_result = get_game_data(message)
    observations.append({"tool": "game_data_provider", "result": game_result})

    if not game_result["ok"]:
        return {
            "answer": "경기 정보를 찾지 못했습니다. 날짜와 응원 팀을 조금 더 구체적으로 알려주세요.",
            "metadata": {
                "agent_mode": "fallback",
                "prompt": SYSTEM_PROMPT,
                "steps": len(observations),
                "observations": observations,
            },
        }

    stadium = game_result["data"]["stadium"]["name"]
    env_result = get_stadium_environment(stadium)
    observations.append({"tool": "stadium_env_expert", "result": env_result})

    answer = (
        f"{stadium} 경기 기준으로 좌석과 날씨를 함께 확인했습니다. "
        f"현재 추천 좌석은 {env_result['data']['recommended_zone']}이며, "
        f"{env_result['data']['weather_tip']} "
        "상세 교통이나 막차까지 필요하면 출발지를 함께 알려주세요."
    )

    return {
        "answer": answer,
        "metadata": {
            "agent_mode": "workflow_with_agent_guardrails",
            "max_steps": MAX_STEPS,
            "steps": len(observations),
            "observations": observations,
        },
    }
