"""ExpectRules·ExpectWatcher: 규칙 → 신호, 조각 경계, 컴파일 주입."""

from __future__ import annotations

import re

import pytest

from agent_console_pty_session import ExpectRule, ExpectRuleError, ExpectRules, ExpectWatcher

URL = r"https://\S+/oauth/authorize\S*"


def test_match_line_returns_rules_in_order() -> None:
    rules = ExpectRules([ExpectRule("code", r"(?i)paste code"), ExpectRule("url", URL)])
    found = rules.match_line("Paste code: https://claude.ai/oauth/authorize?x=1")
    assert [(m.name, m.text) for m in found] == [
        ("code", "Paste code"),
        ("url", "https://claude.ai/oauth/authorize?x=1"),
    ]


def test_named_groups_and_first() -> None:
    rules = ExpectRules({"status": r"exit=(?P<code>\d+)"})
    hit = rules.first("a\nexit=3\n", "status")
    assert hit is not None
    assert hit.groups == {"code": "3"}
    assert rules.first("nothing", "status") is None


def test_compile_is_injected_and_rejection_wrapped() -> None:
    seen: list[str] = []

    def strict(pattern: str) -> re.Pattern[str]:
        seen.append(pattern)
        if "(a+)+" in pattern:
            raise ValueError("unsafe")
        return re.compile(pattern)

    ExpectRules({"ok": "a"}, compile=strict)
    assert seen == ["a"]
    with pytest.raises(ExpectRuleError) as info:
        ExpectRules({"bad": "(a+)+$"}, compile=strict)
    assert info.value.rule == "bad"


def test_invalid_regex_raises_rule_error() -> None:
    with pytest.raises(ExpectRuleError):
        ExpectRules({"broken": "("})


def test_watcher_defers_match_touching_unfinished_line_end() -> None:
    watcher = ExpectWatcher(ExpectRules({"url": URL}))
    assert watcher.feed("open https://claude.ai/oauth/auth") == []
    found = watcher.feed("orize?code=1 in browser")
    assert [m.text for m in found] == ["https://claude.ai/oauth/authorize?code=1"]
    # 줄이 끝나도 다시 알리지 않는다
    assert watcher.feed("\n") == []


def test_watcher_prompt_without_newline_is_reported_once() -> None:
    watcher = ExpectWatcher(ExpectRules({"needs_code": r"(?i)paste code"}))
    assert [m.name for m in watcher.feed("Paste code here if prompted > ")] == ["needs_code"]
    assert watcher.feed("x") == []
    assert watcher.feed("\nPaste code again > ") != []


def test_watcher_flush_reports_deferred() -> None:
    watcher = ExpectWatcher(ExpectRules({"url": URL}))
    assert watcher.feed("https://claude.ai/oauth/authorize") == []
    assert [m.name for m in watcher.flush()] == ["url"]
    assert watcher.flush() == []


def test_watcher_completed_lines() -> None:
    watcher = ExpectWatcher(ExpectRules({"ok": r"(?i)login successful"}))
    assert [m.line for m in watcher.feed("one\nLogin successful. Press Enter\nthree")] == [
        "Login successful. Press Enter"
    ]


def test_watcher_pending_limit() -> None:
    watcher = ExpectWatcher(ExpectRules({"z": "z"}), max_pending_chars=4)
    watcher.feed("z" + "a" * 10)
    assert watcher.flush() == []
