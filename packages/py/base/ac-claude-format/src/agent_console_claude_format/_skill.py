"""skill 폴더(`.claude/skills/<이름>/`: `SKILL.md` + 부속 파일)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from ._frontmatter import json_safe, parse_frontmatter, render_frontmatter

__all__ = ["SKILL_NAME_PATTERN", "SkillFolder", "parse_skill", "render_skill", "valid_skill_name"]

SKILL_NAME_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
"""폴더 이름으로 안전한 skill 이름."""

DEFAULT_SKILL_FILE: Final = "SKILL.md"


def valid_skill_name(name: str) -> bool:
    """`SKILL_NAME_PATTERN`에 맞으면 참."""
    return re.fullmatch(SKILL_NAME_PATTERN, name) is not None


@dataclass(frozen=True, slots=True)
class SkillFolder:
    """skill 폴더 하나.

    Attributes:
        name: skill 이름(폴더 이름).
        title: `SKILL.md` frontmatter `name`(없으면 폴더 이름).
        description: `SKILL.md` frontmatter `description`.
        files: 폴더 기준 상대 경로(`/` 구분) → 내용(주 파일 포함).
        frontmatter: 주 파일 frontmatter 전체(JSON 호환).
    """

    name: str
    title: str
    description: str = ""
    files: dict[str, bytes] = field(default_factory=dict)
    frontmatter: dict[str, Any] = field(default_factory=dict)


def parse_skill(
    folder_name: str, files: Mapping[str, bytes], *, skill_file: str = DEFAULT_SKILL_FILE
) -> SkillFolder:
    """폴더 이름과 파일들 → `SkillFolder`. 주 파일이 없으면 frontmatter는 비어 있다."""
    main = files.get(skill_file)
    meta: dict[str, Any] = {}
    if main is not None:
        meta, _ = parse_frontmatter(main.decode("utf-8", errors="replace"))
    return SkillFolder(
        name=folder_name,
        title=str(meta.get("name") or folder_name),
        description=str(meta.get("description") or ""),
        files={path: bytes(data) for path, data in sorted(files.items())},
        frontmatter=json_safe(meta),
    )


def render_skill(
    name: str,
    files: Mapping[str, bytes],
    *,
    description: str = "",
    skill_file: str = DEFAULT_SKILL_FILE,
) -> dict[str, bytes]:
    """skill 폴더에 쓸 파일들.

    주 파일이 있으면 그대로 두고, 없으면 frontmatter만 있는 주 파일을 만든다.
    """
    out = {path: bytes(data) for path, data in sorted(files.items())}
    if skill_file not in out:
        meta = {"name": name, "description": description}
        out[skill_file] = render_frontmatter(meta, "").encode("utf-8")
    return out
