"""정의 종류·리소스 종류 이름 대응(`ClaudeMapping`)과 `.claude` 산출물 경로(`ClaudeLayout`).

둘 다 데이터다.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self

__all__ = ["ClaudeLayout", "ClaudeMapping"]


def _from_options[T](cls: type[T], raw: Mapping[str, Any] | None) -> T:
    if raw is None:
        return cls()
    names = {f.name for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
    unknown = sorted(str(k) for k in raw if k not in names)
    if unknown:
        raise ValueError(f"{cls.__name__}: 모르는 키 {', '.join(unknown)}")
    values = {str(k): v for k, v in raw.items()}
    bad = sorted(k for k, v in values.items() if not isinstance(v, str) or not v)
    if bad:
        raise ValueError(
            f"{cls.__name__}: 값은 빈 문자열이 아닌 문자열이어야 합니다: {', '.join(bad)}"
        )
    return cls(**values)


@dataclass(frozen=True, slots=True)
class ClaudeMapping:
    """`.claude` 산출물 ↔ Agent Console 정의의 이름 대응(데이터).

    기본값은 기본 플러그인 이름이다. 다른 리소스 종류 플러그인을 쓰면 바꿔 넘긴다
    (서버 설정 `imports.options.claude.mapping`, `exports.options.<형식>.mapping`).

    Attributes:
        agent_kind / resource_kind / graph_kind: 정의 종류 이름(저장소 kind).
        instruction_type / mcp_type / permission_type / skill_type / rule_type / hook_type:
            리소스 종류 id.
        content_file / content_media_type: 한 파일 본문 리소스의 본문 파일 이름·형식.
    """

    agent_kind: str = "agent"
    resource_kind: str = "resource"
    graph_kind: str = "graph"
    instruction_type: str = "instruction"
    mcp_type: str = "mcp-server"
    permission_type: str = "tool-permission"
    skill_type: str = "skill"
    rule_type: str = "rule"
    hook_type: str = "hook"
    content_file: str = "content.md"
    content_media_type: str = "text/markdown"

    @classmethod
    def from_options(cls, raw: Mapping[str, Any] | None) -> Self:
        """설정 값(dict)으로 만든다. 생략한 키는 기본값.

        Raises:
            ValueError: 모르는 키이거나 값이 빈 문자열이 아닌 문자열이 아닐 때.
        """
        return _from_options(cls, raw)


@dataclass(frozen=True, slots=True)
class ClaudeLayout:
    """`.claude` 산출물의 상대 경로(데이터). 프로젝트 폴더 기준이다.

    Attributes:
        claude_dir: 설정 폴더(`.claude`).
        instruction_file: 지침 파일 이름(`CLAUDE.md`, 프로젝트 폴더와 설정 폴더에 있을 수 있다).
        mcp_file: 프로젝트 MCP 서버 파일(`.mcp.json`, 프로젝트 폴더).
        agents_dir / skills_dir / rules_dir: 설정 폴더 안 하위 폴더.
        settings_file: 설정 폴더 안 설정 파일(`settings.json`).
        skill_file: skill 폴더의 주 파일(`SKILL.md`).
        instructions_dir: 지침을 따로 쓸 때(내보내기 `separate_files`) 설정 폴더 안 하위 폴더.
    """

    claude_dir: str = ".claude"
    instruction_file: str = "CLAUDE.md"
    mcp_file: str = ".mcp.json"
    agents_dir: str = "agents"
    skills_dir: str = "skills"
    rules_dir: str = "rules"
    settings_file: str = "settings.json"
    skill_file: str = "SKILL.md"
    instructions_dir: str = "instructions"

    @classmethod
    def from_options(cls, raw: Mapping[str, Any] | None) -> Self:
        """설정 값(dict)으로 만든다. `ClaudeMapping.from_options`와 같은 규칙."""
        return _from_options(cls, raw)

    def in_claude_dir(self, *parts: str) -> str:
        """설정 폴더 안 상대 경로(`/` 구분)."""
        return "/".join((self.claude_dir, *parts))
