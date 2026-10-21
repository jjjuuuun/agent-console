"""agent-console-safe-regex: 사용자 정규식 검증·컴파일과 시간 제한 실행(ReDoS 대비).

공개 API:
    - ``compile_user_regex(pattern, *, required_groups, max_pattern_chars, ignore_case,
      timeout, max_input_chars) -> SafePattern``: 검사 + 컴파일.
    - ``check_user_regex(pattern, ...)``: 검증만(설정 저장 전).
    - ``SafePattern.search(text)`` / ``.match(text)`` -> ``SafeMatch | None``: 입력 앞부분만,
      시간 제한 안에서. 초과 시 ``RegexTimeoutError``.
    - ``SafePattern.finditer(text, *, overlapped=False) -> list[SafeMatch]``: 모든 매치(훑기 전체에
      시간 제한, ``overlapped``면 시작 위치마다).
      ``SafeMatch.span(name)``: 이름 그룹 위치.
    - 예외: ``UnsafeRegexError``(ValueError), ``RegexTimeoutError``(TimeoutError).
    - 기본값: ``DEFAULT_MAX_PATTERN_CHARS``, ``DEFAULT_MAX_INPUT_CHARS``,
      ``DEFAULT_TIMEOUT_SECONDS``.
"""

from agent_console_safe_regex._core import (
    DEFAULT_MAX_INPUT_CHARS,
    DEFAULT_MAX_PATTERN_CHARS,
    DEFAULT_TIMEOUT_SECONDS,
    RegexTimeoutError,
    SafeMatch,
    SafePattern,
    UnsafeRegexError,
    check_user_regex,
    compile_user_regex,
)

__all__ = [
    "DEFAULT_MAX_INPUT_CHARS",
    "DEFAULT_MAX_PATTERN_CHARS",
    "DEFAULT_TIMEOUT_SECONDS",
    "RegexTimeoutError",
    "SafeMatch",
    "SafePattern",
    "UnsafeRegexError",
    "check_user_regex",
    "compile_user_regex",
]
