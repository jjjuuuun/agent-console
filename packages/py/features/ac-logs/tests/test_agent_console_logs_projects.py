from pathlib import Path

from agent_console_logs import (
    UNGROUPED_PROJECT,
    RepoRootResolver,
    git_worktree_root,
)
from agent_console_logs.testing import RecordingOpen


def test_group_rules_are_gone_33i() -> None:
    """옛 묶기 규칙 해석(`resolve_project`·`group_projects`)은 5.7R.33i에서 없앴다."""
    import agent_console_logs

    for name in ("resolve_project", "group_projects", "project_base"):
        assert not hasattr(agent_console_logs, name)
    assert UNGROUPED_PROJECT == "~ungrouped"


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
