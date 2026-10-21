"""agent-console-teams: 팀 구성 그래프의 의미(순수 로직, design §R1.2·§R2·§R3.1·§R14.2).

연결 종류·노드 타입·위임 방식·상호작용 종류의 이름을 모른다. 엣지 디스크립터(`scheduling`·
`invocation`·`interaction`·`connects`), 노드 타입 디스크립터(`role`·`executable`·`binds`),
위임 방식 디스크립터, 설정 데이터로만 판단한다.

공개 API:
    - 해석: ``team_plan(graph, *, node_types, edge_types, conventions) -> TeamPlan``
      (입구·답변 연결, 위임 연결 ``DelegationLink``, 리소스 연결 첨부 ``Attachment``, 노드별
      허용 상호작용 ``grants``), ``session_grant(plan, node_id, strategies)``(위임자 세션 grant,
      ``shares_session`` false인 방식의 대상은 빼고), ``shares_session(link, strategies)``·
      ``runs_in_own_session(plan, node_id, strategies)``(같은 세션 여부),
      ``describe_member(link, agent) -> MemberProfile``.
    - 검증: ``validate_team(graph, *, node_types, edge_types, strategies, agents, workspace,
      backends, settings_validators, ..., edge_checks=None) -> list[Issue]``(흐름 사이클은 사이클
      연결 ``cycle``이 닫으면 허용, 반복·혼합 위임 ``composable`` 규칙 포함), 코드
      ``TeamIssueCodes``, 중첩 팀 규칙(``teams=`` 팀 구성 조회 ``TeamLookup`` — 자기·순환 참조
      ``team.recursive``, ``team.nesting_exceeded``(``delegation.max_nesting``),
      ``team.team_not_found``, ``team.child_no_entry``),
      백엔드 훅 프로토콜 ``SettingsValidator``(``validate_settings(effective, grant)``).
      저장 시점 위임 검사(design §5.2R.7): 일반 규칙(방식 config 스키마
      ``delegation.invalid_config``, 같은 대상 ``delegation.duplicate_member``)은 늘 돌고, 방식
      고유 정적 검사·합침 이름 충돌은
      ``validate_team(delegation_checks=)`` 또는 ``delegation_static_issues(plan, checks, *,
      delegators, agents)``(대상 ``DelegationTarget``, ``delegation_targets``).
    - 설정: ``layers_for(plan, node_id, *, agent, workspace, scope_layers=()) -> list[Layer]``
      (4층 + 리소스 연결, ``scope_layers`` = 공통 바로 아래에 끼우는 일반 층 — 예: 프로젝트 층),
      ``agent_layers(agent, workspace, *, scope_layers=())``(팀 밖 2층),
      ``team_settings(graph, workspace, *, scope_layers=())``(팀 구성 수준 유효 값 — 공통 →
      범위 층 → 팀 구성, 예: Run의 유효 작업 폴더), ``Layer``(``ac-settings`` 다시 내보내기),
      ``resolve_settings(layers, *, rules, ...) -> NodeSettings``,
      ``node_settings``/``effective_settings(plan, node_id, ..., scope_layers=())``,
      ``node_bundle(settings, *, resource_types, resources, accepted_slots)``,
      ``merge_rules(workspace, graph)``, ``user_settings(workspace, graph)``,
      ``delegation_max_depth(workspace, graph)``, ``member_fields_for``, ``settings_value``,
      ``agent_settings_schema()``, ``AGENT_SETTINGS_FIELDS``, ``USER_SETTINGS_KEYS``.
    - 실행 백엔드 사전 점검(design §5.2R.5, 해결 순서 불변): ``resolve_backends(plan, *, agents,
      workspace, default_backend=None) -> {node_id: backend_id | None}``(백엔드를 쓰는 노드 =
      에이전트에 묶인 실행 가능 노드 또는 디스크립터 능력 ``conventions.backend_capability``,
      ``backend_nodes``), ``unresolved_backends(plan, resolved, *, agents)`` -> 세션 주인 중 빈 노드
      ``UnresolvedBackend{node_id, label}``, 화면 이름 ``node_display_name``.
    - 실행 경로(엔진 결과는 인자로): ``blocks_run(issue)``, ``team_rules_apply(engine_issues)``,
      ``merge_validation(engine_issues, team_issues, *, equivalents=DEFAULT_EQUIVALENTS)``(같은 뜻
      표는 데이터), ``run_blockers(engine_issues, team_issues)``,
      ``prepare_run(graph, plan, workspace, *, strategies) -> RunPreparation{grants,
      interaction_settings, flow_settings, delegation_settings}``,
      ``flow_settings(workspace, graph) -> FlowSettings``(유효 반복·실행 한도),
      ``delegation_settings(workspace, graph) -> DelegationSettings``(유효 위임 설정, 엔진 실행 중
      깊이 한도).
    - 중첩 팀(design §5R.7): ``TeamLookup``, ``find_team``, ``with_team_settings(graph, override)``
      (중첩 팀 노드의 팀 층 덮어쓰기), ``merge_overrides``. 계획 ``TeamPlan.team_refs``·
      ``team_versions``(``binds.kind == TeamConventions.team_kind``).
    - 약속: ``TeamConventions``(config 키·층 이름 데이터), ``DEFAULT_CONVENTIONS``, ``LayerName``.
    - 화면 요약: ``plan_summary(plan) -> TeamPlanSummary``(답변 속성은 엣지 디스크립터
      `reply_fields`로 읽음, ``reply_value``), ``validation_summary(issues) ->
      GraphValidationSummary``, 묶음 미리보기 ``bundle_preview(plan, node_id, *, backends, ...)
      -> BundlePreview``(받지 않는 칸 + 서브에이전트 자리 세션 공유 칸 경고, ``compose_preview``,
      ``session_owner``, 백엔드 선택 훅 ``PreviewNotes.preview_notes(effective, bundle)``로
      안내 추가),
      강제되지 않는 실행 범위 ``limits_warnings(value, enforce)``
      (`node_settings`·`resolve_settings`에 ``backends``를 주면 자동으로 더함).
    - 사용처: ``definition_references(kind, id, *, graphs, agents, workspace, node_types)``
      (노드 `binds`·설정 층 리소스 첨부로 찾는다). 반대 방향(쓰는 정의 — 에이전트·리소스·
      자식 팀 구성, 내보내기·프리셋 적용 순서용):
      ``graph_dependencies(plan, *, workspace)``·``agent_dependencies(agent, *, workspace)``
      -> ``DefinitionDependency[]``.
    - 첨부 검사: ``agent_attachments``·``graph_attachments(graph, *, plan)``·
      ``settings_attachments``
      (문서 기준 위치 붙은 첨부 ``PlacedAttachmentRef``), ``attachment_issues(placed, *, types,
      resources, secret_rules=None)``(첨부 ``config_override``를 덮은 결과의 종류 검사,
      path = 문서 기준),
      표시용 가리기 ``mask_effective_secrets``·``mask_node_settings``(`x-secret` 평문 → `***`).
    - 디스크립터 묶음: ``catalog_from_registries(registries) -> TeamCatalog``(플러그인 레지스트리
      묶음에서 노드·엣지·위임 방식·백엔드 디스크립터를 읽음, ``TeamCatalog.plan(graph)``).
    - 제안: ``SuggestionBuilder``(제안 데이터 ``GraphPatch`` 만들기 — 연결 추가 ``connect``·종류
      바꾸기 ``replace_kind``·좁히기 ``narrow``, 화면·다른 검사기 재사용).
"""

from agent_console_settings import Layer
from agent_console_teams._attachments import (
    PlacedAttachmentRef,
    agent_attachments,
    attachment_issues,
    graph_attachments,
    mask_effective_secrets,
    mask_node_settings,
    settings_attachments,
)
from agent_console_teams._backends import (
    UnresolvedBackend,
    backend_nodes,
    node_display_name,
    resolve_backends,
    unresolved_backends,
)
from agent_console_teams._catalog import TeamCatalog, catalog_from_registries
from agent_console_teams._conventions import DEFAULT_CONVENTIONS, LayerName, TeamConventions
from agent_console_teams._dependencies import (
    DefinitionDependency,
    agent_dependencies,
    graph_dependencies,
)
from agent_console_teams._issues import SettingsValidator, TeamIssueCodes
from agent_console_teams._nested import TeamLookup, find_team, merge_overrides, with_team_settings
from agent_console_teams._plan import (
    Attachment,
    DelegationLink,
    MemberProfile,
    TeamPlan,
    describe_member,
    runs_in_own_session,
    session_grant,
    shares_session,
    team_plan,
)
from agent_console_teams._preview import (
    PreviewNotes,
    bundle_preview,
    compose_preview,
    session_owner,
)
from agent_console_teams._references import definition_references
from agent_console_teams._rules_delegation_static import (
    DelegationTarget,
    delegation_static_issues,
    delegation_targets,
)
from agent_console_teams._run import (
    DEFAULT_EQUIVALENTS,
    DEFAULT_TEAM_SKIP_PREFIXES,
    RunPreparation,
    blocks_run,
    delegation_settings,
    flow_settings,
    merge_validation,
    prepare_run,
    run_blockers,
    team_rules_apply,
)
from agent_console_teams._settings import (
    AGENT_SETTINGS_FIELDS,
    USER_SETTINGS_KEYS,
    NodeSettings,
    agent_layers,
    agent_settings_schema,
    delegation_max_depth,
    effective_settings,
    layers_for,
    limits_warnings,
    member_fields_for,
    merge_rules,
    node_bundle,
    node_settings,
    resolve_settings,
    settings_value,
    team_settings,
    user_settings,
)
from agent_console_teams._suggest import SuggestionBuilder
from agent_console_teams._summary import plan_summary, reply_value, validation_summary
from agent_console_teams._validate import validate_team

__all__ = [
    "AGENT_SETTINGS_FIELDS",
    "DEFAULT_CONVENTIONS",
    "DEFAULT_EQUIVALENTS",
    "DEFAULT_TEAM_SKIP_PREFIXES",
    "USER_SETTINGS_KEYS",
    "Attachment",
    "DefinitionDependency",
    "DelegationLink",
    "DelegationTarget",
    "Layer",
    "LayerName",
    "MemberProfile",
    "NodeSettings",
    "PlacedAttachmentRef",
    "PreviewNotes",
    "RunPreparation",
    "SettingsValidator",
    "SuggestionBuilder",
    "TeamCatalog",
    "TeamConventions",
    "TeamIssueCodes",
    "TeamLookup",
    "TeamPlan",
    "UnresolvedBackend",
    "agent_attachments",
    "agent_dependencies",
    "agent_layers",
    "agent_settings_schema",
    "attachment_issues",
    "backend_nodes",
    "blocks_run",
    "bundle_preview",
    "catalog_from_registries",
    "compose_preview",
    "definition_references",
    "delegation_max_depth",
    "delegation_settings",
    "delegation_static_issues",
    "delegation_targets",
    "describe_member",
    "effective_settings",
    "find_team",
    "flow_settings",
    "graph_attachments",
    "graph_dependencies",
    "layers_for",
    "limits_warnings",
    "mask_effective_secrets",
    "mask_node_settings",
    "member_fields_for",
    "merge_overrides",
    "merge_rules",
    "merge_validation",
    "node_bundle",
    "node_display_name",
    "node_settings",
    "plan_summary",
    "prepare_run",
    "reply_value",
    "resolve_backends",
    "resolve_settings",
    "run_blockers",
    "runs_in_own_session",
    "session_grant",
    "session_owner",
    "settings_attachments",
    "settings_value",
    "shares_session",
    "team_plan",
    "team_rules_apply",
    "team_settings",
    "unresolved_backends",
    "user_settings",
    "validate_team",
    "validation_summary",
    "with_team_settings",
]
