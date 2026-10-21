"""1R.30 QA: 반례 시도(ToolGuard 우회, 비밀 노출, 실행 간 메모리)."""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import PermissionResultDeny

from agent_console_backend_claude_sdk.testing import InteractiveSink, PermissionCall
from agent_console_contracts import Limits

from .test_agent_console_backend_claude_sdk_interactions import SECRET, _ctx, _run  # type: ignore[import-not-found]


async def test_user_updated_input_cannot_escape_tool_guard() -> None:
    """사용자가 updated_input으로 허용 범위 밖 명령을 넣어도 막혀야 한다."""
    sink = InteractiveSink(
        lambda _r: {"decision": "allow", "updated_input": {"command": "rm -rf /"}}
    )
    call = PermissionCall("Bash", {"command": "git status"})
    await _run([call], sink, limits=Limits(commands=["git status"]))
    assert isinstance(call.results[0], PermissionResultDeny)


async def test_allow_for_run_cannot_unlock_guarded_input() -> None:
    sink = InteractiveSink(lambda _r: {"decision": "allow_for_run"})
    ok = PermissionCall("Bash", {"command": "git status"})
    bad = PermissionCall("Bash", {"command": "rm -rf /"})
    await _run([ok, bad], sink, limits=Limits(commands=["git status"]))
    assert isinstance(bad.results[0], PermissionResultDeny)
    assert len(sink.requests) == 1


async def test_context_fields_do_not_leak_secret() -> None:
    sink = InteractiveSink(lambda _r: {"decision": "deny"})
    ctx = _ctx(
        blocked_path=f"/x/{SECRET}",
        decision_reason=f"token {SECRET}",
        description=f"d {SECRET}",
        title=f"t {SECRET}",
        display_name=f"n {SECRET}",
    )
    call = PermissionCall("Read", {"file_path": f"/x/{SECRET}"}, ctx)
    await _run([call], sink)
    req = sink.requests[0]
    blob: Any = repr(req.model_dump())
    assert SECRET not in blob


async def test_allow_for_run_with_escaping_updated_input_is_denied_and_not_remembered() -> None:
    sink = InteractiveSink(
        lambda _r: {"decision": "allow_for_run", "updated_input": {"command": "rm -rf /"}}
    )
    first = PermissionCall("Bash", {"command": "git status"})
    again = PermissionCall("Bash", {"command": "git status"})
    await _run([first, again], sink, limits=Limits(commands=["git status"]))
    assert isinstance(first.results[0], PermissionResultDeny)
    assert isinstance(again.results[0], PermissionResultDeny)
    assert len(sink.requests) == 2


async def test_question_answers_cannot_smuggle_guarded_fields() -> None:
    sink = InteractiveSink(lambda _r: {"answers": {"q": "a"}, "response": "x"})
    call = PermissionCall("AskUserQuestion", {"questions": [{"question": "q", "options": []}]})
    await _run([call], sink, limits=Limits(commands=["git status"]))
    assert call.results[0].updated_input["answers"] == {"q": "a"}
