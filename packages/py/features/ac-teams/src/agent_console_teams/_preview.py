"""묶음 미리보기(순수, design §2R.6·§R9.5): 노드 실행 묶음 + 경고(`BundlePreview`).

경고 = `ac-resources.build_bundle`의 묶음 경고(받지 않는 칸 등) + **서브에이전트 자리의 세션 공유
칸**(위임받는 노드의 칸 중 실행 백엔드 `capabilities.subagent_slots`에 없는 칸 — 대상별로 나뉘지
않고 위임자 세션에 합쳐진다). 위임받는 노드는 위임자 세션의 백엔드로 실행되므로 칸 판정은 세션
주인 노드의 유효 `backend` 능력으로 한다. 칸 이름·백엔드 이름은 이 모듈에 없다.

백엔드 선택 훅 `PreviewNotes.preview_notes(effective, bundle)`(예: claude-sdk의 "hook 감싸기 켜짐"
안내)가 있으면 그 이슈를 뒤에 붙인다. 훅 예외는 `team.validator_failed` 경고다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from agent_console_contracts import (
    Agent,
    AgentSettings,
    BackendCapabilities,
    BundlePreview,
    DelegationStrategyDescriptor,
    Issue,
    KnownIssueCodes,
    ResourceBundle,
    WorkspaceSettings,
)
from agent_console_registry import Registry
from agent_console_resources import ResourceLookup, ResourceType

from ._attachments import mask_node_settings
from ._issues import TeamIssueCodes
from ._plan import TeamPlan, runs_in_own_session
from ._settings import NodeSettings, node_bundle, node_settings

__all__ = ["PreviewNotes", "bundle_preview", "compose_preview", "session_owner"]


@runtime_checkable
class PreviewNotes(Protocol):
    """백엔드 선택 훅(X3): 묶음 미리보기에 덧붙일 백엔드만 아는 안내·경고.

    `effective`는 세션 주인 노드의 유효 설정(관측 설정 등 세션 단위 값), `bundle`은 미리보는 노드의
    묶음이다. 실행을 바꾸지 않는 설명용 이슈(대개 `info`)를 돌려준다.
    """

    def preview_notes(self, effective: AgentSettings, bundle: ResourceBundle) -> list[Issue]: ...


def _notes(
    hook: PreviewNotes | None, effective: AgentSettings, bundle: ResourceBundle, backend: str | None
) -> list[Issue]:
    if hook is None:
        return []
    try:
        return list(hook.preview_notes(effective, bundle))
    except Exception as exc:
        return [
            Issue(
                severity="warning",
                code=TeamIssueCodes.VALIDATOR_FAILED,
                message=f"백엔드 미리보기 안내 계산 중 오류: {type(exc).__name__}",
                details={"backend": backend},
            )
        ]


def session_owner(
    plan: TeamPlan,
    node_id: str,
    strategies: Mapping[str, DelegationStrategyDescriptor] | None = None,
) -> str:
    """노드가 실제로 도는 세션의 노드(위임받는 노드면 첫 위임자, 깊으면 끝까지 따라감).

    `strategies`를 주면 같은 세션이 아닌 방식(`shares_session` false)으로 불리는 노드에서 멈춘다
    (그 노드가 자기 세션의 주인이다). 주지 않으면 모든 위임을 같은 세션으로 본다.
    """
    seen = {node_id}
    current = node_id
    while True:
        if runs_in_own_session(plan, current, strategies) and plan.callers_of.get(current):
            return current
        callers = plan.callers_of.get(current, ())
        if not callers or callers[0].delegator in seen:
            return current
        current = callers[0].delegator
        seen.add(current)


def _shared_slot_issue(slot: str) -> Issue:
    return Issue(
        severity="warning",
        code=KnownIssueCodes.RESOURCE_SLOT_SESSION_SHARED,
        message=(
            f"서브에이전트 자리에서는 '{slot}' 칸을 대상별로 나눌 수 없어 위임자 세션에 합쳐집니다"
        ),
        details={"slot": slot},
    )


def compose_preview(
    settings: NodeSettings,
    *,
    resource_types: Registry[ResourceType],
    resources: ResourceLookup,
    capabilities: BackendCapabilities | None,
    member: bool = False,
) -> BundlePreview:
    """유효 설정 → `BundlePreview`(묶음 + 경고).

    Args:
        settings: 노드 유효 설정(`node_settings` 결과, 표시용이면 가린 값).
        resource_types, resources: 리소스 종류·조회(`node_bundle`과 같다).
        capabilities: 세션 백엔드 능력. None이면 칸 경고를 하지 않는다(모르는 백엔드).
        member: 위임받는 노드(서브에이전트 자리)인지. 참이면 세션 공유 칸을 경고한다.
    """
    accepted = capabilities.resource_slots if capabilities is not None else None
    composed = node_bundle(
        settings,
        resource_types=resource_types,
        resources=resources,
        accepted_slots=accepted,
        slot_notes=capabilities.slot_notes if capabilities is not None else None,
    )
    warnings = list(composed.issues)
    own = capabilities.subagent_slots if capabilities is not None else None
    if member and own is not None:
        for slot, value in composed.bundle.slots.items():
            if not value or slot in own or (accepted is not None and slot not in accepted):
                continue
            warnings.append(_shared_slot_issue(slot))
    return BundlePreview(bundle=composed.bundle, warnings=warnings)


def bundle_preview(
    plan: TeamPlan,
    node_id: str,
    *,
    resource_types: Registry[ResourceType],
    resources: ResourceLookup,
    backends: Mapping[str, BackendCapabilities],
    agents: Mapping[str, Agent] | None = None,
    workspace: WorkspaceSettings | None = None,
    strategies: Mapping[str, DelegationStrategyDescriptor] | None = None,
    notes: Mapping[str, PreviewNotes] | None = None,
) -> BundlePreview:
    """팀 구성 안 노드의 실행 묶음 미리보기(표시용: `x-secret` 평문은 `***`로 가린다).

    비밀 참조(`secret://`)는 그대로 둔다. 해석한 비밀 값 가리기는 호출자 몫이다(서버의
    `SecretResolver.redact`).

    Args:
        plan: `team_plan` 결과(저장본이든 초안이든).
        node_id: 노드 id.
        resource_types, resources: 리소스 종류·조회.
        backends: 백엔드 id → 능력(받는 칸·서브에이전트 칸).
        agents, workspace, strategies: `node_settings`와 같다.
        notes: 백엔드 id → 선택 훅 `PreviewNotes`(세션 주인의 백엔드 것만 부른다). 없으면 생략.
    """

    def settings_of(nid: str) -> NodeSettings:
        return node_settings(
            plan,
            nid,
            agents=agents,
            workspace=workspace,
            strategies=strategies,
            resource_types=resource_types,
            resources=resources,
        )

    settings = settings_of(node_id)
    owner = session_owner(plan, node_id, strategies)
    owner_settings = settings if owner == node_id else settings_of(owner)
    backend_id = owner_settings.effective.value.backend
    caps = backends.get(backend_id) if backend_id else None
    masked, lookup = mask_node_settings(settings, types=resource_types, resources=resources)
    preview = compose_preview(
        masked,
        resource_types=resource_types,
        resources=lookup,
        capabilities=caps,
        member=owner != node_id,
    )
    hook = notes.get(backend_id) if notes is not None and backend_id else None
    extra = _notes(hook, owner_settings.effective.value, preview.bundle, backend_id)
    if not extra:
        return preview
    return preview.model_copy(update={"warnings": [*preview.warnings, *extra]})
