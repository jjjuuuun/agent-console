"""5.7R.33y3 X38: Claude 세션 기록 보관·복원(앱 전용 자격 폴더의 ``projects/<키>/``만).

SDK·CLI를 부르지 않는다. 가짜 자격 폴더에 세션 파일과 자격·설정 파일을 두고 확인한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_console_backend_claude_sdk import ClaudeSdkBackend, claude_session_archive
from agent_console_claude_format import project_key
from agent_console_contracts import KnownSessionStates
from agent_console_runtime import (
    JsonlFolderSessionArchive,
    SessionArchive,
    SessionRef,
    copy_files,
)


def _fake_config(config: Path, cwd: Path, sid: str) -> Path:
    """가짜 자격 폴더: 세션 하나 + 자격·설정·다른 세션 파일."""
    folder = config / "projects" / project_key(str(cwd))
    (folder / sid / "subagents").mkdir(parents=True)
    (folder / f"{sid}.jsonl").write_text('{"type":"user"}\n', encoding="utf-8")
    (folder / sid / "subagents" / "agent-a1.jsonl").write_text("{}\n", encoding="utf-8")
    (folder / "other-session.jsonl").write_text("{}\n", encoding="utf-8")
    (config / ".credentials.json").write_text('{"token":"x"}', encoding="utf-8")
    (config / "settings.json").write_text("{}", encoding="utf-8")
    (folder / ".credentials.json").write_text('{"token":"x"}', encoding="utf-8")
    return folder


def test_backend_archive_uses_app_auth_dir_only(tmp_path: Path) -> None:
    backend = ClaudeSdkBackend(workspace=tmp_path / "ws", environ={})
    archive = backend.session_archive()
    assert isinstance(archive, SessionArchive)
    assert isinstance(archive, JsonlFolderSessionArchive)
    assert archive.root == tmp_path / "ws" / ".state" / "claude" / "projects"


def test_no_app_auth_dir_means_no_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """앱 전용 자격 폴더가 없으면(단독 사용·config_dir null) ~/.claude를 보지 않고 None."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert ClaudeSdkBackend(environ={}).session_archive() is None
    off = ClaudeSdkBackend(workspace=tmp_path, environ={}, auth_dir={"config_dir": None})
    assert off.session_archive() is None


def test_files_exclude_credentials_settings_and_other_sessions(tmp_path: Path) -> None:
    config = tmp_path / "ws" / ".state" / "claude"
    cwd = tmp_path / "project"
    _fake_config(config, cwd, "s-1")
    archive = ClaudeSdkBackend(workspace=tmp_path / "ws", environ={}).session_archive()
    assert archive is not None
    files = archive.files(SessionRef(backend="claude-agent-sdk", session_id="s-1"), cwd=cwd)
    assert files is not None
    names = sorted(f.name for f in files)
    assert names == ["s-1.jsonl", "s-1/subagents/agent-a1.jsonl"]
    assert all(".credentials" not in f.name and "settings" not in f.name for f in files)


def test_status_and_restore_between_two_apps(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    ref = SessionRef(backend="claude-agent-sdk", session_id="s-1")
    a = claude_session_archive(tmp_path / "a" / "claude")
    b = claude_session_archive(tmp_path / "b" / "claude")
    _fake_config(tmp_path / "a" / "claude", cwd, "s-1")
    assert a.status(ref, cwd=cwd) == KnownSessionStates.AVAILABLE
    assert b.status(ref, cwd=cwd) == KnownSessionStates.MISSING
    saved = tmp_path / "saved"
    copy_files(a.files(ref, cwd=cwd) or [], saved)
    assert b.restore(saved, ref, cwd=cwd) is True
    assert b.status(ref, cwd=cwd) == KnownSessionStates.AVAILABLE
    b_root = tmp_path / "b" / "claude"
    written = sorted(p.relative_to(b_root).as_posix() for p in b_root.rglob("*") if p.is_file())
    key = project_key(str(cwd))
    assert written == [f"projects/{key}/s-1.jsonl", f"projects/{key}/s-1/subagents/agent-a1.jsonl"]


def test_relocate_old_key_to_new_key(tmp_path: Path) -> None:
    config = tmp_path / "claude"
    old = tmp_path / "old-place"
    new = tmp_path / "new-place"
    _fake_config(config, old, "s-1")
    archive = claude_session_archive(config)
    ref = SessionRef(backend="claude-agent-sdk", session_id="s-1")
    assert archive.status(ref, cwd=new) == KnownSessionStates.RELOCATABLE
    assert archive.restore(None, ref, cwd=new) is True
    assert (config / "projects" / project_key(str(new)) / "s-1.jsonl").is_file()
    assert not (config / "projects" / project_key(str(new)) / "other-session.jsonl").exists()
