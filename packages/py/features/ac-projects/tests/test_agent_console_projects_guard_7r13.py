"""폴더 안 경로 지킴 ``FolderGuard``(design §PI.5, 7R.13)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_console_projects import FolderGuard, normalize_reserved, relative_inside


def test_reserved_is_case_insensitive_prefix(tmp_path: Path) -> None:
    guard = FolderGuard(tmp_path, reserved=["/.agent-console/", "build/out"])
    assert guard.reserved == (".agent-console", "build/out")
    assert guard.is_reserved(".agent-console")
    assert guard.is_reserved(".AGENT-CONSOLE/wiki-pages/a.md")
    assert guard.is_reserved("build/out/x")
    assert not guard.is_reserved(".agent-console2/x")
    assert not guard.is_reserved("build")
    assert not guard.is_reserved("")


def test_contains_reserved(tmp_path: Path) -> None:
    guard = FolderGuard(tmp_path, reserved=[".cfg/.state"])
    assert guard.contains_reserved(".cfg")
    assert guard.contains_reserved("")
    assert not guard.contains_reserved(".cfg/pages")
    assert not FolderGuard(tmp_path).contains_reserved("")


def test_resolves_inside_follows_links(tmp_path: Path) -> None:
    folder = tmp_path / "app"
    outside = tmp_path / "outside"
    (folder / "docs").mkdir(parents=True)
    outside.mkdir()
    guard = FolderGuard(folder)
    assert guard.resolves_inside("")
    assert guard.resolves_inside("docs/new/a.md")  # 없는 경로도 본다
    try:
        os.symlink(outside, folder / "escape", target_is_directory=True)
    except OSError:  # pragma: no cover - 링크를 만들 수 없는 환경
        pytest.skip("symlink unavailable")
    assert not guard.resolves_inside("escape")
    assert not guard.resolves_inside("escape/a.md")
    assert guard.violation("escape/a.md") == "link"
    os.symlink(folder / "docs", folder / "inside", target_is_directory=True)
    assert guard.violation("inside/a.md") is None


def test_injected_realpath(tmp_path: Path) -> None:
    folder = str(tmp_path / "app")
    calls: list[str] = []

    def fake(path: str) -> str:
        calls.append(path)
        return str(tmp_path / "elsewhere") if path.endswith("j") else path

    guard = FolderGuard(folder, realpath=fake)
    assert guard.violation("j") == "link"
    assert calls


def test_normalize_and_relative() -> None:
    assert normalize_reserved(["", " /a/ ", "A"]) == ("a",)
    assert relative_inside(Path("/w/app/.cfg/x"), Path("/w/app")) == ".cfg/x"
    with pytest.raises(ValueError, match="outside"):
        relative_inside("/w/other", "/w/app")
    with pytest.raises(ValueError, match="inside"):
        relative_inside("/w/app", "/w/app")
