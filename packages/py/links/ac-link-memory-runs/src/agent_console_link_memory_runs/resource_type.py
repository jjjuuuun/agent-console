"""리소스 종류 ``memory``(에이전트 메모리 접근, X14 구현, design §5.7R.1.3).

디스크립터는 패키지 데이터(``data/memory_resource_type.yaml``)이고 설정 스키마는 계약
``MemoryAccessConfig``의 JSON Schema다. 리소스 하나는 칸(데이터의 ``contributes`` 첫 칸)에 항목
하나 ``{resource, layer, config}``를 낸다. 같은 칸에 여러 첨부가 쌓이면(``combine: append``,
층 순서 = 공통 → 팀 구성 → 에이전트 → 노드) 공급자가 범위 종류마다 가까운 층(뒤 항목)을 쓴다.
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import files
from typing import Any, Final

from ruamel.yaml import YAML

from agent_console_contracts import Resource, ResourceTypeDescriptor
from agent_console_contracts.memory import MemoryAccessConfig
from agent_console_resources import (
    Content,
    ContributeContext,
    Contribution,
    SchemaResourceType,
)

__all__ = [
    "MEMORY_RESOURCE_TYPE_RESOURCE",
    "MemoryResourceType",
    "access_item",
    "load_memory_resource_type",
    "memory_slot",
]

MEMORY_RESOURCE_TYPE_RESOURCE: Final = "data/memory_resource_type.yaml"
"""리소스 종류 디스크립터 데이터 위치(패키지 안 상대 경로)."""


def load_memory_resource_type(data: Mapping[str, Any] | None = None) -> ResourceTypeDescriptor:
    """디스크립터(데이터 + 계약 ``MemoryAccessConfig`` 스키마).

    Args:
        data: 디스크립터 데이터. 없으면 패키지 데이터 ``data/memory_resource_type.yaml``.
            ``config_schema``가 있으면 그것을 쓴다(없으면 계약 스키마).

    Raises:
        pydantic.ValidationError: 데이터가 디스크립터 형식이 아니다.
        ValueError: ``contributes``가 비었다(칸 이름이 필요하다).
    """
    if data is None:
        text = files(__package__ or __name__).joinpath(MEMORY_RESOURCE_TYPE_RESOURCE)
        loaded = YAML(typ="safe").load(text.read_text("utf-8"))
        data = loaded if isinstance(loaded, Mapping) else {}
    doc = dict(data)
    doc.setdefault("config_schema", MemoryAccessConfig.model_json_schema())
    descriptor = ResourceTypeDescriptor.model_validate(doc)
    if not descriptor.contributes:
        raise ValueError("메모리 리소스 종류 데이터에 contributes(칸 이름)가 없습니다")
    return descriptor


def memory_slot(descriptor: ResourceTypeDescriptor) -> str:
    """실행 묶음 칸 이름(``contributes`` 첫 칸)."""
    return descriptor.contributes[0]


def access_item(resource: Resource, layer: str | None) -> dict[str, Any]:
    """칸 항목 하나: ``{resource, layer, config}``(config = 첨부 덮어쓰기를 반영한 원문)."""
    return {"resource": resource.id, "layer": layer, "config": dict(resource.config)}


class MemoryResourceType(SchemaResourceType):
    """리소스 종류 ``memory``. entry point에는 클래스를 등록한다(인자 없이 패키지 데이터로).

    Args:
        descriptor: 디스크립터. 없으면 ``load_memory_resource_type()``.

    >>> from agent_console_contracts import Resource, ResourceAttachment
    >>> rtype = MemoryResourceType()
    >>> res = Resource(id="m", type=rtype.descriptor.id, name="메모리",
    ...                config={"scopes": [{"kind": "notes", "access": ["read"]}]})
    >>> rtype.validate(res)
    []
    >>> [(c.slot, c.value[0]["config"]["scopes"][0]["kind"])
    ...  for c in rtype.contribute(res, None, ContributeContext(ResourceAttachment(ref="m")))]
    [('memory', 'notes')]
    """

    def __init__(self, descriptor: ResourceTypeDescriptor | None = None) -> None:
        self.descriptor = descriptor if descriptor is not None else load_memory_resource_type()

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        """칸에 항목 하나(``access_item``)."""
        return [Contribution(memory_slot(self.descriptor), [access_item(resource, ctx.layer)])]
