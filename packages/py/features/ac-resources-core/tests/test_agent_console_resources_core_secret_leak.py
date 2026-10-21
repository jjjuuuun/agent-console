"""QA: 잘못된 모양의 env·headers 값이 이슈 메시지로 새지 않아야 한다(1R.6 R13.5)."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import Resource
from agent_console_resources_core.mcp_server import McpServerType

SECRET = "sk-SECRETVALUE123"
NUMBER = 987654321


@pytest.mark.parametrize(
    "config",
    [
        {"name": "a", "command": "x", "env": SECRET},
        {"name": "a", "command": "x", "env": {"K": [SECRET]}},
        {"name": "a", "command": "x", "env": {"K": NUMBER}},
        {"name": "a", "transport": "http", "url": "u", "headers": SECRET},
        {"name": "a", "transport": "http", "url": "u", "headers": {"A": {"v": SECRET}}},
    ],
)
def test_malformed_secret_fields_do_not_leak(config: dict[str, Any]) -> None:
    issues = McpServerType().validate(Resource(id="m", type="mcp-server", name="m", config=config))
    assert issues
    text = repr(issues)
    assert SECRET not in text
    assert str(NUMBER) not in text
