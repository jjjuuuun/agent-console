"""코어는 서버 계층·특정 도구 형식을 모른다."""

import subprocess
import sys


def test_import_does_not_pull_web_framework() -> None:
    code = (
        "import sys, agent_console_logs, agent_console_logs.testing, agent_console_logs.query;"
        "roots=('fastapi','starlette','agent_console_modkit');"
        "bad=[m for m in sys.modules if m.split('.')[0] in roots];"
        "print(bad); raise SystemExit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
