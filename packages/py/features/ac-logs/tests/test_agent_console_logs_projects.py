from pathlib import Path

from agent_console_contracts.logs import LogProjectSettings
from agent_console_logs import (
    UNGROUPED_PROJECT,
    RepoRootResolver,
    git_worktree_root,
    group_projects,
    resolve_project,
)
from agent_console_logs.testing import RecordingOpen


def _settings(**kw: object) -> LogProjectSettings:
    return LogProjectSettings.model_validate(kw)


def test_groups_first_match_wins() -> None:
    s = _settings(
        groups=[
            {"id": "inner", "label": "안쪽", "match": ["/w/a/**"]},
            {"id": "outer", "match": ["/w/**"]},
        ]
    )
    assert resolve_project("/w/a/x", "", s)[0].id == "inner"  # type: ignore[union-attr]
    ref, grouped = resolve_project("/w/b", "", s)
    assert ref is not None
    assert (ref.id, ref.label, grouped) == ("outer", "outer", True)


def test_ungrouped_policies() -> None:
    assert resolve_project("", "", None) == (None, False)
    ref, grouped = resolve_project("/p/wt", "/p/main", None)
    assert ref is not None
    assert (ref.id, grouped) == ("/p/wt", False)  # 기본 cwd 정책
    ref = resolve_project("/p/wt", "/p/main", _settings(ungrouped="repo_root"))[0]
    assert ref is not None
    assert ref.id == "/p/main"
    ref = resolve_project("/p/wt", "/p/main", _settings(ungrouped="none"))[0]
    assert ref is not None
    assert ref.id == UNGROUPED_PROJECT
    off = _settings(ungrouped="repo_root", git_worktrees=False)
    assert resolve_project("/p/wt", "/p/main", off)[0].id == "/p/wt"  # type: ignore[union-attr]


def test_worktree_groups_by_main_repo() -> None:
    s = _settings(groups=[{"id": "main", "match": ["/p/main"]}])
    assert resolve_project("/p/wt", "/p/main", s)[0].id == "main"  # type: ignore[union-attr]
    mapping = group_projects([("/p/wt", "/p/main"), ("/q", "")], s)
    assert mapping[("/q", "")].id == "/q"  # type: ignore[union-attr]


def test_git_worktree_root_reads_git_file(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: /repos/main/.git/worktrees/wt\n", encoding="utf-8")
    plain = tmp_path / "plain"
    (plain / ".git").mkdir(parents=True)
    opener = RecordingOpen()
    assert git_worktree_root(str(wt), open_read=opener) == "/repos/main"
    assert git_worktree_root(str(plain), open_read=opener) == ""
    assert git_worktree_root(str(tmp_path / "missing"), open_read=opener) == ""
    assert git_worktree_root("") == ""
    resolver = RepoRootResolver(opener)
    before = len(opener.opened)
    assert resolver(str(wt)) == resolver(str(wt)) == "/repos/main"
    assert len(opener.opened) == before + 1  # cwd별 캐시
