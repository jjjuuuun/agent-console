"""경계: `ac-logs`를 불러오지 않는다, 코드에 칸·범주·도구·출처 이름 문자열이 없다(R0.1)."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "agent_console_architecture"

# 기본 프로필·로그 출처에서 쓰일 법한 이름. 코드(문서 문자열 제외)의 문자열 값에 나오면 안 된다.
_FORBIDDEN = re.compile(
    r"\b(llm|mcp|hook|tool_call|tool_result|subagents?|delegation|dispatch|workspace|"
    r"claude-code[\w-]*|platform-runs|bash|grep|write|edit|rules|instructions|context|"
    r"agent-architecture|input|response|handoff|merge)\b",
    re.IGNORECASE,
)


def test_does_not_import_logs_package() -> None:
    code = (
        "import sys, agent_console_architecture, agent_console_architecture.testing\n"
        "bad = sorted(m for m in sys.modules if m.startswith('agent_console_logs'))\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def _string_values(tree: ast.AST) -> list[str]:
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            docstrings.add(id(node.value))  # 속성 설명 문자열
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_no_hardcoded_names_in_code() -> None:
    files = sorted(SRC.rglob("*.py"))
    assert files
    found = [
        (path.name, value)
        for path in files
        for value in _string_values(ast.parse(path.read_text(encoding="utf-8")))
        if _FORBIDDEN.search(value)
    ]
    assert found == []
