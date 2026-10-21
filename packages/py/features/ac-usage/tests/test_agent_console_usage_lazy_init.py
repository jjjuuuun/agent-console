"""패키지 `__init__` 지연 import(PEP 562): 공개 이름은 그대로, statusline만 쓰면 가볍다."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

import agent_console_usage


def test_every_public_name_resolves() -> None:
    for name in agent_console_usage.__all__:
        assert getattr(agent_console_usage, name) is not None
    assert set(agent_console_usage.__all__) <= set(dir(agent_console_usage))
    with pytest.raises(AttributeError):
        _ = agent_console_usage.no_such_name


def test_statusline_module_does_not_load_contracts() -> None:
    code = (
        "import json, sys, agent_console_usage.statusline; "
        "print(json.dumps(sorted(m for m in sys.modules if '.' not in m)))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout
    loaded = set(json.loads(out))
    assert loaded.isdisjoint({"agent_console_contracts", "agent_console_registry", "pydantic"})
