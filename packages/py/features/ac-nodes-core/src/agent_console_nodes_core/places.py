"""`resource`(리소스) 노드 타입(design §R12). 사용자 노드는 `user.py`.

- `resource`: 리소스 정의 하나의 자리(`binds{kind: resource, field: resource_ref}`),
  포트 `provides`.
  `executable=false` — 실행되지 않고 연결된 에이전트의 노드 층 첨부가 된다(`ac-teams`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import (
    DefinitionBinding,
    Issue,
    NodeTypeDescriptor,
    PortDef,
    PortSpec,
    UiHints,
    x_ui,
)
from agent_console_runtime import NodeContext, NodeResult, ValidationContext

from ._common import (
    PROVIDES_PORT,
    RESOURCE_ROLE,
    NodesCoreErrorCodes,
    failed,
    issue,
)
from .services import RESOURCE_LOOKUP

__all__ = ["ResourceNode", "ResourceNodeConfig"]


class ResourceNodeConfig(BaseModel):
    """리소스 노드 설정."""

    model_config = ConfigDict(extra="forbid", title="리소스 노드 설정")

    resource_ref: str = Field(
        min_length=1,
        title="리소스",
        description="이 자리에 놓을 리소스입니다. 연결한 에이전트에 붙습니다.",
        json_schema_extra=x_ui(
            tier="basic", when="연결한 에이전트에 다른 리소스를 주고 싶을 때 고르세요."
        ),
    )


_RESOURCE_PORTS = PortSpec(outputs=[PortDef(name=PROVIDES_PORT, label="제공")])


class ResourceNode:
    """노드 타입 `resource`: 리소스 정의 하나를 그래프에 두고 연결로 에이전트에 붙인다."""

    descriptor = NodeTypeDescriptor(
        id="resource",
        version=1,
        title="리소스",
        description="지침·파일·MCP 서버 등 리소스. 연결한 에이전트에 붙는다(실행되지 않음).",
        category="리소스",
        role=RESOURCE_ROLE,
        executable=False,
        binds=DefinitionBinding(kind="resource", field="resource_ref"),
        config_schema=ResourceNodeConfig.model_json_schema(),
        static_ports=_RESOURCE_PORTS,
        ui_hints=UiHints(shape="chip"),
    )

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        """고정 포트(`provides`)."""
        return _RESOURCE_PORTS

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        """리소스 조회 서비스가 있으면 `resource_ref`가 있는지 본다."""
        ref = config.get("resource_ref")
        lookup = ctx.services.get(RESOURCE_LOOKUP)
        if not isinstance(ref, str) or lookup is None:
            return []
        try:
            found = lookup.get_resource(ref)
        except LookupError:
            found = None
        if found is not None:
            return []
        return [
            issue(
                NodesCoreErrorCodes.RESOURCE_NOT_FOUND,
                f"리소스 {ref!r}가 없습니다",
                "/resource_ref",
            )
        ]

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        """엔진은 `executable=false` 노드를 스케줄하지 않는다. 직접 부르면 실패."""
        return failed(
            NodesCoreErrorCodes.RESOURCE_NOT_EXECUTABLE, "리소스 노드는 실행되지 않습니다"
        )
