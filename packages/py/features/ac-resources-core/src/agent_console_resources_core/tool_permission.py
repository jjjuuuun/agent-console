"""`tool-permission` 종류: 허용·금지 도구 목록과 명령 허용 목록.

칸 `tools` = `{tools?, disallowed_tools?, commands?}` 목록. 여러 항목을 합치는 규칙(허용은 합집합,
금지가 우선 등)은 받는 쪽(백엔드·실행 범위 검사)이 정한다.
"""

from __future__ import annotations

from typing import Any

from agent_console_contracts import (
    KnownResourceSlots,
    Resource,
    ResourceTypeDescriptor,
    UiHints,
    x_ui,
)
from agent_console_resources import Content, ContributeContext, Contribution, SchemaResourceType

__all__ = ["PERMISSION_FIELDS", "ToolPermissionType"]

PERMISSION_FIELDS = ("tools", "disallowed_tools", "commands")
"""config에서 읽어 칸 항목으로 옮기는 필드."""

_LIST: dict[str, Any] = {"type": "array", "items": {"type": "string", "minLength": 1}}

_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tools": {
            **_LIST,
            "title": "허용 도구",
            "description": "붙인 에이전트가 쓸 수 있게 할 도구 이름입니다.",
            **x_ui(
                tier="basic",
                when="붙인 에이전트에게 도구를 더 주고 싶을 때 더하세요.",
                example=["Read", "Grep"],
            ),
        },
        "disallowed_tools": {
            **_LIST,
            "title": "금지 도구",
            "description": "붙인 에이전트가 쓰지 못하게 할 도구 이름입니다.",
            **x_ui(
                tier="basic",
                when="붙인 에이전트가 특정 도구를 쓰지 못하게 하고 싶을 때 더하세요.",
                example=["Bash"],
            ),
        },
        "commands": {
            **_LIST,
            "title": "허용 명령",
            "description": "붙인 에이전트가 실행할 수 있는 명령입니다.",
            **x_ui(
                tier="basic",
                when="붙인 에이전트가 특정 명령을 실행해야 할 때 더하세요.",
                example=["git", "pytest"],
            ),
        },
    },
    "minProperties": 1,
    "additionalProperties": False,
}


class ToolPermissionType(SchemaResourceType):
    """도구 권한 묶음 하나를 `tools` 칸에 낸다."""

    descriptor = ResourceTypeDescriptor(
        id="tool-permission",
        version=1,
        title="도구 권한",
        description="허용·금지 도구 목록과 명령 허용 목록.",
        config_schema=_CONFIG_SCHEMA,
        slot_key=None,
        combine="append",
        contributes=[KnownResourceSlots.TOOLS],
        ui_hints=UiHints(icon="권"),
    )

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        """`tools` 칸에 `{tools?, disallowed_tools?, commands?}` 한 항목."""
        entry = {k: list(resource.config[k]) for k in PERMISSION_FIELDS if k in resource.config}
        return [Contribution(KnownResourceSlots.TOOLS, [entry])] if entry else []
