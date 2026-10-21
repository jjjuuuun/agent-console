"""stdout JSON·종료 코드 → 결정(allow/deny/ask/block/수정 입력)."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_hook_probe import derive_decision, parse_hook_output


def _pre(**specific: Any) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", **specific}}


@pytest.mark.parametrize(
    ("output", "code", "event", "value", "reason"),
    [
        (_pre(permissionDecision="allow"), 0, "PreToolUse", "allow", None),
        (
            _pre(permissionDecision="deny", permissionDecisionReason="r"),
            0,
            "PreToolUse",
            "deny",
            "r",
        ),
        (_pre(permissionDecision="ask"), 0, "PreToolUse", "ask", None),
        (_pre(permissionDecision="defer"), 0, "PreToolUse", "defer", None),
        (_pre(updatedInput={"command": "x"}), 0, "PreToolUse", "modify", None),
        ({"decision": "approve"}, 0, "PreToolUse", "allow", None),  # 옛 값
        ({"decision": "block", "reason": "r"}, 0, "PreToolUse", "deny", "r"),
        ({"decision": "block", "reason": "r"}, 0, "PostToolUse", "block", "r"),
        ({"continue": False, "stopReason": "s"}, 0, "Stop", "stop", "s"),
        (
            {"hookSpecificOutput": {"decision": {"behavior": "deny", "message": "m"}}},
            0,
            "PermissionRequest",
            "deny",
            "m",
        ),
        (None, 0, "PreToolUse", "none", None),
        (_pre(permissionDecision="allow"), 2, "PreToolUse", "block", None),  # 2는 뒤집지 못함
        (_pre(permissionDecision="allow"), 1, "PreToolUse", "error", None),
        (None, None, "PreToolUse", "error", None),  # 실행 실패·신호
    ],
)
def test_derive_decision(
    output: dict[str, Any] | None, code: int | None, event: str, value: str, reason: str | None
) -> None:
    decision = derive_decision(output, code, event=event)
    assert decision["value"] == value
    assert decision["reason"] == reason


def test_flags_for_updated_input_output_and_context() -> None:
    d = derive_decision(
        _pre(
            permissionDecision="allow",
            updatedInput={"a": 1},
            updatedToolOutput="x",
            additionalContext="c",
        ),
        0,
    )
    assert (d["value"], d["updated_input"], d["updated_output"], d["additional_context"]) == (
        "allow",
        True,
        True,
        True,
    )
    allow_with_input = derive_decision(
        {"hookSpecificOutput": {"decision": {"behavior": "allow", "updatedInput": {}}}}, 0
    )
    assert allow_with_input["updated_input"] is True


@pytest.mark.parametrize(
    ("raw", "parsed"),
    [
        (b'{"a": 1}\n', {"a": 1}),
        (b'  {"a": 1}  ', {"a": 1}),
        (b"[1]", None),
        (b'text {"a": 1}', None),
        (b'{"a": 1} trailing', None),
        (b"\xff{", None),
        (b"", None),
    ],
)
def test_parse_hook_output_whole_object_only(raw: bytes, parsed: dict[str, Any] | None) -> None:
    assert parse_hook_output(raw) == parsed
