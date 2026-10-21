"""노드 유효 설정: 층 목록 만들기(`layers_for`)와 병합(`resolve_settings`, design §R2, §R12.1).

층 = 공통(`WorkspaceSettings.agent_defaults`) → [범위 층(`scope_layers`)]
→ 팀 구성(`Graph.settings`) → 에이전트(정의) → 노드(노드 config + 리소스 연결 첨부).
층 목록은 데이터(`ac-settings.Layer`)라서 호출자가 층을 더하거나 뺄 수 있다.
범위 층은 호출자가 공통 바로 아래에 끼우는 일반 층이다(예: 프로젝트 층, design §5.2R.6 —
이 패키지는 프로젝트를 모른다). 층 값은 **지정한 필드만**(`exclude_unset`) 읽는다 —
모델 기본값은 층 값이 아니다.

병합은 `ac-settings.resolve_layers`, 첨부(`resources`)는 `ac-resources`의 `keyed_attachments`
전략(같은 전략 표)으로 합친다. 필드 이름은 계약 스키마(`x-merge`·`x-widen`)에서 온다.
"""

from __future__ import annotations

import copy
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from agent_console_contracts import (
    Agent,
    AgentSettings,
    BackendCapabilities,
    DelegationStrategyDescriptor,
    EffectiveSettings,
    Graph,
    GraphSettings,
    Issue,
    IssueSeverity,
    KnownIssueCodes,
    SettingsLayerInfo,
    WorkspaceSettings,
)
from agent_console_registry import Registry
from agent_console_resources import (
    ComposedBundle,
    PlacedAttachment,
    ResourceLookup,
    ResourceType,
    attachment_slot_key,
    build_bundle,
    placed_from_resolved,
    resource_strategies,
)
from agent_console_settings import (
    Layer,
    MergeIssue,
    Resolved,
    StrategyTable,
    find_widenings,
    resolve_layers,
)

from ._conventions import DEFAULT_CONVENTIONS, TeamConventions
from ._plan import TeamPlan

__all__ = [
    "AGENT_SETTINGS_FIELDS",
    "USER_SETTINGS_KEYS",
    "NodeSettings",
    "agent_layers",
    "agent_settings_schema",
    "delegation_max_depth",
    "effective_settings",
    "layers_for",
    "limits_warnings",
    "member_fields_for",
    "merge_rules",
    "node_bundle",
    "node_settings",
    "resolve_settings",
    "settings_value",
    "team_settings",
    "user_settings",
]

AGENT_SETTINGS_FIELDS: tuple[str, ...] = tuple(AgentSettings.model_fields)
"""`AgentSettings` 필드 이름(계약에서 읽음). 에이전트 설정 층 값은 이 필드만 담는다."""

USER_SETTINGS_KEYS: tuple[str, ...] = tuple(
    name for name in GraphSettings.model_fields if name not in AgentSettings.model_fields
)
"""에이전트 설정 밖의 사용자 설정 묶음(채팅·편집기·위임·상호작용·병합 규칙 등, 계약에서 읽음)."""

_SCHEMA: dict[str, Any] = AgentSettings.model_json_schema()


def agent_settings_schema() -> dict[str, Any]:
    """`AgentSettings` JSON Schema 복사본(`x-merge`·`x-widen` 주석 포함)."""
    return copy.deepcopy(_SCHEMA)


def settings_value(
    model: BaseModel | Mapping[str, Any] | None, fields: Collection[str] = AGENT_SETTINGS_FIELDS
) -> dict[str, Any] | None:
    """층 값으로 쓸 dict. 모델이면 **지정한 필드만**(`exclude_unset`), dict면 그대로(복사).

    `fields`에 없는 키는 뺀다. `None`이면 `None`(이 층은 아무것도 지정하지 않음).
    """
    if model is None:
        return None
    if isinstance(model, BaseModel):
        raw: dict[str, Any] = model.model_dump(mode="json", exclude_unset=True)
    else:
        raw = copy.deepcopy(dict(model))
    return {k: v for k, v in raw.items() if k in fields}


def _common_value(workspace: WorkspaceSettings | None) -> dict[str, Any] | None:
    if workspace is None:
        return None
    value = settings_value(workspace.agent_defaults) or {}
    # 읽기 호환(design §R9.3): 이전 형식 default_backend는 공통 층 backend로 본다.
    if "backend" not in value and workspace.default_backend:
        value["backend"] = workspace.default_backend
    return value


def agent_layers(
    agent: Agent | None,
    workspace: WorkspaceSettings | None,
    *,
    conventions: TeamConventions = DEFAULT_CONVENTIONS,
    scope_layers: Sequence[Layer] = (),
) -> list[Layer]:
    """팀 구성 밖(에이전트 화면)의 층: 공통 → [범위 층] → 에이전트.

    Args:
        agent: 에이전트 정의(없으면 에이전트 층이 비어 있다).
        workspace: 공통 설정(없으면 공통 층이 비어 있다).
        conventions: 층 id·이름 약속.
        scope_layers: 공통 바로 아래에 그대로 끼울 층(예: 프로젝트 층). 층 id는 다른 층과 겹치면
            안 된다(`resolve_settings`가 `ValueError`). 기본은 없음(지금과 같음).
    """
    c = conventions
    return [
        Layer(c.common_layer.id, c.common_layer.label, _common_value(workspace), "settings"),
        *scope_layers,
        Layer(
            c.agent_layer.id,
            c.agent_layer.label,
            settings_value(agent),
            f"agent:{agent.id}" if agent is not None else None,
        ),
    ]


def layers_for(
    plan: TeamPlan,
    node_id: str,
    *,
    agent: Agent | None,
    workspace: WorkspaceSettings | None,
    scope_layers: Sequence[Layer] = (),
) -> list[Layer]:
    """팀 구성 안 노드 하나의 설정 층: 공통 → [범위 층] → 팀 구성 → 에이전트 → 노드.

    노드 층 = 노드 config의 설정(`conventions.node_settings_key`) + 리소스 연결 첨부
    (`plan.attachments_of`, 그래프 순서로 `resources` 끝에 붙음).

    Args:
        plan: `team_plan` 결과.
        node_id: 노드 id(없는 노드면 노드 층이 비어 있다).
        agent: 이 노드에 묶인 에이전트 정의(없으면 에이전트 층이 비어 있다).
        workspace: 공통 설정(없으면 공통 층이 비어 있다).
        scope_layers: 공통 바로 아래에 그대로 끼울 층(예: 프로젝트 층의 작업 폴더·설정). 이 함수는
            층의 뜻을 모른다. 층 id는 다른 층과 겹치면 안 된다. 기본은 없음(지금과 같음).
    """
    c = plan.conventions
    graph = plan.graph
    node = plan.node(node_id)
    node_value: dict[str, Any] | None = None
    if node is not None:
        raw = node.config.get(c.node_settings_key)
        node_value = settings_value(raw) if isinstance(raw, Mapping) else None
        attached = plan.attachments_of.get(node_id, ())
        if attached:
            node_value = dict(node_value or {})
            existing = node_value.get("resources")
            items = list(existing) if isinstance(existing, list) else []
            items.extend(a.attachment.model_dump(mode="json", exclude_unset=True) for a in attached)
            node_value["resources"] = items
    return [
        Layer(c.common_layer.id, c.common_layer.label, _common_value(workspace), "settings"),
        *scope_layers,
        Layer(
            c.team_layer.id, c.team_layer.label, settings_value(graph.settings), f"graph:{graph.id}"
        ),
        Layer(
            c.agent_layer.id,
            c.agent_layer.label,
            settings_value(agent),
            f"agent:{agent.id}" if agent is not None else None,
        ),
        Layer(c.node_layer.id, c.node_layer.label, node_value, f"graph:{graph.id}#{node_id}"),
    ]


def team_settings(
    graph: Graph | None,
    workspace: WorkspaceSettings | None,
    *,
    scope_layers: Sequence[Layer] = (),
    conventions: TeamConventions = DEFAULT_CONVENTIONS,
) -> NodeSettings:
    """팀 구성 수준의 유효 에이전트 설정: 공통 → [범위 층] → 팀 구성(에이전트·노드 층 없음).

    실행 하나의 기준 값(예: Run의 유효 작업 폴더)을 고를 때 쓴다. 노드마다 값은 `node_settings`.

    >>> from agent_console_settings import Layer
    >>> ws = WorkspaceSettings.model_validate({"agent_defaults": {"working_directory": "/a"}})
    >>> team_settings(None, ws).effective.value.working_directory
    '/a'
    >>> scope = [Layer("project", "프로젝트", {"working_directory": "/p"})]
    >>> team_settings(None, ws, scope_layers=scope).effective.value.working_directory
    '/p'
    """
    c = conventions
    layers = [
        Layer(c.common_layer.id, c.common_layer.label, _common_value(workspace), "settings"),
        *scope_layers,
    ]
    if graph is not None:
        layers.append(
            Layer(
                c.team_layer.id,
                c.team_layer.label,
                settings_value(graph.settings),
                f"graph:{graph.id}",
            )
        )
    return resolve_settings(layers, rules=merge_rules(workspace, graph))


def user_settings(
    workspace: WorkspaceSettings | None,
    graph: Graph | None,
    *,
    conventions: TeamConventions = DEFAULT_CONVENTIONS,
) -> Resolved:
    """에이전트 설정 밖 사용자 설정 묶음(`USER_SETTINGS_KEYS`)의 유효 값: 기본값 → 공통 → 팀 구성.

    기본값 층은 계약 모델의 기본값, 공통·팀 구성 층은 지정한 값만(`exclude_unset`) 읽는다.
    """
    c = conventions
    keys = USER_SETTINGS_KEYS
    defaults = settings_value(WorkspaceSettings().model_dump(mode="json"), keys)
    return resolve_layers(
        [
            Layer(c.defaults_layer.id, c.defaults_layer.label, defaults),
            Layer(c.common_layer.id, c.common_layer.label, settings_value(workspace, keys)),
            Layer(
                c.team_layer.id,
                c.team_layer.label,
                settings_value(graph.settings if graph is not None else None, keys),
            ),
        ]
    )


def merge_rules(workspace: WorkspaceSettings | None, graph: Graph | None) -> dict[str, str]:
    """사용자 병합 규칙 `settings_merge`(공통 → 팀 구성, 키별로 팀 구성이 이김)."""
    rules: dict[str, str] = {}
    if workspace is not None:
        rules.update(workspace.settings_merge)
    if graph is not None and graph.settings is not None and graph.settings.settings_merge:
        rules.update(graph.settings.settings_merge)
    return {k: v for k, v in rules.items() if isinstance(v, str)}


def delegation_max_depth(workspace: WorkspaceSettings | None, graph: Graph | None) -> int | None:
    """설정 `delegation.max_depth`(공통 → 팀 구성). 비어 있으면 None."""
    value = user_settings(workspace, graph).value.get("delegation")
    depth = value.get("max_depth") if isinstance(value, Mapping) else None
    return depth if isinstance(depth, int) and not isinstance(depth, bool) else None


@dataclass(frozen=True)
class NodeSettings:
    """`resolve_settings` 결과.

    Attributes:
        effective: 계약 `EffectiveSettings`(값·출처·층·경고·적용 안 되는 필드).
        resolved: `ac-settings` 원 결과(`layers_under` 등).
        attachments: 병합 후 적용 순서의 첨부와 출처 층(묶음 조립 입력).
        strategies: 병합에 쓴 전략 표(묶음 조립에도 같은 표를 쓴다).
    """

    effective: EffectiveSettings
    resolved: Resolved
    attachments: tuple[PlacedAttachment, ...]
    strategies: StrategyTable


def _merge_issue(issue: MergeIssue) -> Issue:
    code = issue.code if issue.code.startswith("resource.") else f"settings.{issue.code}"
    severity: IssueSeverity = (
        "info" if code in ("resource.replace_unmatched", "resource.remove_unmatched") else "warning"
    )
    return Issue(
        severity=severity,
        code=code,
        message=issue.message,
        path=issue.pointer or None,
        details={"layer": issue.layer} if issue.layer else {},
    )


def _validated(value: dict[str, Any]) -> tuple[AgentSettings, list[Issue]]:
    """유효 값 → `AgentSettings`. 형식이 틀린 최상위 필드는 빼고 경고한다.

    입력값은 메시지에 넣지 않는다(비밀 누출 방지).
    """
    data = dict(value)
    issues: list[Issue] = []
    for _ in range(len(AGENT_SETTINGS_FIELDS) + 1):
        try:
            return AgentSettings.model_validate(data), issues
        except ValidationError as exc:
            bad = {str(err["loc"][0]) for err in exc.errors() if err.get("loc")}
            bad &= set(data)
            if not bad:
                break
            for name in sorted(bad):
                data.pop(name)
                issues.append(
                    Issue(
                        severity="warning",
                        code="settings.invalid_value",
                        message=f"설정 '{name}'의 형식이 맞지 않아 적용하지 않았습니다",
                        path=f"/{name}",
                    )
                )
    return AgentSettings(), issues


LIMITS_FIELD = "limits"
"""`AgentSettings`에서 실행 범위 묶음의 필드 이름(계약 필드, `limits_warnings`가 읽는다)."""


def limits_warnings(
    value: AgentSettings,
    enforce: BaseModel | Mapping[str, Any],
    *,
    backend: str | None = None,
) -> list[Issue]:
    """`limits`에 값이 있는데 백엔드가 강제하지 못하는 항목마다 경고 `limits.not_enforced`.

    필드↔능력 대응은 **같은 키 이름**이라는 계약 관례뿐이다(코드에 필드 목록 없음). `enforce`에
    없는 이름은 강제하지 못하는 것으로 본다(안전한 쪽, R4.5).

    Args:
        value: 유효 설정.
        enforce: 백엔드 `capabilities.enforce`(모델 또는 이름 → bool).
        backend: 경고 `details.backend`에 넣을 백엔드 id(표시용).

    Returns:
        경고 목록(path = `/limits/<필드>`). `limits`가 없으면 빈 목록.
    """
    limits = getattr(value, LIMITS_FIELD, None)
    if not isinstance(limits, BaseModel):
        return []
    table = enforce.model_dump() if isinstance(enforce, BaseModel) else dict(enforce)
    out: list[Issue] = []
    for name in limits.model_dump(mode="json", exclude_none=True):
        if table.get(name) is True:
            continue
        details: dict[str, Any] = {"field": name}
        if backend is not None:
            details["backend"] = backend
        out.append(
            Issue(
                severity="warning",
                code=KnownIssueCodes.LIMITS_NOT_ENFORCED,
                message=f"실행 백엔드가 실행 범위 '{name}'을(를) 강제하지 못합니다(설정만 전달됨)",
                path=f"/{LIMITS_FIELD}/{name}",
                details=details,
            )
        )
    return out


def resolve_settings(
    layers: Iterable[Layer],
    *,
    rules: Mapping[str, str] | None = None,
    resource_types: Registry[ResourceType] | None = None,
    resources: ResourceLookup | None = None,
    member_fields: Collection[str] | None = None,
    backends: Mapping[str, BackendCapabilities] | None = None,
) -> NodeSettings:
    """설정 층들을 병합해 유효 설정·출처·경고를 만든다.

    순서(1R.6 연결 방법): 첨부 전략 표 `resource_strategies(slot_key_of=...)` → `resolve_layers`
    (계약 스키마·`rules`) → `placed_from_resolved`. 넓힘 경고는 `find_widenings`(스키마 `x-widen`).

    Args:
        layers: 위 층부터(`layers_for`·`agent_layers` 결과, 또는 직접 만든 목록).
        rules: 사용자 병합 규칙(`merge_rules`).
        resource_types, resources: 둘 다 주면 첨부 `replace`가 종류의 슬롯 키로 같은 자리를 찾는다.
        member_fields: 이 자리에서 적용되는 필드(위임받는 노드면 위임 방식 `member_fields`).
            주면 나머지 필드가 `inapplicable`이 된다.
        backends: 백엔드 id → 능력. 주면 유효 `backend`의 `enforce`로 `limits_warnings`를 더한다
            (`limits`가 적용되지 않는 자리거나 모르는 백엔드면 건너뛴다).

    Raises:
        ValueError: 층 id가 비었거나 겹칠 때.
    """
    layer_list = list(layers)
    key_of = (
        attachment_slot_key(resource_types, resources)
        if resource_types is not None and resources is not None
        else None
    )
    table = resource_strategies(slot_key_of=key_of)
    resolved = resolve_layers(layer_list, schema=_SCHEMA, rules=rules, strategies=table)
    warnings = [_merge_issue(i) for i in resolved.issues]
    for w in find_widenings(layer_list, schema=_SCHEMA, rules=rules, strategies=table):
        warnings.append(
            Issue(
                severity="warning",
                code="settings.widened",
                message="아래 층이 위 층보다 범위를 넓혔습니다",
                path=w.pointer,
                details={
                    "layer": w.layer,
                    "upper_layer": w.upper_layer,
                    "check": w.check,
                    "added": [str(a) for a in w.added],
                },
            )
        )
    value, invalid = _validated(resolved.value)
    warnings.extend(invalid)
    inapplicable = (
        [f"/{name}" for name in AGENT_SETTINGS_FIELDS if name not in member_fields]
        if member_fields is not None
        else []
    )
    caps = backends.get(value.backend) if backends is not None and value.backend else None
    if caps is not None and f"/{LIMITS_FIELD}" not in inapplicable:
        warnings.extend(limits_warnings(value, caps.enforce, backend=value.backend))
    effective = EffectiveSettings(
        value=value,
        provenance=dict(resolved.provenance),
        layers=[
            SettingsLayerInfo(id=i.id, label=i.label, source=i.source) for i in resolved.layers
        ],
        warnings=warnings,
        inapplicable=inapplicable,
    )
    return NodeSettings(effective, resolved, tuple(placed_from_resolved(resolved)), table)


def member_fields_for(
    plan: TeamPlan,
    node_id: str,
    strategies: Mapping[str, DelegationStrategyDescriptor] | None,
) -> list[str] | None:
    """위임받는 노드면 그 노드에 적용되는 필드(부르는 위임 방식들의 `member_fields` 교집합).

    위임받지 않거나 위임 방식 디스크립터를 모르면 None(모든 필드 적용).
    """
    fields: set[str] | None = None
    for link in plan.callers_of.get(node_id, ()):
        desc = (strategies or {}).get(link.strategy)
        if desc is None:
            continue
        fields = set(desc.member_fields) if fields is None else fields & set(desc.member_fields)
    if fields is None:
        return None
    return [name for name in AGENT_SETTINGS_FIELDS if name in fields]


def node_settings(
    plan: TeamPlan,
    node_id: str,
    *,
    agents: Mapping[str, Agent] | None = None,
    workspace: WorkspaceSettings | None = None,
    strategies: Mapping[str, DelegationStrategyDescriptor] | None = None,
    resource_types: Registry[ResourceType] | None = None,
    resources: ResourceLookup | None = None,
    backends: Mapping[str, BackendCapabilities] | None = None,
    scope_layers: Sequence[Layer] = (),
) -> NodeSettings:
    """팀 구성 안 노드 하나의 유효 설정(4층 + 리소스 연결 첨부 + 출처 + 적용 안 되는 필드).

    Args:
        plan: `team_plan` 결과.
        node_id: 노드 id.
        agents: 에이전트 정의 id → 정의. 노드에 묶인 정의를 여기서 찾는다.
        workspace: 공통 설정.
        strategies: 위임 방식 id → 디스크립터(`inapplicable` 계산).
        resource_types, resources: 첨부 `replace`의 슬롯 키 계산(선택).
        backends: 백엔드 id → 능력(선택). 주면 강제되지 않는 실행 범위 경고를 더한다.
        scope_layers: 공통 바로 아래에 끼울 층(`layers_for` 참고, 선택).
    """
    ref = plan.agent_refs.get(node_id)
    agent = (agents or {}).get(ref) if ref is not None else None
    return resolve_settings(
        layers_for(plan, node_id, agent=agent, workspace=workspace, scope_layers=scope_layers),
        rules=merge_rules(workspace, plan.graph),
        resource_types=resource_types,
        resources=resources,
        member_fields=member_fields_for(plan, node_id, strategies),
        backends=backends,
    )


def effective_settings(
    plan: TeamPlan,
    node_id: str,
    *,
    agents: Mapping[str, Agent] | None = None,
    workspace: WorkspaceSettings | None = None,
    strategies: Mapping[str, DelegationStrategyDescriptor] | None = None,
    resource_types: Registry[ResourceType] | None = None,
    resources: ResourceLookup | None = None,
    backends: Mapping[str, BackendCapabilities] | None = None,
    scope_layers: Sequence[Layer] = (),
) -> EffectiveSettings:
    """`node_settings(...).effective`(계약 모델만 필요할 때)."""
    return node_settings(
        plan,
        node_id,
        agents=agents,
        workspace=workspace,
        strategies=strategies,
        resource_types=resource_types,
        resources=resources,
        backends=backends,
        scope_layers=scope_layers,
    ).effective


def node_bundle(
    settings: NodeSettings,
    *,
    resource_types: Registry[ResourceType],
    resources: ResourceLookup,
    accepted_slots: Collection[str] | None = None,
    slot_notes: Mapping[str, str] | None = None,
) -> ComposedBundle:
    """유효 설정의 첨부로 실행 묶음(출처 포함)을 만든다(`ac-resources.build_bundle`, 같은 전략 표).

    `accepted_slots`(백엔드 `capabilities.resource_slots`)를 주면 받지 못하는 칸을 경고한다.
    `slot_notes`(백엔드 `capabilities.slot_notes`)는 그 경고에 붙일 칸별 설명이다.
    """
    return build_bundle(
        settings.attachments,
        types=resource_types,
        resources=resources,
        accepted_slots=accepted_slots,
        strategies=settings.strategies,
        slot_notes=slot_notes,
    )
