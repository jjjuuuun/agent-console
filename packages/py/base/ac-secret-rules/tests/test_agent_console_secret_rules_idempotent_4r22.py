"""4R.22: 이미 가려진 글을 다시 가려도 모양이 변하지 않아야 한다(수집+내보내기 이중 가림)."""

import pytest

from agent_console_secret_rules import REDACTED, SecretRules, default_rules

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlX3ZhbHVl"
PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAKj\n-----END RSA PRIVATE KEY-----"
PEM_OPEN = "-----BEGIN PRIVATE KEY-----\nMIIBOgIBAAJBAKj and more"

SAMPLES = [
    "password=hunter2-planted-pw",
    "MY_API_KEY=abc123",
    "export API_KEY=abc and TOKEN: def",
    '{"password": "hunter2"}',
    "password='quoted'",
    "password=ab]cd",
    "run --token abc123 now",
    "run --api-key=abc123",
    "http://h/p?api_key=xyz&q=1",
    "postgres://user:pw123@host/db",
    "Authorization: Bearer abcdef123456",
    "Authorization: Basic dXNlcjpwYXNzd29yZDEyMw==",
    f"jwt {JWT} end",
    f"{PEM} after",
    PEM_OPEN,
    "use AIzaSyA1234567890abcdef here",
    "gh ghp_ABCDEFGHIJKLMNOP and sk-ant-0123456789abcdef",
    "aws AKIAABCDEFGHIJKLMNOP x",
    "slack xoxb-123456-abcdef",
    "hf hf_abcdefghijk npm npm_abcdefghijk",
]


def test_redact_is_idempotent() -> None:
    rules = default_rules()
    once = rules.redact_suspected("password=hunter2-planted-pw")
    assert once == f"password={REDACTED}"
    assert rules.redact_suspected(once) == once


@pytest.mark.parametrize("text", SAMPLES)
def test_every_default_rule_is_idempotent(text: str) -> None:
    rules = default_rules()
    once = rules.redact_suspected(text)
    assert once != text  # 표본은 모두 무언가 가려진다
    assert rules.redact_suspected(once) == once


def test_mask_alone_is_not_suspected() -> None:
    rules = default_rules()
    assert not rules.value_suspected(f"password={REDACTED}")
    assert rules.redact_value({"a": [f"--token {REDACTED}"]}) == {"a": [f"--token {REDACTED}"]}


def test_text_glued_to_a_mask_is_still_redacted() -> None:
    """가린 자리를 섞어 넣어도 옆의 평문은 가린다(가림 회피 방지)."""
    rules = default_rules()
    out = rules.redact_suspected(f"password=hunter2{REDACTED}")
    assert "hunter2" not in out
    assert rules.redact_suspected(out) == out


def test_custom_mask_is_idempotent() -> None:
    rules = SecretRules(mask="<hidden>")
    once = rules.redact_suspected("password=x and --token abc123")
    assert once == "password=<hidden> and --token <hidden>"
    assert rules.redact_suspected(once) == once
