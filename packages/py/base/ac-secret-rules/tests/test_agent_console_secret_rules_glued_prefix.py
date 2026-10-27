"""앞에 글자가 붙은 접두 토큰(`xxxsk-…`, 5.5R.32): 키 모양 몸통이면 가리고, 낱말 안 접두는
그대로 둔다.

경계 규칙은 기본 값 패턴 데이터(`DEFAULT_VALUE_PATTERNS`)에 있고 `ac-safe-regex` 검사를 통과한다.
"""

from __future__ import annotations

import pytest

from agent_console_safe_regex import check_user_regex
from agent_console_secret_rules import (
    DEFAULT_KEY_NAMES,
    DEFAULT_VALUE_PATTERNS,
    REDACTED,
    SecretRules,
    default_rules,
)

# 가짜 토큰은 실행 중에 이어 붙인다. 소스에 실제 형식 문자열이 통째로 있으면
# 공개 저장소의 비밀 검사(secret scanning)가 진짜 토큰으로 판정해 푸시를 막는다.
FAKE_ANTHROPIC = "sk-" + "ant-" + "api03-ABCDEFGH12345678abcd"
FAKE_GITHUB_PAT = "ghp" + "_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
FAKE_SLACK_BOT = "xox" + "b-" + "123456789012-AbCdEfGhIjKlMnOpQrStUv"

QA_FILLER = "x" * 200  # 5.2R.43 QA 관찰: 긴 글자 뒤에 공백 없이 붙은 키
GLUED = [
    (f"{QA_FILLER}sk-abcdefghijklmnopqrstuvwx0123456789ZZ tail", f"{QA_FILLER}{REDACTED} tail"),
    ("xxx" + FAKE_ANTHROPIC, f"xxx{REDACTED}"),
    ("abcsk-proj-AbCdEf0123456789xyz!", f"abc{REDACTED}!"),
    ("keyAKIAIOSFODNN7EXAMPLE", f"key{REDACTED}"),
    ("prefix" + FAKE_GITHUB_PAT, f"prefix{REDACTED}"),
    ("값은" + FAKE_SLACK_BOT, f"값은{REDACTED}"),
]


@pytest.mark.parametrize(("text", "expected"), GLUED)
def test_glued_prefix_token_is_redacted(text: str, expected: str) -> None:
    rules = default_rules()
    assert rules.value_suspected(text)
    out = rules.redact_suspected(text)
    assert out == expected
    assert rules.redact_suspected(out) == out  # 멱등


@pytest.mark.parametrize(
    "text",
    [
        "disk-usage-report-2024-final-version",
        "task-runner-ABCDEFGHIJKLMNOP",
        "risk-assessment-Q4-2024-REVIEW-DOC",
        "pnpm_config_store_dir",
        "ashf_settings_value",
        "xxxsk-short1A",
    ],
)
def test_prefix_inside_words_is_left_alone(text: str) -> None:
    rules = default_rules()
    assert not rules.value_suspected(text)
    assert rules.redact_suspected(text) == text


def test_bounded_prefix_still_needs_only_short_body() -> None:
    """앞이 단어 경계면 기존대로 몸통 6자면 된다(소문자만이어도)."""
    rules = default_rules()
    assert rules.redact_suspected("key: sk-live-123456") == f"key: {REDACTED}"
    assert rules.redact_suspected("(sk-abcdefgh)") == f"({REDACTED})"


def test_glued_rule_is_data_and_passes_safe_regex() -> None:
    for pattern in DEFAULT_VALUE_PATTERNS:
        check_user_regex(pattern)
    # 규칙은 데이터다: 붙은 접두 규칙을 뺀 묶음을 넘기면 옛 동작(단어 경계만)으로 돌아간다
    bounded_only = tuple(p for p in DEFAULT_VALUE_PATTERNS if p != DEFAULT_VALUE_PATTERNS[1])
    rules = SecretRules(DEFAULT_KEY_NAMES, bounded_only)
    assert not rules.value_suspected("xxx" + FAKE_ANTHROPIC)
    assert rules.value_suspected(FAKE_ANTHROPIC)
