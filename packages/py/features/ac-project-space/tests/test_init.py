"""등록 시점 초기화: 없을 때만 만들고, 있으면 채택하고, 쓸 수 없으면 알린다."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_console_contracts import ProjectManifest
from agent_console_project_space import (
    default_gitignore_template,
    init_space,
    open_space,
    read_manifest,
)
from agent_console_project_space.testing import ReadOnlyFiles, WriteFailsFiles, snapshot_tree


def test_new_folder_gets_manifest_and_gitignore(folder: Path, manifest: ProjectManifest) -> None:
    result = init_space(folder, manifest=manifest)
    assert (result.manifest_state, result.gitignore_state) == ("created", "created")
    assert result.config_writable is True
    assert result.manifest is not None
    assert result.manifest.manifest.name == "결제 서비스"
    root = folder / ".agent-console"
    assert sorted(p.name for p in root.iterdir()) == [".gitignore", "project.yaml"]
    assert (root / ".gitignore").read_text(encoding="utf-8") == default_gitignore_template()


def test_second_init_changes_nothing(folder: Path, manifest: ProjectManifest) -> None:
    init_space(folder, manifest=manifest)
    before = snapshot_tree(folder)
    other = ProjectManifest(id="other", name="다른 이름")
    again = init_space(folder, manifest=other)
    assert (again.manifest_state, again.gitignore_state) == ("adopted", "adopted")
    assert again.manifest is not None
    assert again.manifest.manifest.id == "payments"
    assert snapshot_tree(folder) == before


def test_existing_manifest_is_adopted_and_gitignore_added(folder: Path) -> None:
    root = folder / ".agent-console"
    root.mkdir()
    text = "# 손으로 쓴 매니페스트\nformat: 1\nid: team-x\nname: 팀 X\nfoo: bar\n"
    (root / "project.yaml").write_text(text, encoding="utf-8")
    result = init_space(folder, manifest=ProjectManifest(id="zzz", name="zzz"))
    assert result.manifest_state == "adopted"
    assert result.gitignore_state == "created"
    assert (root / "project.yaml").read_text(encoding="utf-8") == text


def test_users_gitignore_is_kept(folder: Path, manifest: ProjectManifest) -> None:
    root = folder / ".agent-console"
    root.mkdir()
    (root / ".gitignore").write_bytes(b"mine/\r\n")
    result = init_space(folder, manifest=manifest)
    assert result.gitignore_state == "adopted"
    assert (root / ".gitignore").read_bytes() == b"mine/\r\n"
    assert result.manifest_state == "created"


def test_broken_manifest_writes_nothing(folder: Path, manifest: ProjectManifest) -> None:
    root = folder / ".agent-console"
    root.mkdir()
    (root / "project.yaml").write_text("id: [", encoding="utf-8")
    (root / "agents").mkdir()
    (root / "agents" / "a.yaml").write_text("id: a\nname: n\n", encoding="utf-8")
    before = snapshot_tree(folder)
    result = init_space(folder, manifest=manifest)
    assert result.manifest_state == "invalid"
    assert result.manifest is None
    assert result.manifest_issue is not None
    assert result.manifest_issue.reason == "yaml"
    assert result.gitignore_state == "skipped"
    assert snapshot_tree(folder) == before


def test_read_only_folder(folder: Path, manifest: ProjectManifest) -> None:
    files = ReadOnlyFiles()
    result = init_space(folder, manifest=manifest, files=files)
    assert result.config_writable is False
    assert (result.manifest_state, result.gitignore_state) == ("absent", "skipped")
    assert files.writes == []
    assert snapshot_tree(folder) == {}


def test_read_only_folder_with_manifest_is_adopted(folder: Path, manifest: ProjectManifest) -> None:
    init_space(folder, manifest=manifest)
    (folder / ".agent-console" / ".gitignore").unlink()
    result = init_space(folder, manifest=manifest, files=ReadOnlyFiles())
    assert result.manifest_state == "adopted"
    assert result.gitignore_state == "skipped"
    assert result.config_writable is False


def test_write_failure_means_not_writable(folder: Path, manifest: ProjectManifest) -> None:
    result = init_space(folder, manifest=manifest, files=WriteFailsFiles())
    assert result.config_writable is False
    assert result.manifest_state == "absent"


def test_gitignore_failure_after_manifest(folder: Path, manifest: ProjectManifest) -> None:
    class GitignoreFails(WriteFailsFiles):
        def write_bytes(self, path: Path, data: bytes) -> None:
            super(WriteFailsFiles, self).write_bytes(path, data)

    result = init_space(folder, manifest=manifest, files=GitignoreFails())
    assert result.manifest_state == "created"
    assert result.gitignore_state == "skipped"
    assert result.config_writable is False


def test_custom_template_and_config_dir(folder: Path, manifest: ProjectManifest) -> None:
    init_space(folder, manifest=manifest, config_dir=".ac", gitignore_template="only/\n")
    assert (folder / ".ac" / ".gitignore").read_text(encoding="utf-8") == "only/\n"
    assert read_manifest(open_space(folder, config_dir=".ac")) is not None


# ---- .gitignore 틀을 실제 git으로 검사 ------------------------------------------------------
def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


@pytest.fixture
def repo(folder: Path, manifest: ProjectManifest) -> Path:
    if _git(folder, "--version").returncode != 0:
        pytest.skip("git is not available")
    assert _git(folder, "init", "-q").returncode == 0
    init_space(folder, manifest=manifest)
    return folder


IGNORED = [
    ".state/x.tmp",
    ".state/backups/project-20261028T093005Z.yaml",
    "memory.sqlite3",
    "memory.sqlite3-wal",
    "memory.sqlite3-shm",
    "records.sqlite3",
    "records.sqlite3-journal",
    "records.sqlite3-wal",
    "sessions/claude/abc/session.jsonl",
    "claude/credentials.json",
]
KEPT = [
    "project.yaml",
    ".gitignore",
    "graphs/g1.yaml",
    "agents/a1.yaml",
    "resources/r1.yaml",
    "resources/r1/content.md",
    # 이름이 겹쳐도 구성 안의 것은 제외되지 않는다(틀의 줄은 이 폴더 바로 아래에만 적용)
    "resources/claude/content.md",
    "resources/sessions/content.md",
    "resources/memory.sqlite3-notes/content.md",
    "agents/.state/x.yaml",
]


@pytest.mark.parametrize("name", IGNORED)
def test_template_ignores_runtime_files(repo: Path, name: str) -> None:
    path = repo / ".agent-console" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    result = _git(repo, "check-ignore", "-q", f".agent-console/{name}")
    assert result.returncode == 0, name


@pytest.mark.parametrize("name", KEPT)
def test_template_keeps_definition_files(repo: Path, name: str) -> None:
    path = repo / ".agent-console" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    result = _git(repo, "check-ignore", "-q", f".agent-console/{name}")
    assert result.returncode == 1, name


def test_template_has_no_inline_comments() -> None:
    for line in default_gitignore_template().splitlines():
        stripped = line.strip()
        assert not stripped or stripped.startswith("#") or "#" not in stripped
