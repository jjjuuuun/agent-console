"""5.7R.33y3: 세션 기록 보관 사본(``sessions/<backend>/<session>/``)·이어 가기 상태·복원(X38).

실제 백엔드 없이 ``JsonlFolderSessionArchive``(키 함수만 다름)를 앱 둘의 "자격 폴더"로 쓴다.
"""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_console_contracts import KnownSessionStates, RunEvent
from agent_console_link_projects_records import (
    ProjectSessionArchive,
    SessionArchiver,
    SessionArchiveSettings,
)
from agent_console_link_projects_records.testing import FolderSpaces
from agent_console_runtime import JsonlFolderSessionArchive, SessionArchive, SessionRef

BACKEND = "fake-agent"


def _key(cwd: str) -> str:
    return "k" + "".join(ch if ch.isalnum() else "-" for ch in cwd)


class Backends:
    """``runs.session_archive`` 모양(백엔드 id → 보관 기능)."""

    def __init__(self, archives: dict[str, SessionArchive]) -> None:
        self.archives = archives

    def get(self, backend_id: str) -> SessionArchive | None:
        return self.archives.get(backend_id)


def _app(root: Path) -> JsonlFolderSessionArchive:
    return JsonlFolderSessionArchive(root / "projects", _key)


def _write_session(app: JsonlFolderSessionArchive, cwd: Path, sid: str, text: str = "t1\n") -> Path:
    folder = app.root / _key(os.path.abspath(cwd))
    (folder / sid / "subagents").mkdir(parents=True, exist_ok=True)
    (folder / f"{sid}.jsonl").write_text(text, encoding="utf-8")
    (folder / sid / "subagents" / "agent-1.jsonl").write_text("{}\n", encoding="utf-8")
    (folder / "other.jsonl").write_text("other\n", encoding="utf-8")
    (app.root.parent / ".credentials.json").write_text('{"t":"x"}', encoding="utf-8")
    (app.root.parent / "settings.json").write_text("{}", encoding="utf-8")
    return folder


def _archive(
    folders: dict[str, Path], app: JsonlFolderSessionArchive | None, **settings: Any
) -> ProjectSessionArchive:
    spaces = FolderSpaces(folders)
    backends = Backends({BACKEND: app} if app is not None else {})
    return ProjectSessionArchive(
        lambda: spaces, lambda: backends, settings=SessionArchiveSettings(**settings)
    )


REF = SessionRef(backend=BACKEND, session_id="s1")


def _files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_archive_copy_has_only_that_session(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    app_a = _app(tmp_path / "a")
    _write_session(app_a, folder, "s1")
    archive = _archive({"p": folder}, app_a)
    assert archive.archive("p", REF) == 2
    sessions = folder / ".agent-console" / "sessions"
    assert _files(sessions) == [
        "fake-agent/s1/s1.jsonl",
        "fake-agent/s1/s1/subagents/agent-1.jsonl",
    ]
    assert not any(".credentials" in n or "settings" in n for n in _files(folder))


def test_other_app_continues_from_archive(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    app_a, app_b = _app(tmp_path / "a"), _app(tmp_path / "b")
    _write_session(app_a, folder, "s1")
    _archive({"p": folder}, app_a).archive("p", REF)
    other = _archive({"p": folder}, app_b)
    assert other.state("p", REF) == KnownSessionStates.ARCHIVED
    assert other.prepare("p", REF) == KnownSessionStates.ARCHIVED
    assert other.state("p", REF) == KnownSessionStates.AVAILABLE
    restored = _files(app_b.root.parent)
    key = _key(os.path.abspath(folder))
    assert restored == [f"projects/{key}/s1.jsonl", f"projects/{key}/s1/subagents/agent-1.jsonl"]


def test_newer_archive_replaces_stale_local_copy(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    app_a, app_b = _app(tmp_path / "a"), _app(tmp_path / "b")
    local_a = _write_session(app_a, folder, "s1", "a-turn1\n")
    a = _archive({"p": folder}, app_a)
    b = _archive({"p": folder}, app_b)
    a.archive("p", REF)
    assert b.prepare("p", REF) == KnownSessionStates.ARCHIVED
    # B가 이어 가서 원본이 자람 → 보관
    b_file = app_b.root / _key(os.path.abspath(folder)) / "s1.jsonl"
    future = time.time() + 5
    b_file.write_text("a-turn1\nb-turn2\n", encoding="utf-8")
    os.utime(b_file, (future, future))
    b.archive("p", REF)
    # A의 원본은 옛것: 보내기 직전에 보관 사본으로 바꾼다
    assert a.state("p", REF) == KnownSessionStates.AVAILABLE
    assert a.prepare("p", REF) == KnownSessionStates.ARCHIVED
    assert (local_a / "s1.jsonl").read_text(encoding="utf-8") == "a-turn1\nb-turn2\n"
    # 같은 사본이면 다시 바꾸지 않는다
    assert a.prepare("p", REF) == KnownSessionStates.AVAILABLE


def test_disabled_archive_writes_nothing_and_other_app_is_missing(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    app_a, app_b = _app(tmp_path / "a"), _app(tmp_path / "b")
    _write_session(app_a, folder, "s1")
    off = _archive({"p": folder}, app_a, enabled=False)
    assert off.archive("p", REF) is None
    assert not (folder / ".agent-console" / "sessions").exists()
    other = _archive({"p": folder}, app_b, enabled=False)
    assert other.state("p", REF) == KnownSessionStates.MISSING
    assert other.prepare("p", REF) == KnownSessionStates.MISSING


def test_relocated_folder_same_app_is_relocatable(tmp_path: Path) -> None:
    old = tmp_path / "old"
    old.mkdir()
    app = _app(tmp_path / "a")
    _write_session(app, old, "s1")
    new = tmp_path / "new"
    shutil.move(str(old), str(new))  # [경로 다시 지정]: 같은 등록 id가 새 경로를 가리킨다
    archive = _archive({"p": new}, app, enabled=False)
    assert archive.state("p", REF) == KnownSessionStates.RELOCATABLE
    assert archive.prepare("p", REF) == KnownSessionStates.RELOCATABLE
    assert archive.state("p", REF) == KnownSessionStates.AVAILABLE


def test_backend_without_archive_is_not_applicable(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    archive = _archive({"p": folder}, None)
    assert archive.state("p", REF) == KnownSessionStates.NOT_APPLICABLE
    assert archive.prepare("p", REF) == KnownSessionStates.NOT_APPLICABLE
    assert archive.archive("p", REF) is None
    assert archive.state(None, REF) == KnownSessionStates.NOT_APPLICABLE
    assert archive.state("ghost", REF) == KnownSessionStates.NOT_APPLICABLE
    unsafe = SessionRef(backend=BACKEND, session_id="../x")
    assert _archive({"p": folder}, _app(tmp_path / "a")).archive_dir("p", unsafe) is None


def test_planted_archive_files_are_not_restored(tmp_path: Path) -> None:
    """보관 폴더(사용자 폴더 — git 클론 등)에 다른 파일이 있어도 자격 폴더에는 세션 파일만 쓴다."""
    folder = tmp_path / "proj"
    saved = folder / ".agent-console" / "sessions" / BACKEND / "s1"
    saved.mkdir(parents=True)
    (saved / "s1.jsonl").write_text("x\n", encoding="utf-8")
    (saved / ".credentials.json").write_text("planted", encoding="utf-8")
    (saved / "settings.json").write_text("planted", encoding="utf-8")
    app = _app(tmp_path / "b")
    assert _archive({"p": folder}, app).prepare("p", REF) == KnownSessionStates.ARCHIVED
    assert _files(app.root.parent) == [f"projects/{_key(os.path.abspath(folder))}/s1.jsonl"]


class Runs:
    def __init__(self, project: str | None) -> None:
        self.project = project

    def get(self, run_id: str) -> Any:
        class _Run:
            project_id = self.project

        return _Run()


def _event(seq: int, type: str, node_path: list[str], **payload: Any) -> RunEvent:
    return RunEvent(
        event_id=f"e{seq}",
        run_id="r1",
        seq=seq,
        ts=float(seq),
        node_path=node_path,
        type=type,
        payload=payload,
    )


def _archiver(
    archive: ProjectSessionArchive, project: str | None
) -> tuple[SessionArchiver, list[Callable[[], None]]]:
    jobs: list[Callable[[], None]] = []
    return SessionArchiver(archive, lambda: Runs(project), submit=jobs.append), jobs


def test_archiver_copies_when_node_ends(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    app = _app(tmp_path / "a")
    _write_session(app, folder, "s1")
    archive = _archive({"p": folder}, app)
    archiver, jobs = _archiver(archive, "p")
    archiver(_event(1, "agent.session_started", ["a"], session_id="s1", backend=BACKEND))
    archiver(_event(2, "agent.session_started", ["a", "sub"], session_id="x", backend=BACKEND))
    assert jobs == []
    archiver(_event(3, "node.completed", ["a"], status="succeeded"))
    assert len(jobs) == 1
    jobs.pop()()
    assert (folder / ".agent-console" / "sessions" / BACKEND / "s1" / "s1.jsonl").is_file()
    archiver(_event(4, "run.completed", [], status="completed"))
    assert jobs == []


def test_archiver_failure_is_only_an_info_issue(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    app = _app(tmp_path / "a")
    _write_session(app, folder, "s1")
    archive = _archive({"p": folder}, app)
    (folder / ".agent-console").mkdir()
    (folder / ".agent-console" / "sessions").write_text("not a folder", encoding="utf-8")
    archiver, jobs = _archiver(archive, "p")
    archiver(_event(1, "agent.session_started", ["a"], session_id="s1", backend=BACKEND))
    archiver(_event(2, "run.failed", [], status="failed"))
    jobs.pop()()
    issues = archive.warnings()
    assert [i.code for i in issues] == ["records.session_archive_failed"]
    assert issues[0].severity == "info"


def test_archiver_skips_runs_without_project_and_when_disabled(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    app = _app(tmp_path / "a")
    _write_session(app, folder, "s1")
    archiver, jobs = _archiver(_archive({"p": folder}, app), None)
    archiver(_event(1, "agent.session_started", ["a"], session_id="s1", backend=BACKEND))
    archiver(_event(2, "node.completed", ["a"]))
    jobs.pop()()
    assert not (folder / ".agent-console" / "sessions").exists()
    off, off_jobs = _archiver(_archive({"p": folder}, app, enabled=False), "p")
    off(_event(1, "agent.session_started", ["a"], session_id="s1", backend=BACKEND))
    off(_event(2, "node.completed", ["a"]))
    assert off_jobs == []
