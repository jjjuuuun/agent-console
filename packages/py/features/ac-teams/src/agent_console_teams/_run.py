"""실행 경로의 팀 쪽 판단(순수): 실행 차단 여부, 엔진·팀 검증 합치기, 실행 준비 값.

엔진(ac-runtime)을 import하지 않는다. 엔진 검증 결과는 **인자로** 받는다(design §2R.1).
앱(서버·CLI·테스트)은 "엔진 검증 → `validate_team` → `merge_validation`/`run_blockers` →
`prepare_run` → 엔진 시작" 순서로 조립만 한다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from agent_console_contracts import (
    DelegationSettings,
    DelegationStrategyDescriptor,
    FlowSettings,
    Graph,
    InteractionGrant,
    InteractionSettings,
    Issue,
    WorkspaceSettings,
)

from ._conventions import DEFAULT_CONVENTIONS, TeamConventions
from ._issues import TeamIssueCodes
from ._plan import TeamPlan, runs_in_own_session, session_grant
from ._settings import user_settings

__all__ = [
    "DEFAULT_EQUIVALENTS",
    "DEFAULT_TEAM_SKIP_PREFIXES",
    "RunPreparation",
    "blocks_run",
    "delegation_settings",
    "flow_settings",
    "merge_validation",
    "prepare_run",
    "run_blockers",
    "team_rules_apply",
]

DEFAULT_EQUIVALENTS: Final[Mapping[str, str]] = MappingProxyType(
    {TeamIssueCodes.AGENT_NOT_FOUND: "agent.not_found"}
)
"""같은 뜻 표(데이터): 팀 이슈 코드 → 같은 뜻의 엔진 이슈 코드 접두.

기본값은 기본 노드 플러그인이 내는 "에이전트 정의 없음"과 팀 규칙의 같은 이슈를 잇는다.
다른 플러그인 조합이면 호출자가 표를 바꿔 넘긴다."""

DEFAULT_TEAM_SKIP_PREFIXES: Final[tuple[str, ...]] = ("unknown",)
"""엔진 error 코드가 이 접두로 시작하면 팀 규칙을 돌리지 않는다(모르는 노드·연결 타입 등 —
팀 해석이 의미 없다). `ac-graph` 구조 검증 코드의 접두다."""

_INTERACTION_FIELD: Final = "interaction"
_FLOW_FIELD: Final = "flow"
_DELEGATION_FIELD: Final = "delegation"
"""`WorkspaceSettings`의 상호작용·흐름·위임 설정 필드 이름(계약 모델 필드)."""


def blocks_run(issue: Issue) -> bool:
    """실행을 막는 이슈인가: `issue.blocks_run`, 없으면 severity가 error인지."""
    return issue.blocks_run if issue.blocks_run is not None else issue.severity == "error"


def team_rules_apply(
    engine_issues: Iterable[Issue], *, skip_prefixes: Iterable[str] = DEFAULT_TEAM_SKIP_PREFIXES
) -> bool:
    """엔진 검증 결과를 보고 팀 규칙을 돌릴 의미가 있는지(모르는 타입 error가 없을 때 참)."""
    prefixes = tuple(skip_prefixes)
    return not any(i.severity == "error" and i.code.startswith(prefixes) for i in engine_issues)


def merge_validation(
    engine_issues: Iterable[Issue],
    team_issues: Iterable[Issue],
    *,
    equivalents: Mapping[str, str] = DEFAULT_EQUIVALENTS,
) -> list[Issue]:
    """엔진 이슈 + 팀 이슈(엔진 먼저, 각자 순서 유지). 같은 노드에 같은 뜻의 엔진 error가 있으면
    그 팀 이슈는 뺀다(한 문제를 두 번 알리지 않게).

    Args:
        engine_issues: 엔진 그래프 검증 결과(`GraphRuntime.validate`).
        team_issues: 팀 규칙 결과(`validate_team(graph_checks=False)`).
        equivalents: 같은 뜻 표 `{팀 코드: 엔진 코드 접두}`.
    """
    engine = list(engine_issues)
    errors = [(i.node_id, i.code) for i in engine if i.severity == "error" and i.node_id]
    merged = list(engine)
    for issue in team_issues:
        prefix = equivalents.get(issue.code)
        if (
            prefix is not None
            and issue.node_id is not None
            and any(node == issue.node_id and code.startswith(prefix) for node, code in errors)
        ):
            continue
        merged.append(issue)
    return merged


def run_blockers(
    engine_issues: Iterable[Issue],
    team_issues: Iterable[Issue],
    *,
    equivalents: Mapping[str, str] = DEFAULT_EQUIVALENTS,
) -> list[Issue]:
    """실행을 막는 이슈만(`merge_validation` 결과 중 `blocks_run`). 비어 있으면 실행해도 된다."""
    return [
        i
        for i in merge_validation(engine_issues, team_issues, equivalents=equivalents)
        if blocks_run(i)
    ]


@dataclass(frozen=True)
class RunPreparation:
    """엔진 시작에 넘길 팀 쪽 값.

    Attributes:
        grants: 노드 id → 허용 상호작용(`GraphRuntime.start(interaction_grants=)`). 엔진은 대기
            한도 기본값으로 쓴다. 위임 방식을 알면 세션 단위(`session_grant`)다.
        interaction_settings: 유효 상호작용 설정(기본값 → 공통 → 팀 구성,
            `GraphRuntime.start(interaction_settings=)`).
        flow_settings: 유효 반복·실행 한도(기본값 → 공통 → 팀 구성, `GraphRuntime.start(
            flow_settings=)`, design §5R.4).
        delegation_settings: 유효 위임 설정(기본값 → 공통 → 팀 구성, `GraphRuntime.start(
            delegation_settings=)` — 실행 중 위임 깊이 한도, design §5R.6).
    """

    grants: Mapping[str, InteractionGrant] = field(default_factory=dict)
    interaction_settings: InteractionSettings = field(default_factory=InteractionSettings)
    flow_settings: FlowSettings = field(default_factory=FlowSettings)
    delegation_settings: DelegationSettings = field(default_factory=DelegationSettings)


def prepare_run(
    graph: Graph,
    plan: TeamPlan,
    workspace: WorkspaceSettings | None,
    *,
    conventions: TeamConventions = DEFAULT_CONVENTIONS,
    strategies: Mapping[str, DelegationStrategyDescriptor] | None = None,
) -> RunPreparation:
    """팀 구성 실행에 필요한 값을 계산한다(grant·상호작용 설정·반복 한도·위임 설정).

    `strategies`(위임 방식 id → 디스크립터)를 주면 자기 세션을 여는 노드의 grant는 세션 grant
    (`session_grant`)다 — 같은 세션 방식(`shares_session` true) 대상의 종류·대기 한도가 위임자
    NodeRun 대기에 들어가고, 자기 세션 방식 대상의 값은 들어가지 않는다(design §5.2R.7). 주지
    않으면 노드 자신의 연결 grant(`plan.grants`)다.

    Raises:
        pydantic.ValidationError: 유효 상호작용·흐름·위임 설정이 계약 모델에 맞지 않을 때.
    """
    values = user_settings(workspace, graph, conventions=conventions).value
    raw = values.get(_INTERACTION_FIELD)
    interaction = InteractionSettings.model_validate(raw if isinstance(raw, Mapping) else {})
    flow = flow_settings(workspace, graph, conventions=conventions)
    delegation = delegation_settings(workspace, graph, conventions=conventions)
    return RunPreparation(
        grants=_engine_grants(plan, strategies),
        interaction_settings=interaction,
        flow_settings=flow,
        delegation_settings=delegation,
    )


def _engine_grants(
    plan: TeamPlan, strategies: Mapping[str, DelegationStrategyDescriptor] | None
) -> dict[str, InteractionGrant]:
    grants = dict(plan.grants)
    if strategies is None:
        return grants
    for nid in plan.delegates_of:
        if not runs_in_own_session(plan, nid, strategies):
            continue
        grant = session_grant(plan, nid, strategies)
        if grant is not None:
            grants[nid] = grant
    return grants


def flow_settings(
    workspace: WorkspaceSettings | None,
    graph: Graph | None,
    *,
    conventions: TeamConventions = DEFAULT_CONVENTIONS,
) -> FlowSettings:
    """유효 반복·실행 한도 설정 `flow`(기본값 → 공통 → 팀 구성, design §5R.4).

    Raises:
        pydantic.ValidationError: 합친 값이 계약 모델에 맞지 않을 때.
    """
    raw = user_settings(workspace, graph, conventions=conventions).value.get(_FLOW_FIELD)
    return FlowSettings.model_validate(raw if isinstance(raw, Mapping) else {})


def delegation_settings(
    workspace: WorkspaceSettings | None,
    graph: Graph | None,
    *,
    conventions: TeamConventions = DEFAULT_CONVENTIONS,
) -> DelegationSettings:
    """유효 위임 설정 `delegation`(기본값 → 공통 → 팀 구성, design §5R.6·§5R.7).

    Raises:
        pydantic.ValidationError: 합친 값이 계약 모델에 맞지 않을 때.
    """
    raw = user_settings(workspace, graph, conventions=conventions).value.get(_DELEGATION_FIELD)
    return DelegationSettings.model_validate(raw if isinstance(raw, Mapping) else {})
