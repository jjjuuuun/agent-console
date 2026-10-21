"""5R.19: `]`·가림 문자열 경계에서 비밀의 뒤 조각이 남지 않아야 한다(입력 통제 공격자 사례)."""

import time

import pytest

from agent_console_safe_regex import check_user_regex
from agent_console_secret_rules import (
    DEFAULT_VALUE_PATTERNS,
    REDACTED,
    SecretRules,
    default_rules,
)

from .test_agent_console_secret_rules_idempotent_4r22 import SAMPLES  # type: ignore[import-not-found]

ATTACKS = [
    ("password=abc]hunter2", "password=[REDACTED]"),
    ("password=[REDACTED]hunter2", "password=[REDACTED]"),
    ("password=AAAA[REDACTED]BBBB", "password=[REDACTED]"),
    ("token=abc)def}ghi", "token=[REDACTED]"),
    ("password=]hunter2", "password=[REDACTED]"),
    ("--token AAAA[REDACTED]BBBB", "--token [REDACTED]"),
    ("sk-AAAAAAAA[REDACTED]BBBB end", "[REDACTED] end"),
    ("Authorization: Bearer abc123[REDACTED]BBBB", "Authorization: Bearer [REDACTED]"),
    ("[REDACTED]ghp_ABCDEFGHIJ", "[REDACTED]"),
]


@pytest.mark.parametrize(("text", "expected"), ATTACKS)
def test_no_tail_left_after_boundary(text: str, expected: str) -> None:
    rules = default_rules()
    out = rules.redact_suspected(text)
    assert out == expected
    for tail in ("hunter2", "BBBB", "def", "ghi", "ABCDEFGHIJ"):
        assert tail not in out
    assert rules.redact_suspected(out) == out  # 멱등


@pytest.mark.parametrize("text", SAMPLES)
def test_4r22_samples_stay_idempotent(text: str) -> None:
    rules = default_rules()
    once = rules.redact_suspected(text)
    assert once != text
    assert rules.redact_suspected(once) == once


def test_closing_bracket_still_ends_value_when_nothing_follows() -> None:
    rules = default_rules()
    assert rules.redact_suspected("{password=abc}") == "{password=[REDACTED]}"
    assert rules.redact_suspected("f(token=x), y") == "f(token=[REDACTED]), y"
    assert rules.redact_suspected('["api_key=abc"]') == '["api_key=[REDACTED]"]'
    assert rules.redact_suspected("{password=}") == "{password=}"


def test_mask_without_secret_context_is_left_alone() -> None:
    """비밀 규칙에 걸리지 않는 글(이름·접두어 없음)은 가린 자리 옆이어도 그대로다."""
    rules = default_rules()
    for text in ("AAAA[REDACTED]BBBB", "x [REDACTED] y", f"password={REDACTED}"):
        assert rules.redact_suspected(text) == text
        assert not rules.value_suspected(text)


def test_glued_tail_is_suspected() -> None:
    assert default_rules().value_suspected("password=[REDACTED]hunter2")


def test_custom_mask_boundary() -> None:
    rules = SecretRules(mask="<hidden>")
    out = rules.redact_suspected("password=<hidden>hunter2 and token=a]b")
    assert out == "password=<hidden> and token=<hidden>"
    assert rules.redact_suspected(out) == out


def test_default_patterns_pass_safe_regex_rules() -> None:
    for pattern in DEFAULT_VALUE_PATTERNS:
        check_user_regex(pattern)


@pytest.mark.parametrize(
    "text",
    [
        "password=" + "a]" * 50_000,
        "password=" + "]" * 100_000 + "x",
        ("password=" + REDACTED) * 5_000 + "x",
        "token=a" + ")b}c]" * 20_000,
    ],
)
def test_adversarial_inputs_finish_quickly(text: str) -> None:
    rules = default_rules()
    started = time.monotonic()
    out = rules.redact_suspected(text)
    assert time.monotonic() - started < 5.0
    assert out != text
    assert rules.redact_suspected(out) == out
