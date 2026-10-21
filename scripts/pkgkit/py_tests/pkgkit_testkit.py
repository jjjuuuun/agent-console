"""pkgkit 테스트 도우미: 가짜 워크스페이스(루트 pyproject + 템플릿으로 만든 패키지)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from new_package import plan_new_package, write_plan
from pkgkit_common import (
    Config,
    KindSpec,
    load_common,
    load_config,
    load_kinds,
    resolve_ranges,
    workspace_versions,
)
from pkgkit_template import read_templates

PKGKIT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES = PKGKIT_DIR / "templates" / "python"
REPO_ROOT = PKGKIT_DIR.parents[1]

ROOT_PYPROJECT = """\
[project]
name = "ws"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = []

[tool.uv]
package = false

[tool.uv.workspace]
members = ["packages/py/*/*", "apps/*"]

[tool.ruff]
target-version = "py312"
line-length = 100
extend-exclude = ["node_modules"]

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "SIM", "RUF", "N", "PT", "TID"]

[tool.ruff.lint.isort]
known-first-party = ["agent_console_*"]

[tool.mypy]
python_version = "3.12"
files = ["packages/py/*/*/src"]
strict = true
warn_unreachable = true
"""


def config() -> Config:
    """저장소 설정에서 템플릿 경로만 실제 템플릿 절대 경로로 바꾸고, ``from-package`` 범위를 저장소
    워크스페이스의 지금 버전으로 푼 설정."""
    cfg = resolve_ranges(load_config(), workspace_versions(REPO_ROOT))
    return dataclasses.replace(cfg, templates=str(TEMPLATES))


def contracts_range() -> str:
    """저장소 계약 패키지 버전에서 만든 지금 범위(테스트가 고정 값 대신 쓴다)."""
    return config().range_for("agent-console-contracts")


def kinds(cfg: Config | None = None) -> dict[str, KindSpec]:
    """설정 값으로 렌더링한 종류 정보."""
    return load_kinds(TEMPLATES, (cfg or config()).template_vars)


def make_workspace(root: Path, root_pyproject: str = ROOT_PYPROJECT) -> Config:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(root_pyproject, encoding="utf-8")
    return config()


def add_package(root: Path, cfg: Config, kind: str, folder: str, **kw: object) -> Path:
    """템플릿으로 패키지를 만들어 쓰고 폴더를 돌려준다."""
    plan = plan_new_package(
        cfg=cfg,
        kind=kinds(cfg)[kind],
        common=load_common(TEMPLATES),
        templates=read_templates(TEMPLATES, kind),
        folder_name=folder,
        members=["packages/py/*/*"],
        year="2026",
        **kw,  # type: ignore[arg-type]
    )
    write_plan(root, plan)
    return root / plan.rel


def add_app(root: Path, folder: str, import_name: str) -> Path:
    app = root / "apps" / folder
    (app / "src" / import_name).mkdir(parents=True)
    (app / "src" / import_name / "__init__.py").write_text("", encoding="utf-8")
    dist = import_name.replace("_", "-")
    (app / "pyproject.toml").write_text(
        f'[project]\nname = "{dist}"\nversion = "0.0.0"\n', encoding="utf-8"
    )
    return app
