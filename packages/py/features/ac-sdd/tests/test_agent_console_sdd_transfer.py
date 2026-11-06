"""가져오기·내보내기·가져오기 파일 목록(design §6R.1.2·§6R.13, §6R.18 Q13)과 경로 공격 거부."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from agent_console_contracts.sdd import SpecDefinition
from agent_console_sdd import (
    LocalSpecFiles,
    SpecFiles,
    SpecPathError,
    check_project_path,
    export_documents,
    guess_title,
    import_documents,
    list_import_files,
)
from agent_console_sdd.testing import MemorySpecFiles, memory_repository

RESERVED = (".agent-console",)
MD = (".md", ".markdown")
BAD_PATHS = ("../x.md", "/etc/passwd", "a/../../x.md", "C:/x.md", "a\\b.md", "", "a//b.md")


def test_check_project_path() -> None:
    assert check_project_path("docs/a.md") == "docs/a.md"
    assert check_project_path("", allow_root=True) == ""
    for bad in BAD_PATHS:
        with pytest.raises(SpecPathError) as err:
            check_project_path(bad)
        assert err.value.details["reason"] == "invalid"
    with pytest.raises(SpecPathError) as reserved:
        check_project_path(".Agent-Console/specs", reserved=RESERVED)
    assert reserved.value.details["reason"] == "reserved"
    files = MemorySpecFiles({"real/a.md": "x"}, links=["linked"])
    with pytest.raises(SpecPathError) as link:
        check_project_path("linked/a.md", files)
    assert link.value.details["reason"] == "link"


def test_import_copies_and_rejects_attacks() -> None:
    files = MemorySpecFiles(
        {
            "specs/old/req.md": "# 요구사항\n\n**R1** a\n",
            "notes/req.md": "본문만\n",
            ".agent-console/specs/x.md": "앱 구성",
        },
        links=["linked.md"],
    )
    got = import_documents(files, ["specs/old/req.md", "notes/req.md"], reserved=RESERVED)
    assert [(d.id, d.title, d.file) for d in got.documents] == [
        ("req", "요구사항", "req.md"),
        ("req-2", "req", "req-2.md"),
    ]
    assert got.contents == {
        "req.md": "# 요구사항\n\n**R1** a\n".encode(),
        "req-2.md": "본문만\n".encode(),
    }
    for bad in [*BAD_PATHS, "linked.md", ".agent-console/specs/x.md"]:
        with pytest.raises(SpecPathError):
            import_documents(files, [bad], reserved=RESERVED)
    with pytest.raises(SpecPathError) as missing:
        import_documents(files, ["nope.md"])
    assert missing.value.details["reason"] == "not_found"

    repo = memory_repository()
    stored = repo.create(name="imported", documents=got.documents, contents=got.contents)
    assert repo.read_files(stored.id) == got.contents
    # 원본과 연결되지 않는다: 원본을 바꿔도 스펙은 그대로.
    files.files["specs/old/req.md"] = b"changed"
    assert repo.read_files(stored.id)["req.md"] != b"changed"


def _spec() -> SpecDefinition:
    return SpecDefinition.model_validate(
        {
            "kind": "spec",
            "id": "s",
            "name": "s",
            "documents": [
                {"id": "a", "title": "A", "file": "a.md"},
                {"id": "b", "title": "B", "file": "sub/b.md"},
                {"id": "c", "title": "C", "file": "c.md"},
            ],
        }
    )


def test_export_overwrite_and_rejects() -> None:
    files = MemorySpecFiles({"docs/spec/a.md": "old"}, links=["linkdir"])
    contents = {"a.md": b"A", "sub/b.md": b"B", "c.md": None}
    result = export_documents(_spec(), contents, files, "docs/spec", reserved=RESERVED)
    assert result.written == ["sub/b.md"]
    assert result.skipped == ["a.md", "c.md"]
    assert files.files["docs/spec/a.md"] == b"old"
    again = export_documents(
        _spec(), contents, files, "docs/spec", overwrite=True, reserved=RESERVED
    )
    assert again.written == ["a.md", "sub/b.md"]
    assert files.files["docs/spec/a.md"] == b"A"
    root = export_documents(_spec(), contents, files, "", reserved=RESERVED)
    assert root.to_dir == "."
    assert "a.md" in root.written
    for bad in ("../out", "/tmp/out", ".agent-console/specs", "linkdir", "linkdir/deeper"):
        with pytest.raises(SpecPathError):
            export_documents(_spec(), contents, files, bad, reserved=RESERVED)


def test_list_import_files() -> None:
    files = MemorySpecFiles(
        {
            "docs/b.md": "# 둘째\n",
            "docs/A.markdown": "```\n# 코드 안\n```\n\n# 첫째 제목 #\n",
            "docs/.hidden.md": "# 숨김\n",
            "docs/note.txt": "텍스트",
            "docs/deep/c.md": "# 재귀 안 함\n",
            "docs/plain.md": "제목 없음\n",
        },
        links=["docs/link.md"],
    )
    listing = list_import_files(files, "docs", extensions=MD, reserved=RESERVED)
    assert [(f.name, f.title_guess) for f in listing.files] == [
        ("A.markdown", "첫째 제목"),
        ("b.md", "둘째"),
        ("plain.md", "plain"),
    ]
    assert listing.files[1].size == len("# 둘째\n".encode())
    assert listing.truncated is False
    small = list_import_files(files, "docs", extensions=MD, limit=2)
    assert len(small.files) == 2
    assert small.truncated is True
    assert list_import_files(files, "", extensions=[".md"]).files == []
    for bad, reason in (
        ("missing", "not_found"),
        ("docs/b.md", "not_directory"),
        ("../x", "invalid"),
    ):
        with pytest.raises(SpecPathError) as err:
            list_import_files(files, bad, extensions=MD)
        assert err.value.details["reason"] == reason
    with pytest.raises(SpecPathError):
        list_import_files(files, ".agent-console", extensions=MD, reserved=RESERVED)


def test_list_import_files_subfolders() -> None:
    """6R.20d: 바로 아래 하위 폴더만(재귀 없음) — 숨김·링크·루트 예약 폴더 제외, 상한 truncated."""
    files = MemorySpecFiles(
        {
            "docs/zeta/a.md": "# a\n",
            "docs/Alpha/deep/b.md": "# b\n",
            "docs/.git/c.md": "x",
            "docs/.agent-console/d.md": "예약은 루트 첫 구성요소만",
            "docs/top.md": "# 위\n",
            ".agent-console/specs/s.md": "앱 구성",
            "other/x.md": "x",
        },
        links=["docs/linked", "linked-root"],
    )
    listing = list_import_files(files, "docs", extensions=MD, reserved=RESERVED)
    assert [d.name for d in listing.dirs] == [
        "Alpha",
        "zeta",
    ]  # 숨김(.git·.agent-console)·링크 제외
    assert [f.name for f in listing.files] == ["top.md"]
    root = list_import_files(files, "", extensions=MD, reserved=RESERVED)
    assert [d.name for d in root.dirs] == ["docs", "other"]  # 예약·링크 제외
    deeper = list_import_files(files, "docs/Alpha", extensions=MD, reserved=RESERVED)
    assert [d.name for d in deeper.dirs] == ["deep"]
    assert deeper.files == []
    small = list_import_files(files, "docs", extensions=MD, limit=1)
    assert [d.name for d in small.dirs] == ["Alpha"]
    assert small.truncated is True
    assert list_import_files(files, "docs/zeta", extensions=MD).dirs == []


def test_list_import_files_reserved_folder_is_hidden_case_insensitive() -> None:
    files = MemorySpecFiles({".AGENT-CONSOLE/x.md": "x", "Specs/y.md": "y"})
    root = list_import_files(files, "", extensions=MD, reserved=(".agent-console", "specs"))
    assert root.dirs == []


def test_guess_title() -> None:
    assert guess_title(b"intro\n## sub\n# Main\n", "f") == "Main"
    assert guess_title(b"#not-heading\n", "f") == "f"


@pytest.mark.skipif(sys.platform == "win32", reason="심볼릭 링크 권한")
def test_local_files_guard(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.md").write_text("# A\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("# 밖\n", encoding="utf-8")
    os.symlink(outside, root / "escape")
    os.symlink(outside / "secret.md", root / "docs" / "linked.md")
    files = LocalSpecFiles(root)
    assert isinstance(files, SpecFiles)
    assert files.read("docs/a.md") == b"# A\n"
    assert files.read("docs/none.md") is None
    listing = list_import_files(files, "docs", extensions=MD)
    assert [f.name for f in listing.files] == ["a.md"]  # 링크 제외
    assert [d.name for d in list_import_files(files, "", extensions=MD).dirs] == ["docs"]
    for bad in ("escape/secret.md", "docs/linked.md"):
        with pytest.raises(SpecPathError):
            import_documents(files, [bad])
        with pytest.raises(SpecPathError):
            files.read(bad)  # 구현도 폴더 밖을 막는다
    with pytest.raises(SpecPathError):
        export_documents(_spec(), {"a.md": b"x"}, files, "escape")
    result = export_documents(_spec(), {"a.md": b"x", "sub/b.md": b"y"}, files, "out")
    assert result.written == ["a.md", "sub/b.md"]
    assert (root / "out" / "sub" / "b.md").read_bytes() == b"y"
    assert not (outside / "a.md").exists()
