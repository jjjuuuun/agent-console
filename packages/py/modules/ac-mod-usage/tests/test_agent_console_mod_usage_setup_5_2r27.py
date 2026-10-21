"""mod-usage 5.2R.27: 출처 목록의 연결 조각(절대 경로)과 빈 설정의 자동 켜기."""

from __future__ import annotations

import json
import os
import shlex
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_mod_usage import module, resolve_command
from agent_console_modkit import BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app

FIXED = datetime(2027, 1, 15, tzinfo=UTC)


def _fake_command(folder: Path) -> Path:
    folder.mkdir(parents=True)
    exe = folder / "agent-console"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


def _sources(tmp_path: Path, environ: dict[str, str], options: dict[str, Any] | None = None) -> Any:
    paths = Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "ws" / ".state")
    base = BaseServices(clock=lambda: FIXED, paths=paths, environ=environ)
    assembly = assemble([module], ModulesConfig(options={"mod-usage": options or {}}), base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        return {s["descriptor"]["id"]: s for s in client.get("/api/v1/usage/sources").json()}


def test_snippets_have_absolute_paths_and_auto_enable(tmp_path: Path) -> None:
    exe = _fake_command(tmp_path / "bin")
    sources = _sources(tmp_path, {"PATH": str(tmp_path / "bin")})
    assert {k: s["enabled"] for k, s in sources.items()} == {
        "fake": False,
        "run-events": True,
        "statusline-file": True,
    }
    line = sources["statusline-file"]
    assert line["descriptor"]["needs_setup"] is True
    assert line["last_received_at"] is None
    output = str(tmp_path / "ws" / ".state" / "usage" / "statusline.json")
    snippets = {s["id"]: s for s in line["descriptor"]["setup_snippets"]}
    command = json.loads(snippets["settings-json"]["text"])["statusLine"]["command"]
    assert shlex.split(command) == [str(exe), "statusline", "--output", output]
    assert os.path.isabs(shlex.split(command)[0])
    for snippet in snippets.values():
        assert "{" + "output_path}" not in snippet["text"]


def test_command_option_and_missing_command(tmp_path: Path) -> None:
    sources = _sources(tmp_path, {"PATH": ""}, {"agent_console_command": "/custom/ac"})
    text = sources["statusline-file"]["descriptor"]["setup_snippets"][0]["text"]
    assert "/custom/ac statusline" in text
    # PATH에서 못 찾으면 이름 그대로(조각은 여전히 쓸 수 있다)
    sources = _sources(tmp_path, {"PATH": ""})
    text = sources["statusline-file"]["descriptor"]["setup_snippets"][0]["text"]
    assert "agent-console statusline" in text


def test_resolve_command(tmp_path: Path) -> None:
    exe = _fake_command(tmp_path / "b")
    assert resolve_command("agent-console", {"PATH": str(tmp_path / "b")}) == str(exe)
    assert resolve_command("./rel/agent-console", {}) == str(Path("./rel/agent-console").absolute())


def test_resolve_command_falls_back_to_extra_dirs(tmp_path: Path) -> None:
    """PATH에 없으면 서버를 실행한 파이썬 폴더 같은 추가 폴더에서 찾아 절대 경로로 낸다."""
    exe = _fake_command(tmp_path / "venv")
    got = resolve_command("agent-console", {"PATH": ""}, extra_dirs=[str(tmp_path / "venv")])
    assert got == str(exe)
    assert Path(got).is_absolute()
