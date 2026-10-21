from __future__ import annotations

import ast
import dataclasses
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from new_package import plan_new_package
from pkgkit_common import Config, load_common, names_for
from pkgkit_template import (
    merge_requirements,
    module_id_for,
    read_templates,
    required_paths,
    with_range,
)
from pkgkit_testkit import TEMPLATES, add_package, config, contracts_range, make_workspace
from pkgkit_testkit import kinds as kinds_of

KINDS = ["base", "feature", "kit", "module", "link"]


def test_five_kinds_are_data() -> None:
    kinds = kinds_of()
    assert sorted(kinds) == sorted(KINDS)
    assert {k.folder for k in kinds.values()} == {"base", "features", "kit", "modules", "links"}
    assert {k.name for k in kinds.values() if k.runnable} == {"module", "link"}


@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_renders_complete_package(kind: str) -> None:
    cfg = config()
    kinds = kinds_of()
    common = load_common(TEMPLATES)
    folder = {"module": "ac-mod-notes", "link": "ac-link-notes-runs"}.get(kind, "ac-notes")
    plan = plan_new_package(
        cfg=cfg,
        kind=kinds[kind],
        common=common,
        templates=read_templates(TEMPLATES, kind),
        folder_name=folder,
        members=[],
        year="2026",
    )
    names = names_for(folder, cfg)
    assert plan.rel == f"packages/py/{kinds[kind].folder}/{folder}"
    assert plan.add_member == plan.rel
    for rel in required_paths(common, kinds[kind], names.import_name):
        if rel != "tests":
            assert rel in plan.files, rel
    assert any(p.startswith("tests/") for p in plan.files)
    assert not any("{{" in p or "{{" in t for p, t in plan.files.items())
    for rel, text in plan.files.items():
        if rel.endswith(".py"):
            ast.parse(text)
    data = tomllib.loads(plan.files["pyproject.toml"])
    assert data["project"]["name"] == names.dist_name
    assert data["project"]["version"] == "0.1.0"
    assert "uv" not in data["tool"], "템플릿에 workspace 문법이 없어야 한다"
    assert data["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests", "README.md"]
    assert data["tool"]["mypy"]["strict"] is True
    assert ">>> " in plan.files["README.md"]
    if kinds[kind].runnable:
        assert f"src/{names.import_name}/__main__.py" in plan.files
        eps = data["project"]["entry-points"]["agent_console.server_modules"]
        assert eps == {module_id_for(names, kinds[kind], cfg): f"{names.import_name}.module:module"}


def test_module_id() -> None:
    cfg = config()
    kinds = kinds_of()
    assert module_id_for(names_for("ac-mod-chat", cfg), kinds["module"], cfg) == "chat"
    assert module_id_for(names_for("ac-link-chat-runs", cfg), kinds["link"], cfg) == "chat-runs"


def test_internal_ranges_and_merge() -> None:
    cfg = config()
    assert (
        with_range("agent-console-contracts", cfg) == f"agent-console-contracts{contracts_range()}"
    )
    assert with_range("agent-console-chat", cfg) == "agent-console-chat>=0.1,<0.2"
    assert with_range("agent-console-chat>=0.3", cfg) == "agent-console-chat>=0.3"
    assert with_range("pydantic", cfg) == "pydantic"
    assert with_range("agent-console-modkit[host]", cfg) == "agent-console-modkit[host]>=0.1,<0.2"
    assert merge_requirements(["a>=1", "b"], ["A", "c"]) == ["a>=1", "b", "c"]


def test_extra_dependencies_rendered() -> None:
    cfg = config()
    kinds = kinds_of()
    plan = plan_new_package(
        cfg=cfg,
        kind=kinds["feature"],
        common=load_common(TEMPLATES),
        templates=read_templates(TEMPLATES, "feature"),
        folder_name="ac-notes",
        members=["packages/py/*/*"],
        year="2026",
        dependencies=["agent-console-registry", "pyyaml>=6"],
        dev_dependencies=["agent-console-backend-fake"],
        description='say "hi"',
    )
    data = tomllib.loads(plan.files["pyproject.toml"])
    assert data["project"]["dependencies"] == [
        f"agent-console-contracts{contracts_range()}",
        "agent-console-registry>=0.1,<0.2",
        "pyyaml>=6",
    ]
    assert "agent-console-backend-fake>=0.1,<0.2" in data["dependency-groups"]["dev"]
    assert data["project"]["description"] == "say 'hi'"
    assert plan.add_member is None


def _render(cfg: Config, kind: str, folder: str) -> dict[str, str]:
    plan = plan_new_package(
        cfg=cfg,
        kind=kinds_of(cfg)[kind],
        common=load_common(TEMPLATES),
        templates=read_templates(TEMPLATES, kind),
        folder_name=folder,
        members=[],
        year="2031",
    )
    return dict(plan.files)


def test_license_is_mit() -> None:
    """MIT 라이선스. SPDX 표기 + license-files."""
    files = _render(config(), "feature", "ac-notes")
    data = tomllib.loads(files["pyproject.toml"])
    assert data["project"]["license"] == "MIT"
    assert data["project"]["license-files"] == ["LICENSE"]
    assert files["LICENSE"].startswith("MIT License\n\nCopyright (c) 2031 jjjuuuun")
    assert "정하지 않았다" not in files["LICENSE"]


@pytest.mark.parametrize("kind", KINDS)
def test_inhouse_names_come_only_from_config(kind: str) -> None:
    """접두사·제품 이름·entry point 그룹을 바꾸면 설정 한 곳만 고쳐도 템플릿 결과가 따라온다."""
    cfg = dataclasses.replace(
        config(),
        dist_prefix="acme-",
        import_prefix="acme_",
        internal_ranges={"default": ">=1,<2"},
        template_values={
            "product_name": "Acme",
            "copyright_holder": "Acme Inc",
            "modules_group": "acme.modules",
        },
    )
    files = _render(cfg, kind, "ac-mod-x" if kind == "module" else "ac-x")
    text = "\n".join(files.values())
    for old in ("agent_console", "agent-console", "Agent Console"):
        assert old not in text, (old, kind)
    data = tomllib.loads(files["pyproject.toml"])
    assert data["tool"]["ruff"]["lint"]["isort"]["known-first-party"] == ["acme_*"]
    assert data["project"]["name"].startswith("acme-")
    assert all(d.startswith("acme-") for d in data["project"]["dependencies"])
    assert data["project"]["description"].startswith("Acme ")
    if kinds_of(cfg)[kind].runnable:
        assert "acme.modules" in data["project"]["entry-points"]
        main = next(t for p, t in files.items() if p.endswith("__main__.py"))
        assert "from acme_modkit.standalone import run" in main


def test_readme_doctest_is_collected(tmp_path: Path) -> None:
    """템플릿 pytest 설정(testpaths에 README.md)으로 README doctest가 실제로 수집·실행된다."""
    root = tmp_path / "repo"
    cfg = make_workspace(root)
    pkg = add_package(root, cfg, "base", "ac-doc")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)}
    env["PYTHONPATH"] = str(pkg / "src")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--collect-only", "-q"],
        cwd=pkg,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "README.md::README.md" in proc.stdout, proc.stdout + proc.stderr
    readme = pkg / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace("'hello, pkgkit'", "'wrong'"), encoding="utf-8"
    )
    failed = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "README.md"],
        cwd=pkg,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode == 1, failed.stdout
