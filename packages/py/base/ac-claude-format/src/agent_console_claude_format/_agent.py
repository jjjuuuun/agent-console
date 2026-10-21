"""에이전트 파일(`.claude/agents/<이름>.md`: frontmatter + 본문 = 시스템 프롬프트)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from ._frontmatter import json_safe, parse_frontmatter, render_frontmatter, str_list
from ._mapping import ClaudeMapping

__all__ = [
    "AGENT_DOCUMENT_FIELDS",
    "INHERIT_MODEL",
    "AgentFile",
    "agent_document",
    "agent_file_from_document",
    "parse_agent_md",
    "render_agent_md",
]

INHERIT_MODEL: Final = "inherit"
"""frontmatter `model`의 "위 설정을 따름" 값(정의에는 모델을 쓰지 않는다)."""

KNOWN_KEYS: Final = ("name", "description", "tools", "disallowedTools", "model")
"""`AgentFile`의 정해진 필드로 읽는 frontmatter 키. 나머지는 `extra`."""

AGENT_DOCUMENT_FIELDS: Final = ("system_prompt", "tools", "disallowed_tools", "model")
"""`agent_file_from_document`가 읽는 정의 필드(이름·설명 외).

정의의 다른 실행 설정은 파일에 없다.
"""

AGENT_IDENTITY_FIELDS: Final = (
    "kind",
    "id",
    "schema_version",
    "name",
    "description",
    "role",
    "labels",
    "attributes",
)
"""정의의 식별·표시 필드(실행 설정이 아님)."""

FRONTMATTER_ATTRIBUTE: Final = "claude_frontmatter"
"""정의 `attributes` 안에 정해진 필드 밖 frontmatter 키를 보관하는 키."""


@dataclass(frozen=True, slots=True)
class AgentFile:
    """에이전트 파일 하나의 내용.

    Attributes:
        name: frontmatter `name`(없으면 파일 이름).
        description: 언제 맡길지(frontmatter `description`).
        prompt: 본문(시스템 프롬프트, 앞뒤 빈 줄 없음).
        tools / disallowed_tools: 도구 목록(None = 쓰지 않음 → 위 설정 상속).
        model: 모델(None = 쓰지 않음 또는 `inherit`).
        extra: 위 필드 밖의 frontmatter 키(값은 JSON 호환).
    """

    name: str
    description: str = ""
    prompt: str = ""
    tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    model: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def parse_agent_md(text: str, *, default_name: str) -> AgentFile:
    """에이전트 파일 텍스트 → `AgentFile`. frontmatter가 없으면 본문 전체가 프롬프트다."""
    meta, body = parse_frontmatter(text)
    name = str(meta.get("name") or default_name).strip() or default_name
    model = meta.get("model")
    model_value = (
        model.strip()
        if isinstance(model, str) and model.strip() and model.strip() != INHERIT_MODEL
        else None
    )
    extra = {k: v for k, v in meta.items() if k not in KNOWN_KEYS}
    return AgentFile(
        name=name,
        description=str(meta.get("description") or ""),
        prompt=body.strip(),
        tools=str_list(meta.get("tools")),
        disallowed_tools=str_list(meta.get("disallowedTools")),
        model=model_value,
        extra=json_safe(extra),
    )


def render_agent_md(agent: AgentFile) -> str:
    """`AgentFile` → 에이전트 파일 텍스트. `extra`는 정해진 키를 덮지 않는다."""
    meta: dict[str, Any] = {"name": agent.name, "description": agent.description}
    if agent.tools is not None:
        meta["tools"] = ", ".join(agent.tools)
    if agent.disallowed_tools is not None:
        meta["disallowedTools"] = ", ".join(agent.disallowed_tools)
    if agent.model:
        meta["model"] = agent.model
    for key, value in agent.extra.items():
        meta.setdefault(key, value)
    return render_frontmatter(meta, agent.prompt)


def agent_document(agent: AgentFile, *, mapping: ClaudeMapping | None = None) -> dict[str, Any]:
    """`AgentFile` → 에이전트 정의 문서(id 없음, "생략 = 상속": 파일에 없는 설정은 쓰지 않는다).

    정해진 필드 밖 frontmatter는 `attributes.claude_frontmatter`에 보관한다(실행 설정 아님).
    """
    m = mapping or ClaudeMapping()
    doc: dict[str, Any] = {
        "kind": m.agent_kind,
        "name": agent.name,
        "description": agent.description,
        "attributes": {},
    }
    if agent.prompt:
        doc["system_prompt"] = agent.prompt
    if agent.tools is not None:
        doc["tools"] = list(agent.tools)
    if agent.disallowed_tools is not None:
        doc["disallowed_tools"] = list(agent.disallowed_tools)
    if agent.model:
        doc["model"] = agent.model
    if agent.extra:
        doc["attributes"][FRONTMATTER_ATTRIBUTE] = dict(agent.extra)
    return doc


def _strings(value: Any) -> list[str] | None:
    return [str(v) for v in value] if isinstance(value, list) else None


def agent_file_from_document(
    document: Mapping[str, Any], *, name: str | None = None
) -> tuple[AgentFile, list[str]]:
    """에이전트 정의 문서 → `AgentFile`과 파일로 옮기지 못한 설정 키 목록.

    `attributes.claude_frontmatter`(가져올 때 보관한 키)는 frontmatter로 되돌린다.

    Args:
        document: 에이전트 정의 원문(생략된 키는 쓰지 않는다).
        name: frontmatter `name`(없으면 정의 `name`, 그것도 없으면 `id`).
    """
    attributes = document.get("attributes")
    extra_raw = attributes.get(FRONTMATTER_ATTRIBUTE) if isinstance(attributes, Mapping) else None
    extra = dict(extra_raw) if isinstance(extra_raw, Mapping) else {}
    prompt = document.get("system_prompt")
    model = document.get("model")
    agent = AgentFile(
        name=name or str(document.get("name") or document.get("id") or ""),
        description=str(document.get("description") or ""),
        prompt=prompt if isinstance(prompt, str) else "",
        tools=_strings(document.get("tools")),
        disallowed_tools=_strings(document.get("disallowed_tools")),
        model=model if isinstance(model, str) and model else None,
        extra=json_safe(extra),
    )
    known = {*AGENT_DOCUMENT_FIELDS, *AGENT_IDENTITY_FIELDS}
    dropped = sorted(k for k, v in document.items() if k not in known and v is not None)
    return agent, dropped
