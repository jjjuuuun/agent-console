"""실행 경로는 가볍다: 패키지 루트·`-m` 실행이 로그 코어·계약·pydantic을 가져오지 않는다."""

from __future__ import annotations

import subprocess
import sys

CHECK = (
    "import sys, runpy\n"
    "import agent_console_hook_probe, agent_console_hook_probe._cli\n"
    "heavy = [m for m in ('agent_console_logs', 'agent_console_contracts', 'pydantic', "
    "'agent_console_secret_rules') if m in sys.modules]\n"
    "print(','.join(heavy))\n"
)


def test_root_import_is_stdlib_only() -> None:
    done = subprocess.run([sys.executable, "-c", CHECK], capture_output=True, text=True, check=True)
    assert done.stdout.strip() == ""


def test_plugins_are_separate_submodule() -> None:
    import agent_console_hook_probe
    from agent_console_hook_probe import plugins

    assert not hasattr(agent_console_hook_probe, "HookProbeSource")
    assert plugins.HookProbeSource.descriptor.id == "hook-probe-jsonl"
