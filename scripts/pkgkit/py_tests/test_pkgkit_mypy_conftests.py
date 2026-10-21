from __future__ import annotations

import sys
from pathlib import Path

from mypy_conftests import find_conftests, mypy_paths, plan


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")


def test_finds_conftests_under_globbed_dirs(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.mypy]\nfiles = ["packages/*/*/tests", "apps/server/tests"]\n', encoding="utf-8"
    )
    _touch(tmp_path / "packages/py/a/tests/conftest.py")
    _touch(tmp_path / "packages/py/b/tests/sub/conftest.py")
    _touch(tmp_path / "packages/py/b/tests/test_x.py")
    _touch(tmp_path / "packages/py/c/tests/.venv/conftest.py")
    _touch(tmp_path / "other/conftest.py")
    found = find_conftests(tmp_path, mypy_paths(tmp_path))
    assert found == [
        Path("packages/py/a/tests/conftest.py"),
        Path("packages/py/b/tests/sub/conftest.py"),
    ]


def test_plan_runs_one_mypy_per_file() -> None:
    cmds = plan([Path("a/conftest.py"), Path("b/conftest.py")])
    assert cmds == [
        [sys.executable, "-m", "mypy", "a/conftest.py"],
        [sys.executable, "-m", "mypy", "b/conftest.py"],
    ]
