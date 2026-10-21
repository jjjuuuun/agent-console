"""agent-console-secret-rules: 비밀 의심 판정과 텍스트 안 의심 값 가리기.

스키마를 모를 때 쓰는 휴리스틱이다(스키마의 `x-secret`이 있으면 그쪽이 우선). 규칙은 데이터이며
기본 규칙에 사용자 규칙을 **더하기만** 한다.

공개 API:
    - ``SecretRules(key_names, value_patterns, *, name_exceptions, is_reference, mask, timeout,
      max_scan_chars)``: 규칙 묶음(불변). ``.with_extra(key_names=, value_patterns=)``로 더한다.
      ``default_rules()``: 기본 규칙(한 번만 만들어 공유).
    - ``.find_suspected(value, *, path="", name=None) -> list[Finding]``: JSON 값의 의심 위치
      (값은 담지 않음).
    - ``.redact_suspected(text) -> str``, ``.redact_value(value)``: 텍스트(또는 JSON 값의 문자열)
      안 의심 부분 가리기.
    - ``.name_suspected(name)``, ``.value_suspected(text)``: 단건 판정.
    - ``check_extra_rules(extra_key_names, extra_value_patterns) -> list[RuleProblem]``:
      저장 전 검사.
    - ``Finding``, ``FindingReason``, ``RuleProblem``, ``InvalidSecretRuleError``.
    - 기본 데이터: ``DEFAULT_KEY_NAMES``, ``DEFAULT_NAME_EXCEPTIONS``, ``DEFAULT_VALUE_PATTERNS``.
"""

from agent_console_secret_rules._defaults import (
    DEFAULT_KEY_NAMES,
    DEFAULT_NAME_EXCEPTIONS,
    DEFAULT_VALUE_PATTERNS,
)
from agent_console_secret_rules._rules import (
    DEFAULT_MAX_SCAN_CHARS,
    DEFAULT_SCAN_TIMEOUT_SECONDS,
    REDACTED,
    Finding,
    FindingReason,
    InvalidSecretRuleError,
    RuleProblem,
    SecretRules,
    check_extra_rules,
    default_is_reference,
    default_rules,
)

__all__ = [
    "DEFAULT_KEY_NAMES",
    "DEFAULT_MAX_SCAN_CHARS",
    "DEFAULT_NAME_EXCEPTIONS",
    "DEFAULT_SCAN_TIMEOUT_SECONDS",
    "DEFAULT_VALUE_PATTERNS",
    "REDACTED",
    "Finding",
    "FindingReason",
    "InvalidSecretRuleError",
    "RuleProblem",
    "SecretRules",
    "check_extra_rules",
    "default_is_reference",
    "default_rules",
]
