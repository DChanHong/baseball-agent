import re
from dataclasses import dataclass
from typing import Any


CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
EXTRACTION_ACTION_PATTERN = r"(출력|보여|공개|알려|요약|번역|설명|힌트|print|show|reveal|leak|dump|summarize|translate|describe|hint)"

SAFE_REDIRECT = "경기 일정, 좌석, 예매, 동선 안내 범위에서 다시 질문해 주세요."
DEFAULT_REFUSAL_ANSWER = (
    "시스템 프롬프트, 개발자 지침, API key, 내부 로그 같은 내부 정보는 제공할 수 없습니다. "
    f"{SAFE_REDIRECT}"
)
REFUSAL_ANSWERS = {
    "PERSONAL_DATA_REQUEST": f"개인정보 목록이나 민감한 사용자 데이터는 제공할 수 없습니다. {SAFE_REDIRECT}",
    "REFUSAL_BYPASS_REQUEST": f"거절 금지나 제한 무시 지시는 따를 수 없습니다. {SAFE_REDIRECT}",
    "SECURITY_BYPASS_REQUEST": f"보안 규칙을 우회하거나 제한을 해제하는 요청은 따를 수 없습니다. {SAFE_REDIRECT}",
}
REFUSAL_CODE_PRIORITY = (
    "SECRET_OR_KEY_REQUEST",
    "PERSONAL_DATA_REQUEST",
    "SYSTEM_PROMPT_EXTRACTION",
    "DEVELOPER_INSTRUCTION_EXTRACTION",
    "HIDDEN_RULES_EXTRACTION",
    "INTERNAL_LOG_REQUEST",
    "SECURITY_BYPASS_REQUEST",
    "REFUSAL_BYPASS_REQUEST",
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
        pattern=re.compile(rf"(시스템\s*프롬프트|system\s*prompt).{{0,40}}{EXTRACTION_ACTION_PATTERN}", re.IGNORECASE),
    ),
    SecurityPattern(
        code="DEVELOPER_INSTRUCTION_EXTRACTION",
        severity="high",
        block=True,
        pattern=re.compile(rf"(developer\s*instruction|개발자\s*(지침|명령)).{{0,40}}{EXTRACTION_ACTION_PATTERN}", re.IGNORECASE),
    ),
    SecurityPattern(
        code="HIDDEN_RULES_EXTRACTION",
        severity="high",
        block=True,
        pattern=re.compile(rf"(hidden\s*rules|숨겨진\s*(규칙|정책|지침)).{{0,40}}{EXTRACTION_ACTION_PATTERN}", re.IGNORECASE),
    ),
    SecurityPattern(
        code="SECRET_OR_KEY_REQUEST",
        severity="high",
        block=True,
        pattern=re.compile(rf"(api\s*key|토큰|token|secret|비밀키|인증키|환경변수|\.env).{{0,40}}{EXTRACTION_ACTION_PATTERN}", re.IGNORECASE),
    ),
    SecurityPattern(
        code="INTERNAL_LOG_REQUEST",
        severity="high",
        block=True,
        pattern=re.compile(rf"(내부\s*로그|internal\s*log|langsmith\s*trace).{{0,40}}{EXTRACTION_ACTION_PATTERN}", re.IGNORECASE),
    ),
    SecurityPattern(
        code="ADMIN_MODE_CLAIM",
        severity="medium",
        block=False,
        pattern=re.compile(r"(관리자\s*모드|admin\s*mode|관리자\s*테스트\s*모드)", re.IGNORECASE),
    ),
    SecurityPattern(
        code="REFUSAL_BYPASS_REQUEST",
        severity="high",
        block=True,
        pattern=re.compile(r"(거절하지\s*말고|제한을\s*무시|규칙을\s*무시|do\s*not\s*refuse)", re.IGNORECASE),
    ),
    SecurityPattern(
        code="SECURITY_BYPASS_REQUEST",
        severity="high",
        block=True,
        pattern=re.compile(
            r"(보안\s*규칙|안전\s*규칙|security\s*rule|safety\s*rule|guardrail).{0,30}(우회|해제|무시|bypass|disable|ignore)",
            re.IGNORECASE,
        ),
    ),
    SecurityPattern(
        code="PERSONAL_DATA_REQUEST",
        severity="high",
        block=True,
        pattern=re.compile(
            r"(개인정보|고객\s*목록|사용자\s*목록|고객\s*데이터|주문\s*고객|전화번호|이메일|주소).{0,40}(출력|보여|공개|알려|csv|목록|리스트|내보내|export|dump)",
            re.IGNORECASE,
        ),
    ),
)


def _refusal_code(flags: list[dict[str, str]]) -> str | None:
    blocked_codes = {flag.get("code") for flag in flags if flag.get("action") == "blocked"}
    for code in REFUSAL_CODE_PRIORITY:
        if code in blocked_codes:
            return code
    return next(iter(blocked_codes), None)


def refusal_answer(refusal_code: str | None) -> str:
    return REFUSAL_ANSWERS.get(refusal_code or "", DEFAULT_REFUSAL_ANSWER)


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

    refusal_code = _refusal_code(flags) if blocked else None
    return {
        "processed_message": processed_message,
        "security": {
            "checked": True,
            "blocked": blocked,
            "refusal_code": refusal_code,
            "flags": flags,
            "flag_count": len(flags),
        },
    }
