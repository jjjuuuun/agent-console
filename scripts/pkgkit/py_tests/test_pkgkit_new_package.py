from __future__ import annotations

import tomllib
from pathlib import Path

import importlinter_sync
import new_package as np_
import pytest
from pkgkit_common import Config, PkgkitError
from pkgkit_testkit import ROOT_PYPROJECT, add_package, make_workspace


@pytest.mark.parametrize(
    ("rel", "pattern", "ok"),
    [
        ("packages/py/features/ac-x", "packages/py/*/*", True),
        ("packages/py/features/ac-x", "packages/py/*", False),
        ("apps/server", "apps/*", True),
        ("packages/py/kit/ac-x", "packages/py/kit/ac-x", True),
    ],
)
def test_member_matches(rel: str, pattern: str, ok: bool) -> None:
    assert np_.member_matches(rel, pattern) is ok


def test_add_workspace_member_single_line() -> None:
    text = '[tool.uv.workspace]\nmembers = ["packages/py/*", "apps/*"]\n\n[tool.x]\ny = 1\n'
    out = np_.add_workspace_member(text, "packages/py/kit/ac-x")
    data = tomllib.loads(out)
    assert data["tool"]["uv"]["workspace"]["members"] == [
        "packages/py/*",
        "apps/*",
        "packages/py/kit/ac-x",
    ]
    assert data["tool"]["x"] == {"y": 1}


def test_add_workspace_member_multi_line() -> None:
    text = '[tool.uv.workspace]\nmembers = [\n    "a",\n    "b",\n]\n'
    out = np_.add_workspace_member(text, "c")
    assert tomllib.loads(out)["tool"]["uv"]["workspace"]["members"] == ["a", "b", "c"]
    with pytest.raises(PkgkitError):
        np_.add_workspace_member("[project]\n", "c")


def test_write_plan_refuses_existing(tmp_path: Path) -> None:
    cfg = make_workspace(tmp_path)
    add_package(tmp_path, cfg, "feature", "ac-x")
    with pytest.raises(PkgkitError, match="이미 있습니다"):
        add_package(tmp_path, cfg, "feature", "ac-x")


def _patch(monkeypatch: pytest.MonkeyPatch, cfg: Config) -> None:
    monkeypatch.setattr(np_, "load_config", lambda _p=None: cfg)
    monkeypatch.setattr(importlinter_sync, "load_config", lambda _p=None: cfg)


def test_main_creates_package_and_updates_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = make_workspace(
        tmp_path,
        ROOT_PYPROJECT.replace('members = ["packages/py/*/*", "apps/*"]', 'members = ["apps/*"]'),
    )
    (tmp_path / cfg.importlinter_rules).write_text(
        'root_packages = ["@all"]\n\n[[contracts]]\nname = "모듈 독립"\ntype = "independence"\n'
        'modules = ["@module"]\n',
        encoding="utf-8",
    )
    _patch(monkeypatch, cfg)
    assert np_.main(["--root", str(tmp_path), "--kind", "module", "ac-mod-a", "--dry-run"]) == 0
    assert not (tmp_path / "packages").exists()
    assert np_.main(["--root", str(tmp_path), "--kind", "module", "ac-mod-a"]) == 0
    assert np_.main(["--root", str(tmp_path), "--kind", "module", "ac-mod-b", "--id", "bee"]) == 0
    data = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["tool"]["uv"]["workspace"]["members"] == [
        "apps/*",
        "packages/py/modules/ac-mod-a",
        "packages/py/modules/ac-mod-b",
    ]
    assert data["tool"]["uv"]["sources"] == {
        "agent-console-mod-a": {"workspace": True},
        "agent-console-mod-b": {"workspace": True},
    }
    il = data["tool"]["importlinter"]
    assert il["root_packages"] == ["agent_console_mod_a", "agent_console_mod_b"]
    assert il["contracts"][0]["modules"] == ["agent_console_mod_a", "agent_console_mod_b"]
    b = tomllib.loads(
        (tmp_path / "packages/py/modules/ac-mod-b/pyproject.toml").read_text(encoding="utf-8")
    )
    assert b["project"]["entry-points"]["agent_console.server_modules"] == {
        "bee": "agent_console_mod_b.module:module"
    }
    assert np_.main(["--root", str(tmp_path), "--kind", "nope", "ac-x"]) == 2


def test_add_root_source_creates_table_when_missing() -> None:
    out = np_.add_root_source('[project]\nname = "ws"\n', "agent-console-x")
    assert tomllib.loads(out)["tool"]["uv"]["sources"] == {"agent-console-x": {"workspace": True}}


def test_add_root_source_appends_inside_existing_table() -> None:
    text = (
        "[tool.uv.sources]\n"
        "agent-console-a = { workspace = true }\n"
        "\n"
        "# 다음 표 설명\n"
        "[tool.poe.tasks]\n"
        'x = "y"\n'
    )
    out = np_.add_root_source(text, "agent-console-b")
    data = tomllib.loads(out)
    assert data["tool"]["uv"]["sources"] == {
        "agent-console-a": {"workspace": True},
        "agent-console-b": {"workspace": True},
    }
    assert data["tool"]["poe"]["tasks"] == {"x": "y"}
    assert "# 다음 표 설명\n[tool.poe.tasks]" in out
    assert np_.add_root_source(out, "agent-console-b") == out


def test_plan_skips_source_already_declared(tmp_path: Path) -> None:
    cfg = make_workspace(tmp_path)
    from new_package import plan_new_package
    from pkgkit_common import load_common
    from pkgkit_template import read_templates
    from pkgkit_testkit import TEMPLATES, kinds

    def plan(sources: list[str]) -> np_.NewPackagePlan:
        return plan_new_package(
            cfg=cfg,
            kind=kinds(cfg)["feature"],
            common=load_common(TEMPLATES),
            templates=read_templates(TEMPLATES, "feature"),
            folder_name="ac-x",
            members=["packages/py/*/*"],
            year="2026",
            sources=sources,
        )

    assert plan([]).add_source == "agent-console-x"
    assert plan(["agent_console_x"]).add_source is None
