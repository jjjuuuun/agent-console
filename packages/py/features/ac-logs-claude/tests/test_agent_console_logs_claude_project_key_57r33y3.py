"""5.7R.33y3: 폴더 키 함수는 ``agent-console-claude-format`` 한 곳(세션 보관과 같은 함수)."""

from __future__ import annotations

from agent_console_claude_format import project_key as format_project_key
from agent_console_logs_claude import project_key


def test_project_key_is_reexported_from_claude_format() -> None:
    assert project_key is format_project_key
    assert project_key("/work/demo") == "-work-demo"
