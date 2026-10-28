"""5.7R.30 후속: `claude-code-jsonl`은 앱에 등록된 프로젝트 폴더의 세션만 읽는다.

빈 HOME 픽스처의 `~/.claude/projects`에 프로젝트 둘(`/work/demo`·`/work/other`)과 앱 전용 자격 폴더
(5.7R.30b: `<앱 workspace>/.state/claude/projects`)를 두고 범위(`current`·`registered`)·등록 없음·
넓은 roots·범위 변경 뒤 정리를 확인한다. 두 루트 모두 같은 범위 필터를 지난다. 실제 `~/.claude`는
읽지 않는다.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.logs import LogSettings
from agent_console_logs import LogIngestor, LogRegistries, ProjectFolders
from agent_console_logs.testing import MemoryLogIndex, RecordingOpen
from agent_console_logs_claude import ClaudeCodeJsonlSource, project_key

DATA = Path(__file__).parent / "data" / "claude_config" / "projects" / "-work-demo"
SOURCE = "claude-code-jsonl"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """빈 HOME: ~/.claude/projects 아래 두 프로젝트(demo·other)."""
    projects = tmp_path / "home" / ".claude" / "projects"
    for key in ("-work-demo", "-work-other"):
        shutil.copytree(DATA, projects / key)
    return tmp_path / "home"


def _settings(config: Mapping[str, Any] | None = None) -> LogSettings:
    entry: dict[str, Any] = {"id": SOURCE, "enabled": True, "config": dict(config or {})}
    return LogSettings.model_validate({"sources": [entry]})


def _ingestor(
    index: MemoryLogIndex, home: Path, folders: list[ProjectFolders], **kw: Any
) -> LogIngestor:
    registries = LogRegistries()
    registries.load()
    return LogIngestor(
        index,
        registries,
        environ={"HOME": str(home)},
        clock=lambda: 1.0,
        projects=lambda: folders[0],
        **kw,
    )


def _projects(index: MemoryLogIndex) -> set[str]:
    return {c.ref.split("/", 1)[0] for c in index.list_cursors(SOURCE)}


def test_project_key_rule() -> None:
    assert project_key("/work/demo") == "-work-demo"
    assert project_key("/home/u/a.b_c d") == "-home-u-a-b-c-d"
    assert project_key("/a.b", keep=".") == "-a.b"


def test_current_scope_reads_only_current_project(home: Path) -> None:
    index = MemoryLogIndex()
    folders = [ProjectFolders(current=(Path("/work/demo"),), registered=(Path("/work/demo"),))]
    ingestor = _ingestor(index, home, folders)
    report = ingestor.scan(_settings())
    assert report.sources[0].error_code is None
    assert _projects(index) == {"-work-demo"}
    assert ingestor.scope_skipped(SOURCE) > 0  # 다른 프로젝트 기록은 건너뜀


def test_registered_scope_reads_all_registered(home: Path) -> None:
    index = MemoryLogIndex()
    both = (Path("/work/demo"), Path("/work/other"))
    folders = [ProjectFolders(current=(Path("/work/demo"),), registered=both)]
    _ingestor(index, home, folders).scan(_settings({"project_scope": "registered"}))
    assert _projects(index) == {"-work-demo", "-work-other"}


def test_no_registered_project_reads_nothing(home: Path) -> None:
    index = MemoryLogIndex()
    opened = RecordingOpen()
    _ingestor(index, home, [ProjectFolders()], open_read=opened).scan(_settings())
    assert index.list_cursors(SOURCE) == []
    assert opened.opened == []  # 홈 전체를 읽는 대체 동작 없음


def test_configured_roots_are_still_filtered(home: Path) -> None:
    index = MemoryLogIndex()
    folders = [ProjectFolders(current=(Path("/work/other"),), registered=(Path("/work/other"),))]
    ingestor = _ingestor(index, home, folders)
    ingestor.scan(_settings({"roots": [str(home / ".claude" / "projects")]}))
    assert _projects(index) == {"-work-other"}
    assert ingestor.scope_skipped(SOURCE) > 0


def test_app_auth_folder_sessions_are_read_and_credentials_never(
    home: Path, tmp_path: Path
) -> None:
    """앱 실행 세션(<앱 workspace>/.state/claude/projects)도 읽고, 자격 파일은 열지 않는다.

    두 루트(~/.claude/projects·앱 자격 폴더) 모두 등록된 프로젝트 키만 읽는다.
    """
    workspace = tmp_path / "app-data"
    project = tmp_path / "proj"
    project.mkdir()
    app_dir = workspace / ".state" / "claude"
    shutil.copytree(DATA, app_dir / "projects" / project_key(project))
    shutil.copytree(DATA, app_dir / "projects" / "-work-unregistered")
    (app_dir / ".credentials.json").write_text('{"token": "never-read"}', encoding="utf-8")
    (app_dir / "projects" / ".credentials.json").write_text("{}", encoding="utf-8")
    index = MemoryLogIndex()
    opened = RecordingOpen()
    folders = [ProjectFolders(current=(project,), registered=(project, Path("/work/demo")))]
    ingestor = _ingestor(index, home, folders, open_read=opened, paths={"workspace": workspace})
    ingestor.scan(_settings({"project_scope": "registered"}))
    # 앱 세션(proj)과 CLI 세션(~/.claude의 /work/demo)만. 등록 안 된 키는 두 루트 모두 무시.
    assert _projects(index) == {project_key(project), "-work-demo"}
    assert opened.opened
    assert not any(p.name == ".credentials.json" for p in opened.opened)
    assert not any("-work-unregistered" in str(p) or "-work-other" in str(p) for p in opened.opened)
    assert list(project.iterdir()) == []  # 작업 폴더는 읽지도 쓰지도 않는다
    roots = ClaudeCodeJsonlSource().default_roots(_ctx(home, folders[0], workspace))
    assert roots == [home / ".claude" / "projects", app_dir / "projects"]


def test_app_root_needs_workspace(home: Path) -> None:
    """앱 workspace를 모르면(단독 사용) 상대 경로 앱 루트는 건너뛴다."""
    roots = ClaudeCodeJsonlSource().default_roots(_ctx(home, ProjectFolders(), None))
    assert roots == [home / ".claude" / "projects"]


def _ctx(home: Path, folders: ProjectFolders, workspace: Path | None) -> Any:
    from agent_console_logs import LogSourceContext, effective_config

    config = effective_config(ClaudeCodeJsonlSource.descriptor.config_schema, {})
    return LogSourceContext(
        source_id=SOURCE,
        config=config,
        environ={"HOME": str(home)},
        projects=folders,
        paths={"workspace": workspace} if workspace is not None else {},
    )


def test_scope_change_purges_out_of_scope_index(home: Path) -> None:
    """범위를 좁히면 이미 색인된 범위 밖 기록을 지우고 범위 안만 다시 색인한다."""
    index = MemoryLogIndex()
    both = (Path("/work/demo"), Path("/work/other"))
    folders = [ProjectFolders(current=(Path("/work/demo"),), registered=both)]
    ingestor = _ingestor(index, home, folders)
    ingestor.scan(_settings({"project_scope": "registered"}))
    assert _projects(index) == {"-work-demo", "-work-other"}
    before = len(index._events)
    ingestor.scan(_settings({"project_scope": "current"}))
    assert _projects(index) == {"-work-demo"}
    purged = ingestor.scope_purged(SOURCE)
    assert purged == 2  # other 프로젝트의 세션 + 서브에이전트 기록
    assert len(index._events) < before
    ingestor.scan(_settings({"project_scope": "current"}))
    assert ingestor.scope_purged(SOURCE) == purged  # 범위 안만 남으면 다시 지우지 않는다


def test_standalone_without_projects_is_unfiltered(home: Path) -> None:
    """앱 밖 단독 사용(projects 미주입)은 예전처럼 루트 전체를 읽는다."""
    index = MemoryLogIndex()
    registries = LogRegistries()
    registries.load()
    LogIngestor(index, registries, environ={"HOME": str(home)}, clock=lambda: 1.0).scan(_settings())
    assert _projects(index) == {"-work-demo", "-work-other"}


def test_old_project_roots_is_ignored(home: Path, tmp_path: Path) -> None:
    """5.7R.30b: 옛 `project_roots`(프로젝트 안 상대 경로)는 deprecated로 남고 읽지 않는다."""
    project = tmp_path / "proj"
    old = project / ".agent-console" / "claude" / "projects" / project_key(project)
    shutil.copytree(DATA, old)
    schema = ClaudeCodeJsonlSource.descriptor.config_schema
    props: Any = schema["properties"]
    assert props["project_roots"]["deprecated"] is True
    assert props["workspace_roots"]["default"] == [".state/claude/projects"]
    index = MemoryLogIndex()
    opened = RecordingOpen()
    folders = [ProjectFolders(current=(project,), registered=(project,))]
    _ingestor(index, home, folders, open_read=opened).scan(
        _settings({"project_roots": [".agent-console/claude/projects"]})
    )
    assert index.list_cursors(SOURCE) == []
    assert not any(str(project) in str(p) for p in opened.opened)
