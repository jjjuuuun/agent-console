"""5.7R.33y3 X38 세션 기록 보관·복원 공용 부품(``JsonlFolderSessionArchive`` 등)."""

from __future__ import annotations

import os
from pathlib import Path

from agent_console_contracts import KnownSessionStates
from agent_console_runtime import (
    ArchiveFile,
    BackendSessionArchives,
    JsonlFolderSessionArchive,
    SessionRef,
    copy_files,
    session_archive_of,
    session_files_in,
)


def _key(cwd: str) -> str:
    return "k" + "".join(ch if ch.isalnum() else "-" for ch in cwd)


def _session(root: Path, cwd: str, sid: str, *, sub: bool = True) -> Path:
    folder = root / _key(os.path.abspath(cwd))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{sid}.jsonl").write_text('{"turn":1}\n', encoding="utf-8")
    if sub:
        (folder / sid / "subagents").mkdir(parents=True)
        (folder / sid / "subagents" / "agent-x.jsonl").write_text("{}\n", encoding="utf-8")
    return folder


def _ref(sid: str = "s1") -> SessionRef:
    return SessionRef(backend="b", session_id=sid)


def test_files_only_that_session(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    folder = _session(root, "/work/p", "s1")
    (folder / "s2.jsonl").write_text("other\n", encoding="utf-8")
    (folder / ".credentials.json").write_text("secret", encoding="utf-8")
    (root.parent / ".credentials.json").write_text("secret", encoding="utf-8")
    (root.parent / "settings.json").write_text("{}", encoding="utf-8")
    archive = JsonlFolderSessionArchive(root, _key)
    files = archive.files(_ref(), cwd="/work/p")
    assert files is not None
    assert sorted(f.name for f in files) == ["s1.jsonl", "s1/subagents/agent-x.jsonl"]
    assert archive.files(_ref("nope"), cwd="/work/p") is None


def test_status_available_relocatable_missing(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _session(root, "/work/old", "s1")
    archive = JsonlFolderSessionArchive(root, _key)
    assert archive.status(_ref(), cwd="/work/old") == KnownSessionStates.AVAILABLE
    assert archive.status(_ref(), cwd="/work/new") == KnownSessionStates.RELOCATABLE
    assert archive.status(_ref("s9"), cwd="/work/new") == KnownSessionStates.MISSING
    assert archive.status(_ref("../s1"), cwd="/work/old") == KnownSessionStates.MISSING


def test_restore_relocate_copies_old_key_to_new(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _session(root, "/work/old", "s1")
    archive = JsonlFolderSessionArchive(root, _key)
    assert archive.restore(None, _ref(), cwd="/work/new") is True
    new = root / _key(os.path.abspath("/work/new"))
    assert (new / "s1.jsonl").is_file()
    assert (new / "s1" / "subagents" / "agent-x.jsonl").is_file()
    assert archive.status(_ref(), cwd="/work/new") == KnownSessionStates.AVAILABLE
    assert archive.restore(None, _ref("s9"), cwd="/work/new") is False


def test_restore_from_archive_takes_only_session_files(tmp_path: Path) -> None:
    root = tmp_path / "app" / "projects"
    saved = tmp_path / "saved" / "s1"
    saved.mkdir(parents=True)
    (saved / "s1.jsonl").write_text("x\n", encoding="utf-8")
    (saved / ".credentials.json").write_text("planted", encoding="utf-8")
    (saved / "s2.jsonl").write_text("planted", encoding="utf-8")
    archive = JsonlFolderSessionArchive(root, _key)
    assert archive.restore(saved, _ref(), cwd="/work/p") is True
    written = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert written == [f"{_key(os.path.abspath('/work/p'))}/s1.jsonl"]
    assert not (root.parent / ".credentials.json").exists()
    assert archive.restore(tmp_path / "empty", _ref("s3"), cwd="/work/p") is False


def test_copy_files_skips_unsafe_names_and_links(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("a", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(src)
    dest = tmp_path / "dest"
    count = copy_files(
        [
            ArchiveFile(src, "ok/a.txt"),
            ArchiveFile(src, "../escape.txt"),
            ArchiveFile(src, "/abs.txt"),
            ArchiveFile(link, "link.txt"),
            ArchiveFile(tmp_path / "none", "none.txt"),
        ],
        dest,
    )
    assert count == 1
    assert (dest / "ok" / "a.txt").read_text(encoding="utf-8") == "a"
    assert not (tmp_path / "escape.txt").exists()
    assert sorted(p.name for p in dest.rglob("*") if p.is_file()) == ["a.txt"]


def test_session_files_in_skips_symlinked_subfolders(tmp_path: Path) -> None:
    folder = _session(tmp_path, "/w", "s1", sub=False)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("x", encoding="utf-8")
    (folder / "s1").symlink_to(outside, target_is_directory=True)
    assert [f.name for f in session_files_in(folder, "s1")] == ["s1.jsonl"]


class _Capable:
    def __init__(self, archive: object | None) -> None:
        self._archive = archive

    def session_archive(self) -> object | None:
        return self._archive


class _Broken:
    def session_archive(self) -> object:
        raise RuntimeError("boom")


def test_backend_lookup_not_applicable_cases(tmp_path: Path) -> None:
    archive = JsonlFolderSessionArchive(tmp_path, _key)
    backends: dict[str, object] = {
        "yes": _Capable(archive),
        "none": _Capable(None),
        "plain": object(),
        "broken": _Broken(),
    }
    found = BackendSessionArchives(backends.get)
    assert found.get("yes") is archive
    assert found.get("none") is None
    assert found.get("plain") is None
    assert found.get("broken") is None
    assert found.get("unknown") is None
    assert session_archive_of(_Capable("not an archive")) is None
