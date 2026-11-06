"""리소스 종류 ``example-notes``: 에이전트에 붙이면 노트 읽기 도구를 받는다(opt-in).

디스크립터는 패키지 데이터(``data/resource_type.json``), 설정 스키마는 ``NotesAccess``다.
리소스 하나는 칸(``contributes`` 첫 칸)에 항목 하나 ``{resource, layer, config}``를 낸다. 같은
칸에 여러 첨부가 쌓이면(``combine: append``, 층 순서 = 먼 층 → 가까운 층) 공급자가 키마다
가까운 층 값을 쓴다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import Resource, ResourceTypeDescriptor, x_ui
from agent_console_nodes_core import RESOURCE_TYPES_EXTENSION
from agent_console_resources import Content, ContributeContext, Contribution, SchemaResourceType
from agent_console_runtime import Registries

__all__ = [
    "RESOURCE_TYPE_RESOURCE",
    "NotesAccess",
    "NotesResourceType",
    "load_resource_type",
    "notes_slot",
    "register",
]

RESOURCE_TYPE_RESOURCE: Final = "data/resource_type.json"
"""디스크립터 데이터 위치(패키지 안 상대 경로)."""


class NotesAccess(BaseModel):
    """에이전트가 받는 노트 읽기 범위입니다."""

    model_config = ConfigDict(extra="forbid")

    limit: int | None = Field(
        default=None,
        ge=1,
        title="기본 개수",
        description=(
            "도구 입력에 개수가 없을 때 읽을 노트 수입니다. 비우면 노트 모듈의 목록 한도를 "
            "따릅니다."
        ),
        json_schema_extra=x_ui(unit="개"),
    )
    tag: str | None = Field(
        default=None,
        min_length=1,
        title="태그",
        description="이 태그가 붙은 노트만 읽게 합니다. 비우면 모든 노트입니다.",
    )


def load_resource_type(data: Mapping[str, Any] | None = None) -> ResourceTypeDescriptor:
    """디스크립터(데이터 + ``NotesAccess`` 스키마).

    Args:
        data: 디스크립터 데이터. 없으면 패키지 데이터. ``config_schema``가 있으면 그것을 쓴다.

    Raises:
        pydantic.ValidationError: 데이터가 디스크립터 형식이 아니다.
        ValueError: ``contributes``가 비었다(칸 이름이 필요하다).
    """
    if data is None:
        text = files(__package__ or __name__).joinpath(RESOURCE_TYPE_RESOURCE).read_text("utf-8")
        data = json.loads(text)
    doc = dict(data or {})
    doc.setdefault("config_schema", NotesAccess.model_json_schema())
    descriptor = ResourceTypeDescriptor.model_validate(doc)
    if not descriptor.contributes:
        raise ValueError("노트 리소스 종류 데이터에 contributes(칸 이름)가 없습니다")
    return descriptor


def notes_slot(descriptor: ResourceTypeDescriptor) -> str:
    """실행 묶음 칸 이름(``contributes`` 첫 칸)."""
    return descriptor.contributes[0]


class NotesResourceType(SchemaResourceType):
    """리소스 종류 ``example-notes``. entry point에는 클래스를 등록한다(인자 없이 패키지 데이터로).

    >>> from agent_console_contracts import ResourceAttachment
    >>> rtype = NotesResourceType()
    >>> res = Resource(id="n", type=rtype.descriptor.id, name="노트", config={"tag": "회의"})
    >>> rtype.validate(res)
    []
    >>> [(c.slot, c.value[0]["config"])
    ...  for c in rtype.contribute(res, None, ContributeContext(ResourceAttachment(ref="n")))]
    [('example_notes', {'tag': '회의'})]
    """

    def __init__(self, descriptor: ResourceTypeDescriptor | None = None) -> None:
        self.descriptor = descriptor if descriptor is not None else load_resource_type()

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        """칸에 항목 하나(``{resource, layer, config}``)."""
        item = {"resource": resource.id, "layer": ctx.layer, "config": dict(resource.config)}
        return [Contribution(notes_slot(self.descriptor), [item])]


def register(registries: Registries) -> None:
    """설치 없이 쓰기: 설정 ``plugins.modules``에
    ``agent_console_example_link.resource_type:register``를 넣는다.

    entry point(``agent_console.resource_types``)로 설치했다면 부르지 않는다.
    """
    rtype = NotesResourceType()
    registries.extension(RESOURCE_TYPES_EXTENSION).register(rtype.descriptor.id, rtype)
