"""규칙 파일(`.claude/rules/**/*.md`: 선택 frontmatter `paths` + 본문)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from ._frontmatter import json_safe, parse_frontmatter, str_list

__all__ = ["PATHS_KEY", "RuleFile", "parse_rule", "render_rule"]

PATHS_KEY: Final = "paths"
"""경로 조건(글롭 목록) frontmatter 키."""


@dataclass(frozen=True, slots=True)
class RuleFile:
    """규칙 파일 하나.

    Attributes:
        paths: 경로 조건 글롭(빈 목록 = 항상 적용).
        body: 본문(앞 빈 줄 없음).
        extra: `paths` 밖의 frontmatter 키(JSON 호환).
    """

    paths: list[str] = field(default_factory=list)
    body: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def parse_rule(text: str) -> RuleFile:
    """규칙 파일 텍스트 → `RuleFile`. `paths`는 목록 또는 쉼표로 이은 문자열."""
    meta, body = parse_frontmatter(text)
    paths = str_list(meta.get(PATHS_KEY)) or []
    extra = {k: v for k, v in meta.items() if k != PATHS_KEY}
    return RuleFile(paths=paths, body=body.lstrip("\n"), extra=json_safe(extra))


def render_rule(paths: Sequence[str], body: str) -> str:
    """`paths` frontmatter(있을 때만) + 본문. 글롭은 JSON 문자열로 따옴표를 친다(YAML 호환)."""
    if not paths:
        return body
    lines = [
        "---",
        f"{PATHS_KEY}:",
        *(f"  - {json.dumps(p, ensure_ascii=False)}" for p in paths),
        "---",
    ]
    return "\n".join(lines) + "\n\n" + body
