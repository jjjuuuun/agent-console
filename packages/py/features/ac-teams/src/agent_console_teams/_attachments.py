"""정의 문서 안의 리소스 첨부 찾기와 첨부 덮어쓰기 검사(1R.37, design §R12·§R9.5).

첨부가 있는 곳(설정 층 `resources[]`, 노드 층, 리소스 연결의 `config_override`)을 문서 기준
JSON Pointer와 함께 낸다. 노드·연결 종류 이름을 모른다: 노드 층 키와 연결 덮어쓰기 키는
`TeamConventions`, 리소스 연결은 `TeamPlan.attachments_of`(디스크립터로 해석)에서 온다.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from agent_console_contracts import (
    Agent,
    EffectiveSettings,
    Graph,
    Issue,
    ResourceAttachment,
    WorkspaceSettings,
)
from agent_console_registry import Registry
from agent_console_resources import (
    MaskedResources,
    PlacedAttachment,
    ResourceLookup,
    ResourceType,
    mask_attachment,
    validate_attachment,
)
from agent_console_secret_rules import SecretRules
from agent_console_teams._conventions import DEFAULT_CONVENTIONS, TeamConventions
from agent_console_teams._plan import TeamPlan
from agent_console_teams._settings import NodeSettings

__all__ = [
    "PlacedAttachmentRef",
    "agent_attachments",
    "attachment_issues",
    "graph_attachments",
    "mask_effective_secrets",
    "mask_node_settings",
    "settings_attachments",
]

RESOURCES_FIELD = "resources"


@dataclass(frozen=True, slots=True)
class PlacedAttachmentRef:
    """문서 안 첨부 하나와 그 위치.

    Attributes:
        path: 첨부(또는 연결 config) 위치 JSON Pointer.
        attachment: 첨부(연결이면 계획이 만든 첨부: ref = 연결된 리소스 노드의 리소스 id).
        override_path: 덮어쓰기 위치(None = `<path>/config_override`).
        ref_path: 리소스 id 위치(None = `<path>/ref`, 연결이면 리소스 노드의 config 필드).
    """

    path: str
    attachment: ResourceAttachment
    override_path: str | None = None
    ref_path: str | None = None


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _list(value: Any, base: str) -> Iterator[PlacedAttachmentRef]:
    """`resources` 목록(모델 또는 dict 원소) → 위치 붙은 첨부. 형식이 틀린 원소는 건너뛴다."""
    if not isinstance(value, list):
        return
    for index, item in enumerate(value):
        if isinstance(item, ResourceAttachment):
            att = item
        else:
            try:
                att = ResourceAttachment.model_validate(item)
            except (ValidationError, ValueError):
                continue
        yield PlacedAttachmentRef(f"{base}/{index}", att)


def _settings_list(settings: Any) -> Any:
    if settings is None:
        return None
    if isinstance(settings, Mapping):
        return settings.get(RESOURCES_FIELD)
    return getattr(settings, RESOURCES_FIELD, None)


def agent_attachments(agent: Agent) -> list[PlacedAttachmentRef]:
    """에이전트 층 첨부(`/resources/<i>`)."""
    return list(_list(agent.resources, f"/{RESOURCES_FIELD}"))


def settings_attachments(settings: WorkspaceSettings) -> list[PlacedAttachmentRef]:
    """공통 층 첨부(`/agent_defaults/resources/<i>`)."""
    return list(
        _list(_settings_list(settings.agent_defaults), f"/agent_defaults/{RESOURCES_FIELD}")
    )


def graph_attachments(
    graph: Graph,
    *,
    plan: TeamPlan | None = None,
    conventions: TeamConventions = DEFAULT_CONVENTIONS,
) -> list[PlacedAttachmentRef]:
    """팀 구성의 첨부: 팀 층(`/settings/resources/<i>`), 노드 층
    (`/nodes/<n>/config/<node_settings_key>/resources/<i>`), 리소스 연결(`/edges/<e>/config`,
    `plan`이 있을 때만 — 연결이 리소스 연결인지는 디스크립터로 정해진다).
    """
    out = list(_list(_settings_list(graph.settings), f"/settings/{RESOURCES_FIELD}"))
    key = conventions.node_settings_key
    for n, node in enumerate(graph.nodes):
        layer = node.config.get(key)
        base = f"/nodes/{n}/config/{_escape(key)}/{RESOURCES_FIELD}"
        out.extend(_list(_settings_list(layer), base))
    if plan is not None:
        edge_index = {edge.id: i for i, edge in enumerate(graph.edges)}
        node_index = {node.id: i for i, node in enumerate(graph.nodes)}
        override_key = _escape(conventions.edge_override_key)
        for attachments in plan.attachments_of.values():
            for att in attachments:
                index = edge_index.get(att.edge_id)
                if index is None:
                    continue
                desc = plan.node_descriptors.get(att.resource_node)
                binds = desc.binds if desc is not None else None
                pos = node_index.get(att.resource_node)
                ref_path = (
                    f"/nodes/{pos}/config/{_escape(binds.field)}"
                    if binds is not None and pos is not None
                    else None
                )
                base = f"/edges/{index}/config"
                out.append(
                    PlacedAttachmentRef(
                        base,
                        att.attachment,
                        override_path=f"{base}/{override_key}",
                        ref_path=ref_path or f"/edges/{index}/source",
                    )
                )
    return out


def attachment_issues(
    placed: Iterable[PlacedAttachmentRef],
    *,
    types: Registry[ResourceType],
    resources: ResourceLookup,
    secret_rules: SecretRules | None = None,
) -> list[Issue]:
    """첨부마다 `validate_attachment`(덮어쓰기를 리소스 config에 얕게 덮어 종류 검사).

    이슈 path는 문서 기준(`<첨부 위치>/config_override/...`). error가 있으면 저장을 막는 것은
    호출자가 정한다. 메시지에는 값이 없다. `secret_rules`는 리소스가 없는 첨부의 비밀 의심
    규칙(없으면 기본 규칙, `ac-secret-rules`).
    """
    issues: list[Issue] = []
    for item in placed:
        issues.extend(
            validate_attachment(
                item.attachment,
                types=types,
                resources=resources,
                path=item.path,
                override_path=item.override_path,
                ref_path=item.ref_path,
                secret_rules=secret_rules,
            )
        )
    return issues


def mask_effective_secrets(
    effective: EffectiveSettings,
    *,
    types: Registry[ResourceType],
    resources: ResourceLookup,
) -> EffectiveSettings:
    """유효 설정 `value.resources[].config_override`의 `x-secret` 평문을 `***`로 가린 사본(표시용).

    저장 검사 전에 저장된 데이터의 안전망이다. `secret://` 참조는 그대로.
    """
    current = effective.value.resources
    if not current:
        return effective
    masked = [mask_attachment(a, types=types, resources=resources) for a in current]
    if all(m is a for m, a in zip(masked, current, strict=True)):
        return effective
    value = effective.value.model_copy(update={"resources": masked})
    return effective.model_copy(update={"value": value})


def mask_node_settings(
    settings: NodeSettings,
    *,
    types: Registry[ResourceType],
    resources: ResourceLookup,
) -> tuple[NodeSettings, ResourceLookup]:
    """묶음 미리보기용: 첨부 덮어쓰기와 리소스 config의 `x-secret` 평문을 가린 설정·조회.

    Returns:
        (가린 `NodeSettings`, 가린 리소스를 돌려주는 `ResourceLookup`) — `node_bundle`에 넘긴다.
    """
    placed = tuple(
        PlacedAttachment(mask_attachment(p.attachment, types=types, resources=resources), p.layer)
        for p in settings.attachments
    )
    effective = mask_effective_secrets(settings.effective, types=types, resources=resources)
    masked = dataclasses.replace(settings, attachments=placed, effective=effective)
    return masked, MaskedResources(resources, types)
