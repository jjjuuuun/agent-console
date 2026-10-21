"""비밀 의심 규칙: 기본 규칙, 보강 4가지(1R.37d·1R.14 QA2), 사용자 규칙 더하기, 가리기."""

from __future__ import annotations

import pytest

from agent_console_secret_rules import (
    DEFAULT_KEY_NAMES,
    DEFAULT_VALUE_PATTERNS,
    REDACTED,
    Finding,
    FindingReason,
    InvalidSecretRuleError,
    SecretRules,
    check_extra_rules,
)

RULES = SecretRules()
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlX3ZhbHVl"
PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAKj\n-----END RSA PRIVATE KEY-----"


def _paths(found: list[Finding]) -> list[str]:
    return [f.path for f in found]


# ---------------------------------------------------------------- 기본 규칙(1R 규칙 유지)


def test_name_rules_keep_1r_behaviour() -> None:
    for name in ("API_KEY", "--auth-token", "apiKey", "x-api-key", "GITHUB_TOKEN", "password"):
        assert RULES.name_suspected(name), name
    for name in ("PATH", "max_tokens", "keybindings", "monkey", ""):
        assert not RULES.name_suspected(name), name


def test_value_rules_keep_1r_behaviour() -> None:
    assert RULES.value_suspected("ghp_abcdefghij")
    assert RULES.value_suspected("sk-live-123456")
    assert not RULES.value_suspected("sk-1")
    assert not RULES.value_suspected("hello")
    assert not RULES.value_suspected("secret://TOKEN")


def test_find_suspected_pointers_and_references() -> None:
    value = {
        "env": {"API_KEY": "plain", "PATH": "/bin", "TOKEN": "secret://T", "EMPTY_KEY": ""},
        "args": ["--x", "ghp_abcdefghijk"],
        "a/b": {"password": "p"},
        "max_tokens": 5,
    }
    assert _paths(RULES.find_suspected(value)) == ["/env/API_KEY", "/args/1", "/a~1b/password"]
    assert _paths(RULES.find_suspected("x", name="secret")) == [""]
    assert _paths(RULES.find_suspected({"k": "v"}, path="/config")) == []
    assert _paths(RULES.find_suspected({"token": "v"}, path="/config")) == ["/config/token"]


def test_findings_never_carry_values() -> None:
    found = RULES.find_suspected({"API_KEY": "plain-value-123"})
    assert found == [Finding("/API_KEY", FindingReason.KEY_NAME)]
    assert "plain-value-123" not in repr(found)


# ---------------------------------------------------------------- 보강 1: 비문자열 값


def test_non_string_values_under_secret_names() -> None:
    found = RULES.find_suspected({"API_KEY": 12345, "password": 1.5, "auth": True, "token": None})
    assert _paths(found) == ["/API_KEY", "/password"]
    assert _paths(RULES.find_suspected({"max_tokens": 5, "count": 3})) == []


# ---------------------------------------------------------------- 보강 2: 이름 이어받기


def test_children_inherit_nearest_secret_name() -> None:
    value = {
        "credentials": {"user": "u", "nested": {"value": "v"}, "list": ["a", 7]},
        "auth": {"mode": "oauth", "client_secret_file": "/x"},
        "plain": {"inner": "x"},
    }
    assert _paths(RULES.find_suspected(value)) == [
        "/credentials/user",
        "/credentials/nested/value",
        "/credentials/list/0",
        "/credentials/list/1",
    ]


def test_secret_flag_followed_by_value_in_argument_list() -> None:
    args = ["--token", "abc", "--verbose", "--key-file", "f.pem", "--token", "--y"]
    assert _paths(RULES.find_suspected({"args": args})) == ["/args/1"]


# ---------------------------------------------------------------- 보강 3: 문자열 안 토큰 모양


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("run --token abc123 now", f"run --token {REDACTED} now"),
        ("run --api-key=abc123", f"run --api-key={REDACTED}"),
        ("http://h/p?api_key=xyz&q=1", f"http://h/p?api_key={REDACTED}&q=1"),
        ("postgres://user:pw123@host/db", f"postgres://user:{REDACTED}@host/db"),
        (f"jwt {JWT} end", f"jwt {REDACTED} end"),
        (f"{PEM} after", f"{REDACTED} after"),
        ("use AIzaSyA1234567890abcdef here", f"use {REDACTED} here"),
        ("export API_KEY=abc and TOKEN: def", f"export API_KEY={REDACTED} and TOKEN: {REDACTED}"),
        ('{"password": "hunter2"}', f'{{"password": "{REDACTED}"}}'),
        ("Authorization: Bearer abcdef123456", f"Authorization: Bearer {REDACTED}"),
    ],
)
def test_tokens_inside_strings_are_found_and_redacted(text: str, expected: str) -> None:
    assert RULES.value_suspected(text)
    assert RULES.redact_suspected(text) == expected
    assert _paths(RULES.find_suspected({"note": text})) == ["/note"]


def test_text_without_secrets_is_untouched() -> None:
    for text in (
        "basic understanding of bearer tokens",
        "see https://example.com/path?page=2",
        "token=secret://GH",
        "--key-file ./k.pem --author bob",
        "",
    ):
        assert RULES.redact_suspected(text) == text
        assert not RULES.value_suspected(text)


def test_long_text_is_scanned_in_overlapping_chunks() -> None:
    rules = SecretRules(max_scan_chars=10_000)
    text = "a " * 20_000 + "ghp_abcdefghij" + " b" * 10
    assert "ghp_abcdefghij" not in rules.redact_suspected(text)


def test_redact_value_keeps_structure() -> None:
    value = {"text": "--token abc123", "n": 5, "list": ["ok", "ghp_abcdefghij"], "b": True}
    assert RULES.redact_value(value) == {
        "text": f"--token {REDACTED}",
        "n": 5,
        "list": ["ok", REDACTED],
        "b": True,
    }


# ---------------------------------------------------------------- 보강 4: 오탐 예외(데이터)


def test_exception_words_reduce_false_positives() -> None:
    for name in ("--key-file", "--author", "auth_mode", "token_url", "secret_name", "key_id"):
        assert not RULES.name_suspected(name), name
    assert RULES.name_suspected("key_id_secret")


def test_exception_list_is_data() -> None:
    strict = SecretRules(name_exceptions=())
    assert strict.name_suspected("--key-file")
    custom = SecretRules(name_exceptions=("salt",))
    assert not custom.name_suspected("token_salt")


# ---------------------------------------------------------------- 사용자 규칙: 더하기만


def test_extra_rules_only_add() -> None:
    rules = RULES.with_extra(key_names=["session-id"], value_patterns=[r"corp_[0-9]{6}"])
    assert rules.key_names == (*DEFAULT_KEY_NAMES, "session-id")
    assert rules.value_patterns == (*DEFAULT_VALUE_PATTERNS, r"corp_[0-9]{6}")
    assert rules.name_suspected("SESSION_ID")
    assert rules.name_suspected("sessionid")
    assert not RULES.name_suspected("SESSION_ID")
    assert rules.redact_suspected("id corp_123456 x") == f"id {REDACTED} x"
    # 기본 규칙은 그대로 남는다
    assert rules.name_suspected("API_KEY")
    assert rules.value_suspected("ghp_abcdefghij")


def test_extra_pattern_groups() -> None:
    rules = RULES.with_extra(value_patterns=[r"pin\s(?P<secret>\d{4})"])
    assert rules.redact_suspected("pin 1234 ok") == f"pin {REDACTED} ok"


def test_dangerous_or_invalid_extra_rules_rejected() -> None:
    problems = check_extra_rules(["", "ok"], ["(a+)+$", "fine", "[unclosed"])
    assert [(p.field, p.index) for p in problems] == [
        ("extra_key_names", 0),
        ("extra_value_patterns", 0),
        ("extra_value_patterns", 2),
    ]
    with pytest.raises(InvalidSecretRuleError) as info:
        RULES.with_extra(value_patterns=["(a|a)*"])
    assert info.value.problems[0].index == 0
    assert check_extra_rules(["x"], [r"corp_\d+"]) == []


def test_timeout_is_treated_as_suspected() -> None:
    rules = SecretRules(value_patterns=[r"(?:a|aa)c"], timeout=1e-9)
    text = "ab" * 200_000
    assert rules.redact_suspected(text) in (text, REDACTED)
    if rules.redact_suspected(text) == REDACTED:
        assert rules.find_suspected({"x": text}) == [Finding("/x", FindingReason.TIMEOUT)]


def test_custom_reference_and_mask() -> None:
    rules = SecretRules(is_reference=lambda v: v.startswith("vault:"), mask="***")
    assert rules.find_suspected({"token": "vault:x"}) == []
    assert rules.redact_suspected("--token abc123") == "--token ***"
