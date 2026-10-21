"""1R.29 QA: 실제 어댑터가 여는 payload·응답이 등록된 상호작용 종류 스키마와 맞는가.

종류 디스크립터는 entry point(`agent_console.interaction_kinds`)로만 읽는다.
nodes-core는 import하지 않는다.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

import pytest

jsonschema = pytest.importorskip("jsonschema")

from agent_console_backend_claude_sdk.testing import InteractiveSink, PermissionCall  # noqa: E402
from agent_console_contracts import Limits  # noqa: E402
from agent_console_runtime import InteractionRequest  # noqa: E402

from .test_agent_console_backend_claude_sdk_interactions import (  # type: ignore[import-not-found]  # noqa: E402
    QUESTION_INPUT,
    SECRET,
    _ctx,
    _run,
)


def _kinds() -> dict[str, Any]:
    found = {ep.name: ep.load() for ep in entry_points(group="agent_console.interaction_kinds")}
    if not {"question", "tool_permission"} <= found.keys():
        pytest.skip("기본 상호작용 종류가 설치되어 있지 않음")
    return found


def _valid(schema: dict[str, Any], value: Any) -> bool:
    return bool(jsonschema.Draft202012Validator(schema).is_valid(value))


async def test_question_payload_and_responses_match_kind_schema() -> None:
    kind = _kinds()["question"]
    replies: list[dict[str, Any]] = [
        {"answers": {"어느 DB를 쓸까요?": "SQLite"}, "response": "로컬로"},
        {"answers": {"어느 DB를 쓸까요?": ["SQLite", "Postgres"]}},
        {"response": "직접 입력"},
    ]
    for reply in replies:
        assert _valid(kind.response_schema, reply), reply

        def answer(_r: InteractionRequest, reply: dict[str, Any] = reply) -> dict[str, Any]:
            return reply

        sink = InteractiveSink(answer)
        call = PermissionCall("AskUserQuestion", QUESTION_INPUT, _ctx(tool_use_id="tq"))
        await _run([call], sink)
        req = sink.requests[0]
        assert _valid(kind.request_schema, req.payload), req.payload
    assert kind.free_text_path == "/response"


async def test_tool_permission_payload_and_responses_match_kind_schema() -> None:
    kind = _kinds()["tool_permission"]
    ctx = _ctx(tool_use_id="tu1", title="t", display_name="d")
    sink = InteractiveSink(lambda _r: {"decision": "allow", "updated_input": {"command": "ls"}})
    call = PermissionCall("Bash", {"command": "ls", "api_key": SECRET}, ctx)
    await _run([call], sink, limits=Limits(commands=["ls"]))
    req: InteractionRequest = sink.requests[0]
    assert _valid(kind.request_schema, req.payload), req.payload
    for reply in (
        {"decision": "allow"},
        {"decision": "allow_for_run"},
        {"decision": "deny", "message": "no"},
        {"decision": "allow", "updated_input": {"command": "ls"}},
        kind.expire_response,
    ):
        assert _valid(kind.response_schema, reply), reply
