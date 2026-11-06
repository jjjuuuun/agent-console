"""ProjectSpecFiles: 폴더 안만(§PI.5), 앱 구성 폴더 예약, 링크·``..``·절대 경로 거부, 쓰기 불가 409,
목록(§6R.18 Q13 ``SpecFiles.list``)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_console_contracts import ErrorCodes
from agent_console_contracts.sdd import SpecDefinition
from agent_console_link_projects_sdd import ProjectSpecFiles, normalize_reserved
from agent_console_project_space import ConfigReadonly
from agent_console_sdd import SpecFiles, SpecPathError, export_documents, list_import_files


def _reason(exc: pytest.ExceptionInfo[SpecPathError]) -> str:
    return str(exc.value.details["reason"])


def test_is_spec_files_and_reads_writes_inside(tmp_path: Path) -> None:
    files = ProjectSpecFiles(tmp_path, reserved=[".agent-console"])
    assert isinstance(files, SpecFiles)
    files.write("docs/a.md", b"# A\n")
    assert (tmp_path / "docs" / "a.md").read_bytes() == b"# A\n"
    assert files.read("docs/a.md") == b"# A\n"
    assert files.read("docs/none.md") is None
    assert files.exists("docs")
    assert not files.exists("nothing")
    assert [e.name for e in files.list("docs")] == ["a.md"]


@pytest.mark.parametrize(
    "path", ["../x.md", "/etc/passwd", "a/../../x.md", "a\\b.md", "C:/x.md", "a//b.md"]
)
def test_rejects_paths_leaving_the_folder(tmp_path: Path, path: str) -> None:
    files = ProjectSpecFiles(tmp_path / "p")
    (tmp_path / "p").mkdir()
    with pytest.raises(SpecPathError) as exc:
        files.read(path)
    assert exc.value.code == ErrorCodes.FOLDERS_INVALID_PATH
    with pytest.raises(SpecPathError):
        files.write(path, b"x")
    assert not (tmp_path / "x.md").exists()


@pytest.mark.parametrize(
    "path", [".agent-console", ".agent-console/specs/a.md", ".AGENT-CONSOLE/x.md", "out/gen/a.md"]
)
def test_reserved_paths_are_refused_everywhere(tmp_path: Path, path: str) -> None:
    files = ProjectSpecFiles(tmp_path, reserved=[".agent-console", "out/gen/"])
    for op in (
        lambda: files.read(path),
        lambda: files.write(path, b"x"),
        lambda: files.exists(path),
        lambda: files.list(path),
        lambda: files.is_link(path),
    ):
        with pytest.raises(SpecPathError) as exc:
            op()
        assert _reason(exc) == "reserved"
    assert not (tmp_path / ".agent-console").exists()
    assert not (tmp_path / "out").exists()


def test_reserved_prefix_is_not_a_name_prefix(tmp_path: Path) -> None:
    files = ProjectSpecFiles(tmp_path, reserved=[".agent-console"])
    files.write(".agent-console-notes/a.md", b"ok")
    assert files.read(".agent-console-notes/a.md") == b"ok"


def test_list_hides_reserved_entries(tmp_path: Path) -> None:
    (tmp_path / ".agent-console").mkdir()
    (tmp_path / "out" / "gen").mkdir(parents=True)
    (tmp_path / "a.md").write_text("# a", encoding="utf-8")
    files = ProjectSpecFiles(tmp_path, reserved=[".agent-console", "out/gen"])
    assert sorted(e.name for e in files.list("")) == ["a.md", "out"]
    assert files.list("out") == []


@pytest.mark.skipif(os.name == "nt", reason="symlink needs privileges on Windows")
def test_links_pointing_outside_are_refused(tmp_path: Path) -> None:
    folder = tmp_path / "p"
    (folder / "docs").mkdir(parents=True)
    outside = tmp_path / "secret"
    outside.mkdir()
    (outside / "s.md").write_text("# secret", encoding="utf-8")
    (folder / "ext").symlink_to(outside, target_is_directory=True)
    (folder / "docs" / "l.md").symlink_to(outside / "s.md")
    files = ProjectSpecFiles(folder)
    for path in ("ext/s.md", "docs/l.md"):
        with pytest.raises(SpecPathError) as exc:
            files.read(path)
        assert _reason(exc) == "link"
    with pytest.raises(SpecPathError):
        files.write("ext/new.md", b"x")
    assert not (outside / "new.md").exists()
    assert files.is_link("ext") is True
    with pytest.raises(SpecPathError):
        files.list("ext")


def test_readonly_folder_refuses_writes_with_409_code(tmp_path: Path) -> None:
    files = ProjectSpecFiles(tmp_path, writable=False)
    with pytest.raises(ConfigReadonly) as exc:
        files.write("a.md", b"x")
    assert exc.value.code == ErrorCodes.PROJECT_CONFIG_READONLY
    assert not (tmp_path / "a.md").exists()
    assert files.read("a.md") is None  # 읽기는 된다


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX permissions as a normal user",
)
def test_permission_error_becomes_config_readonly(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        files = ProjectSpecFiles(tmp_path)
        with pytest.raises(ConfigReadonly):
            files.write("locked/a.md", b"x")
    finally:
        locked.chmod(0o755)


def test_injected_realpath_outside_is_link(tmp_path: Path) -> None:
    def fake(path: str) -> str:
        return "/elsewhere/x" if path.endswith("a.md") else path

    files = ProjectSpecFiles(tmp_path, realpath=fake)
    with pytest.raises(SpecPathError) as exc:
        files.read("a.md")
    assert _reason(exc) == "link"


def test_list_marks_dirs_resolving_outside_as_links(tmp_path: Path) -> None:
    """6R.20d: 링크로 안 보여도 실제 경로가 폴더 밖인 하위 폴더는 링크로 표시(목록에서 빠짐)."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "away").mkdir()
    (tmp_path / "a.md").write_text("# a", encoding="utf-8")

    def fake(path: str) -> str:
        return "/elsewhere/away" if path.endswith("away") else path

    files = ProjectSpecFiles(tmp_path, realpath=fake)
    by_name = {e.name: e for e in files.list("")}
    assert by_name["away"].is_link is True
    assert by_name["docs"].is_link is False
    listing = list_import_files(files, "", extensions=[".md"])
    assert [d.name for d in listing.dirs] == ["docs"]
    with pytest.raises(SpecPathError) as exc:
        list_import_files(files, "away", extensions=[".md"])
    assert _reason(exc) == "link"


def test_import_listing_subfolders_hide_config_folder(tmp_path: Path) -> None:
    """6R.20d: 구성 폴더(예약 경로 전체, 대소문자 무시)·숨김 폴더는 하위 폴더 목록에 없다."""
    (tmp_path / ".agent-console" / "specs").mkdir(parents=True)
    (tmp_path / "docs" / "nested").mkdir(parents=True)
    (tmp_path / "build" / "gen").mkdir(parents=True)
    (tmp_path / "build" / "keep").mkdir(parents=True)
    files = ProjectSpecFiles(tmp_path, reserved=[".agent-console", "build/gen"])
    root = list_import_files(files, "", extensions=[".md"], reserved=[".agent-console"])
    assert [d.name for d in root.dirs] == ["build", "docs"]
    build = list_import_files(files, "build", extensions=[".md"])
    assert [d.name for d in build.dirs] == ["keep"]
    assert [d.name for d in list_import_files(files, "docs", extensions=[".md"]).dirs] == ["nested"]


@pytest.mark.skipif(os.name == "nt", reason="symlink needs privileges on Windows")
def test_import_listing_subfolders_skip_symlinks(tmp_path: Path) -> None:
    folder = tmp_path / "p"
    (folder / "docs").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    (folder / "ext").symlink_to(tmp_path / "outside", target_is_directory=True)
    (folder / "inner").symlink_to(folder / "docs", target_is_directory=True)
    listing = list_import_files(ProjectSpecFiles(folder), "", extensions=[".md"])
    assert [d.name for d in listing.dirs] == ["docs"]


def _spec() -> SpecDefinition:
    return SpecDefinition.model_validate(
        {
            "kind": "spec",
            "id": "s",
            "name": "S",
            "documents": [{"id": "a", "title": "A", "file": "a.md"}],
        }
    )


def test_sdd_helpers_use_it(tmp_path: Path) -> None:
    """ac-sdd 가져오기 목록·내보내기가 이 파일 접근 위에서 돈다(예약 폴더 거부 포함)."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "plan.md").write_text("# 계획\n", encoding="utf-8")
    files = ProjectSpecFiles(tmp_path, reserved=[".cfg"])
    listing = list_import_files(files, "docs", extensions=[".md"])
    assert [(f.name, f.title_guess) for f in listing.files] == [("plan.md", "계획")]
    with pytest.raises(SpecPathError):
        list_import_files(files, ".cfg", extensions=[".md"])
    with pytest.raises(SpecPathError):
        export_documents(_spec(), {"a.md": b"x"}, files, ".cfg/out")
    result = export_documents(_spec(), {"a.md": b"x"}, files, "out")
    assert result.written == ["a.md"]
    assert not (tmp_path / ".cfg").exists()


def test_normalize_reserved() -> None:
    assert normalize_reserved([" /a/ ", "A", "", "b/c"]) == ("a", "b/c")
