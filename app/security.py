import re
from dataclasses import dataclass
from typing import Any


CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

REFUSAL_ANSWER = (
    "시스템 프롬프트, 개발자 지침, API key, 내부 로그 같은 내부 정보는 제공할 수 없습니다. "
    "경기 일정, 좌석, 예매, 동선 안내 범위에서 다시 질문해 주세요."
)


@dataclass(frozen=True)
class SecurityPattern:
    code: str
    severity: str
    block: bool
    pattern: re.Pattern[str]


SECURITY_PATTERNS = (
    SecurityPattern(
        code="IGNORE_PREVIOUS_INSTRUCTIONS",
        severity="medium",
        block=False,
        pattern=re.compile(r"(이전|앞선|위의)\s*(지시|명령|규칙).{0,12}(무시|잊어|취소)", re.IGNORECASE),
    ),
    SecurityPattern(
        code="SYSTEM_PROMPT_EXTRACTION",
        severity="high",
        block=True,
        pattern=re.compile(r"(시스템\s*프롬프트|system\s*prompt).{0,30}(출력|보여|공개|알려|print|show)", re.IGNORECASE),
    ),
    SecurityPattern(
        code="DEVELOPER_INSTRUCTION_EXTRACTION",
        severity="high",
        block=True,
        pattern=re.compile(r"(developer\s*instruction|개발자\s*(지침|명령)).{0,30}(출력|보여|공개|알려|print|show)", re.IGNORECASE),
    ),
    SecurityPattern(
        code="HIDDEN_RULES_EXTRACTION",
        severity="high",
        block=True,
        pattern=re.compile(r"(hidden\s*rules|숨겨진\s*(규칙|정책|지침)).{0,30}(출력|보여|공개|알려|print|show)", re.IGNORECASE),
    ),
    SecurityPattern(
        code="SECRET_OR_KEY_REQUEST",
        severity="high",
        block=True,
        pattern=re.compile(r"(api\s*key|토큰|token|secret|비밀키|인증키|환경변수|\.env).{0,30}(출력|보여|공개|알려|print|show)", re.IGNORECASE),
    ),
    SecurityPattern(
        code="INTERNAL_LOG_REQUEST",
        severity="high",
        block=True,
        pattern=re.compile(r"(내부\s*로그|internal\s*log|langsmith\s*trace).{0,30}(출력|보여|공개|알려|print|show)", re.IGNORECASE),
    ),
    SecurityPattern(
        code="ADMIN_MODE_CLAIM",
        severity="medium",
        block=False,
        pattern=re.compile(r"(관리자\s*모드|admin\s*mode|관리자\s*테스트\s*모드)", re.IGNORECASE),
    ),
    SecurityPattern(
        code="REFUSAL_BYPASS_REQUEST",
        severity="medium",
        block=False,
        pattern=re.compile(r"(거절하지\s*말고|제한을\s*무시|규칙을\s*무시|do\s*not\s*refuse)", re.IGNORECASE),
    ),
)


def analyze_message(message: str) -> dict[str, Any]:
    processed_message = CONTROL_CHAR_PATTERN.sub("", message)
    flags: list[dict[str, str]] = []

    if processed_message != message:
        flags.append(
            {
                "code": "CONTROL_CHARS_REMOVED",
                "severity": "low",
                "action": "normalized",
            }
        )

    blocked = False
    for security_pattern in SECURITY_PATTERNS:
        if not security_pattern.pattern.search(processed_message):
            continue
        flags.append(
            {
                "code": security_pattern.code,
                "severity": security_pattern.severity,
                "action": "blocked" if security_pattern.block else "flagged",
            }
        )
        blocked = blocked or security_pattern.block

    return {
        "processed_message": processed_message,
        "security": {
            "checked": True,
            "blocked": blocked,
            "flags": flags,
            "flag_count": len(flags),
        },
    }
