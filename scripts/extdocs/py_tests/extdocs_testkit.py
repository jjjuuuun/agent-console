"""extdocs 테스트 도우미: 임시 저장소(루트 pyproject + 멤버 패키지 + 예제 + 문서)."""

from __future__ import annotations

import textwrap
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from extdocs_common import TOOL_DIR, ToolData, load_data

REPO_ROOT = TOOL_DIR.parents[1]


def tool_data(**overrides: object) -> ToolData:
    """저장소 데이터 파일 + 설정 덮어쓰기(기본: 계약 표 끔 — 임시 저장소에는 계약이 없다)."""
    data = load_data()
    settings = dict(data.settings)
    settings["facts"] = {}
    settings.update(overrides)
    return ToolData(
        settings=settings,
        areas=data.areas,
        readme_sections=data.readme_sections,
        lint_rules=data.lint_rules,
        registration_templates=data.registration_templates,
        text=data.text,
    )


GOOD_README = """\
# 예제

## 최소 코드

코드.

## 등록

등록.

## 설치·제거

설치.

## 테스트

테스트.
"""


@dataclass
class Repo:
    """임시 저장소. import 이름은 테스트마다 달라 ``sys.modules`` 캐시가 섞이지 않는다."""

    root: Path
    tag: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    members: list[str] = field(default_factory=list)

    def mod(self, base: str) -> str:
        return f"{base}_{self.tag}"

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return path

    def write_root(self) -> None:
        sources = "\n".join(f"{name} = {{ workspace = true }}" for name in self.members)
        self.write(
            "pyproject.toml",
            '[project]\nname = "ws"\nversion = "0"\n\n[tool.uv.workspace]\n'
            'members = ["packages/py/*/*"]\n\n[tool.uv.sources]\n' + sources + "\n",
        )

    def package(
        self,
        folder: str,
        dist: str,
        *,
        files: dict[str, str] | None = None,
        tool: str = "",
        entry_points: str = "",
        member: bool = True,
    ) -> Path:
        """``packages/py/features/<folder>`` 패키지. ``files``의 키는 ``src`` 기준 경로."""
        base = f"packages/py/features/{folder}"
        self.write(
            f"{base}/pyproject.toml",
            f'[project]\nname = "{dist}"\nversion = "0.1.0"\n\n{entry_points}\n\n{tool}\n',
        )
        for rel, text in (files or {}).items():
            self.write(f"{base}/src/{rel}", text)
        if member:
            self.members.append(dist)
        self.write_root()
        return self.root / base

    def example(
        self, folder: str, points: list[str] | None, readme: str | None = GOOD_README
    ) -> str:
        base = f"examples/extensions/{folder}"
        marker = ""
        if points is not None:
            marker = (
                "[tool.agent-console.example]\npoints = ["
                + ", ".join(f'"{p}"' for p in points)
                + "]\n"
            )
        self.write(
            f"{base}/pyproject.toml", f'[project]\nname = "{folder}"\nversion = "0.1.0"\n\n{marker}'
        )
        if readme is not None:
            self.write(f"{base}/README.md", readme)
        return base


MODULE_SOURCE = """\
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Port:
    name: str
    multi: bool = False


@dataclass(frozen=True)
class Descriptor:
    id: str
    kind: str = "feature"
    provides: tuple = ()
    requires: tuple = ()
    optional: tuple = ()
    web_roles: tuple = ()
    contracts: dict = field(default_factory=dict)
    migrations: tuple = ()


class Module:
    def __init__(self, descriptor):
        self.descriptor = descriptor


NOTES = Port("notes.store")
HOOKS = Port("notes.hooks", multi=True)
module = Module(Descriptor(id="mod-notes", provides=(NOTES,), optional=(HOOKS,)))
"""
