"""프로젝트 실행 사전 점검(design §PI.4.5 규칙 1~5·8, §PI.5 경로 지킴, §PI.16 ②).

결정 K33-7·K33-18·K33-34를 따른다.

서버·HTTP 없이 쓰는 순수 부품이다. 오류 본문(``ErrorInfo``)만 만들고 실행을 막는 일은 부르는
쪽(``mod-runs``)이 한다.

- ``required_error``: 프로젝트 없이 시작(422 ``project.required``).
- ``unknown_error``: 등록되지 않은 프로젝트(404 ``project.not_found``).
- ``view_error(view)``: 프로젝트 상태(409 ``project.folder_missing``·``project.manifest_invalid``)와
  기록 DB(409 ``project.records_unavailable``). 상태 판정은 ``ProjectView``(``mod-projects``)가
  한 값을 그대로 읽는다.
- ``space_error(exc)``: 공간을 열다 난 예외 → 409(예외의 ``code``).
- ``not_imported_error``: 실행 대상이 프로젝트 공간에 없음(422 ``project.not_imported``,
  ``in_library``).
- ``outside_paths_of_graph``: 노드마다 유효 설정의 ``x-path`` 값이 프로젝트 폴더 밖인 것(층
  이름 포함, 중첩 팀의 자식·손자 팀 구성 노드까지). ``outside_folder_error``가 422
  ``project.outside_folder`` 본문을 만든다.

문구·해결 버튼은 ``PreflightTexts`` **데이터**다(바꿔 넘길 수 있다).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agent_console_contracts import (
    Agent,
    ErrorCodes,
    ErrorInfo,
    Fix,
    FixAction,
    FixTarget,
    Graph,
    KnownProjectStatuses,
    KnownRecordsUnavailableReasons,
    OutsideFolderPath,
    ProjectFolderUnavailableDetails,
    ProjectNotImportedDetails,
    ProjectOutsideFolderDetails,
    ProjectRecordsUnavailableDetails,
    ProjectView,
    WorkspaceSettings,
)
from agent_console_projects import outside_paths
from agent_console_teams import (
    Layer,
    TeamCatalog,
    TeamPlan,
    agent_settings_schema,
    node_settings,
    with_team_settings,
)

__all__ = [
    "DEFAULT_PREFLIGHT_TEXTS",
    "NESTED_NODE_SEPARATOR",
    "PreflightTexts",
    "TeamFinder",
    "not_imported_error",
    "outside_folder_error",
    "outside_paths_of_graph",
    "required_error",
    "space_error",
    "unknown_error",
    "view_error",
]


@dataclass(frozen=True, slots=True)
class PreflightTexts:
    """사전 점검 오류의 문구·해결 버튼 데이터.

    Attributes:
        required: ``project.required`` 문구.
        unknown: ``project.not_found`` 문구(``{project}``).
        folder_unavailable: ``project.folder_missing`` 문구(``{project}``·``{status}``).
        manifest_invalid: ``project.manifest_invalid`` 문구(``{project}``).
        records_unavailable: ``project.records_unavailable`` 문구(``{project}``·``{reason}``).
        not_imported: ``project.not_imported`` 문구(``{project}``·``{kind}``·``{id}``).
        outside_folder: ``project.outside_folder`` 문구(``{project}``·``{count}``).
        projects_role: 해결 버튼이 데려갈 웹 라우트 역할(프로젝트 화면).
        pick_label: [프로젝트 고르기] 버튼 문구(``project.required``).
        open_label: [프로젝트 열기] 버튼 문구(상태·기록 오류, 대상 ``id`` = 프로젝트 id).
    """

    required: str = "프로젝트를 고른 뒤 실행하세요. 실행은 프로젝트 폴더에서만 합니다."
    unknown: str = "프로젝트 '{project}'을(를) 찾을 수 없습니다."
    folder_unavailable: str = (
        "프로젝트 '{project}'의 폴더를 쓸 수 없어 시작하지 않았습니다(상태: {status})."
    )
    manifest_invalid: str = "프로젝트 '{project}'의 설정 파일을 읽을 수 없어 시작하지 않았습니다."
    records_unavailable: str = (
        "프로젝트 '{project}'에 대화·실행 기록을 저장할 수 없어 시작하지 않았습니다({reason})."
    )
    not_imported: str = (
        "'{id}'은(는) 프로젝트 '{project}'의 구성에 없습니다. 먼저 이 프로젝트로 가져오세요."
    )
    outside_folder: str = (
        "설정의 경로 {count}개가 프로젝트 '{project}' 폴더 밖을 가리켜 시작하지 않았습니다."
    )
    projects_role: str = "projects"
    pick_label: str = "프로젝트 고르기"
    open_label: str = "프로젝트 열기"


DEFAULT_PREFLIGHT_TEXTS = PreflightTexts()
"""기본 문구·웹 역할(``projects`` = ``mod-projects`` 웹 라우트 역할)."""


def _fix(label: str, role: str, item_id: str | None = None) -> Fix:
    return Fix(actions=[FixAction(label=label, target=FixTarget(role=role, id=item_id))])


def _dump(model: Any) -> dict[str, Any]:
    data: dict[str, Any] = model.model_dump(mode="json", exclude_none=True)
    return data


def required_error(texts: PreflightTexts = DEFAULT_PREFLIGHT_TEXTS) -> ErrorInfo:
    """422 ``project.required``(fix = [프로젝트 고르기]).

    >>> required_error().code
    'project.required'
    """
    return ErrorInfo(
        code=ErrorCodes.PROJECT_REQUIRED,
        message=texts.required,
        fix=_fix(texts.pick_label, texts.projects_role),
    )


def unknown_error(project_id: str, texts: PreflightTexts = DEFAULT_PREFLIGHT_TEXTS) -> ErrorInfo:
    """404 ``project.not_found``(``details.project_id``, fix = [프로젝트 고르기])."""
    return ErrorInfo(
        code=ErrorCodes.PROJECT_NOT_FOUND,
        message=texts.unknown.format(project=project_id),
        details={"project_id": project_id},
        fix=_fix(texts.pick_label, texts.projects_role),
    )


def view_error(
    view: ProjectView, texts: PreflightTexts = DEFAULT_PREFLIGHT_TEXTS
) -> ErrorInfo | None:
    """프로젝트 상태·기록 DB로 시작을 막을 오류(없으면 None).

    순서: 상태가 ``manifest_invalid`` → 409 ``project.manifest_invalid``, 그 밖에 ``ready``가 아님 →
    409 ``project.folder_missing``(``ProjectFolderUnavailableDetails``), 기록 DB를 쓸 수 없음
    (``records_writable`` 거짓 — 폴더에 쓸 수 없는 ``config_writable=false`` 포함, K33-34) → 409
    ``project.records_unavailable``(``details`` = ``records_issue.details`` 그대로, 없으면 이유
    ``readonly``).

    >>> from agent_console_contracts import Project
    >>> ok = ProjectView(project=Project(id="app", name="App", folder="/w/app"), status="ready")
    >>> view_error(ok) is None
    True
    >>> gone = ok.model_copy(update={"status": "folder_missing"})
    >>> view_error(gone).code
    'project.folder_missing'
    >>> ro = ok.model_copy(update={"records_writable": False})
    >>> err = view_error(ro)
    >>> err.code, err.details["reason"]
    ('project.records_unavailable', 'readonly')
    """
    project = view.project
    open_fix = _fix(texts.open_label, texts.projects_role, project.id)
    if view.status != KnownProjectStatuses.READY:
        details = _dump(
            ProjectFolderUnavailableDetails(
                project_id=project.id, status=view.status, folder=project.folder
            )
        )
        if view.status == KnownProjectStatuses.MANIFEST_INVALID:
            return ErrorInfo(
                code=ErrorCodes.PROJECT_MANIFEST_INVALID,
                message=texts.manifest_invalid.format(project=project.id),
                details=details,
                fix=open_fix,
            )
        return ErrorInfo(
            code=ErrorCodes.PROJECT_FOLDER_MISSING,
            message=texts.folder_unavailable.format(project=project.id, status=view.status),
            details=details,
            fix=open_fix,
        )
    if not view.records_writable or not view.config_writable:
        issue = view.records_issue
        details = dict(issue.details) if issue is not None and issue.details else {}
        if not details.get("reason"):
            details = _dump(
                ProjectRecordsUnavailableDetails(
                    project_id=project.id, reason=KnownRecordsUnavailableReasons.READONLY
                )
            )
        details.setdefault("project_id", project.id)
        return ErrorInfo(
            code=ErrorCodes.PROJECT_RECORDS_UNAVAILABLE,
            message=texts.records_unavailable.format(
                project=project.id, reason=details.get("reason")
            ),
            details=details,
            fix=open_fix,
        )
    return None


def space_error(
    project_id: str,
    exc: Exception,
    *,
    folder: str | None = None,
    texts: PreflightTexts = DEFAULT_PREFLIGHT_TEXTS,
) -> ErrorInfo:
    """공간을 열다 난 예외 → 오류 본문. 예외의 ``code``가 매니페스트 오류면
    ``project.manifest_invalid``, 그 밖은 ``project.folder_missing``(상태 = 예외 이름)."""
    code = getattr(exc, "code", None)
    status = (
        KnownProjectStatuses.MANIFEST_INVALID
        if code == ErrorCodes.PROJECT_MANIFEST_INVALID
        else KnownProjectStatuses.FOLDER_MISSING
        if code == ErrorCodes.PROJECT_FOLDER_MISSING
        else KnownProjectStatuses.NO_ACCESS
    )
    details = _dump(
        ProjectFolderUnavailableDetails(project_id=project_id, status=status, folder=folder)
    )
    open_fix = _fix(texts.open_label, texts.projects_role, project_id)
    if status == KnownProjectStatuses.MANIFEST_INVALID:
        return ErrorInfo(
            code=ErrorCodes.PROJECT_MANIFEST_INVALID,
            message=texts.manifest_invalid.format(project=project_id),
            details=details,
            fix=open_fix,
        )
    return ErrorInfo(
        code=ErrorCodes.PROJECT_FOLDER_MISSING,
        message=texts.folder_unavailable.format(project=project_id, status=status),
        details=details,
        fix=open_fix,
    )


def not_imported_error(
    project_id: str,
    kind: str,
    item_id: str,
    *,
    in_library: bool,
    texts: PreflightTexts = DEFAULT_PREFLIGHT_TEXTS,
) -> ErrorInfo:
    """422 ``project.not_imported``(``ProjectNotImportedDetails``). 해결 버튼은 두지 않는다 — 웹이
    ``in_library``로 [가져와서 실행](계획 → 적용 → 실행)을 낸다(K33-18).

    >>> err = not_imported_error("app", "graph", "g1", in_library=True)
    >>> err.code, err.details
    ('project.not_imported', {'project_id': 'app', 'kind': 'graph', 'id': 'g1', 'in_library': True})
    """
    return ErrorInfo(
        code=ErrorCodes.PROJECT_NOT_IMPORTED,
        message=texts.not_imported.format(project=project_id, kind=kind, id=item_id),
        details=_dump(
            ProjectNotImportedDetails(
                project_id=project_id, kind=kind, id=item_id, in_library=in_library
            )
        ),
    )


def outside_folder_error(
    project_id: str,
    folder: str,
    paths: Sequence[OutsideFolderPath],
    texts: PreflightTexts = DEFAULT_PREFLIGHT_TEXTS,
) -> ErrorInfo:
    """422 ``project.outside_folder``.

    ``details`` = ``ProjectOutsideFolderDetails{project_id, folder, paths}``.
    """
    return ErrorInfo(
        code=ErrorCodes.PROJECT_OUTSIDE_FOLDER,
        message=texts.outside_folder.format(project=project_id, count=len(paths)),
        details=ProjectOutsideFolderDetails(
            project_id=project_id, folder=folder, paths=list(paths)
        ).model_dump(mode="json"),
    )


# ---------------------------------------------------------------- 경로 지킴(§PI.5)


def _layer_of(pointer: str, provenance: Mapping[str, str]) -> str | None:
    """값 위치를 정한 층 id(출처 표에서 가장 긴 앞부분이 맞는 항목)."""
    best: str | None = None
    best_len = -1
    for key, layer in provenance.items():
        if (pointer == key or pointer.startswith(key + "/")) and len(key) > best_len:
            best, best_len = layer, len(key)
    return best


NESTED_NODE_SEPARATOR = "/"
"""중첩 팀 안 노드 ``node_id``의 구분자: ``"<팀 노드>/<자식 노드>"``(대화 세션 경로 키 모양)."""

TeamFinder = Callable[[str, str | None], Graph | None]
"""팀 구성 id·고정 버전(None = 최신) → 팀 구성(노드 서비스 ``TEAM_LOOKUP`` 모양). 없으면 None 또는
``LookupError``."""


def _find_child(find_team: TeamFinder, ref: str, version: str | None) -> Graph | None:
    try:
        return find_team(ref, version)
    except Exception:  # 없음·읽기 실패 — 실행 시 중첩 팀 노드가 같은 코드로 실패한다
        return None


def outside_paths_of_graph(
    graph: Graph,
    *,
    catalog: TeamCatalog,
    folder: str,
    allowed: Iterable[str] = (),
    find_agent: Callable[[str], Agent | None] | None = None,
    workspace: WorkspaceSettings | None = None,
    scope_layers: Sequence[Layer] = (),
    placeholders: Mapping[str, str] | None = None,
    environ: Mapping[str, str] | None = None,
    find_team: TeamFinder | None = None,
    nested_separator: str = NESTED_NODE_SEPARATOR,
) -> list[OutsideFolderPath]:
    """에이전트 노드마다 **유효 설정**(층을 합친 값)의 ``x-path`` 값 중 ``folder``·``allowed`` 밖인
    것. 중첩 팀 노드가 있으면 그 자식 팀 구성(과 손자)의 에이전트 노드도 같은 규칙으로 본다.

    덮어써진 층 값은 보지 않는다(실제로 쓰이는 값만). 결과의 ``layer``는 그 값을 정한 층의 화면
    이름(``EffectiveSettings.provenance``), ``node_id``는 노드(중첩 팀 안이면
    ``"<팀 노드>/<자식 노드>"``). 에이전트 설정은 계약 스키마(``AgentSettings``),
    ``backend_options``는 유효 백엔드의 ``config_schema``(``catalog``의 디스크립터)로 본다 — 필드
    이름을 코드에 두지 않는다(K33-7). 해석할 수 없는 그래프면 빈 목록(엔진 검증이 맡는다).

    중첩 팀(5.7R.33g 잔여): 자식 Run은 부모 Run의 서비스(범위 층 = 프로젝트 층·공통 설정·정의
    출처)를 물려받으므로 같은 ``scope_layers``·``workspace``·``find_agent``로 본다. 자식 팀 구성의
    팀 층은 중첩 팀 노드 config의 덮어쓰기(``TeamConventions.node_settings_key``,
    ``with_team_settings``)를 적용한 값이다. 고정 버전(``TeamConventions.node_version_key``)은
    ``find_team(ref, version)``으로 그 버전을 읽는다. 이미 경로에 있는 팀 구성(순환)·읽을 수 없는
    자식·덮어쓰기가 틀린 자식은 건너뛴다(실행 시 엔진·노드가 막는다).

    Args:
        graph: 실행할 팀 구성.
        catalog: 노드·엣지·위임 방식·백엔드 디스크립터(``catalog_from_registries``).
        folder: 프로젝트 폴더(절대 경로). 상대 경로 값은 이 폴더 기준이다.
        allowed: 함께 허용하는 폴더(앱 workspace·상태 폴더).
        find_agent: 에이전트 id → 정의(Run의 정의 출처, 노드 서비스 ``AGENT_LOOKUP``).
        workspace: 공통 설정(노드 서비스 ``WORKSPACE_SETTINGS``).
        scope_layers: 공통 바로 아래 범위 층(노드 서비스 ``SCOPE_LAYERS``, 프로젝트 층 포함).
        placeholders: 값 안 틀 바꾸기(예: ``{"workspace": folder}``).
        environ: ``~`` 펼치기용 환경.
        find_team: 중첩 팀의 자식 팀 구성 읽기(노드 서비스 ``TEAM_LOOKUP``). None이면 루트 그래프의
            노드만 본다.
        nested_separator: 중첩 팀 안 노드 ``node_id``의 구분자.
    """
    out: list[OutsideFolderPath] = []
    allowed_dirs = tuple(allowed)
    schema = agent_settings_schema()
    schemas = {d.id: d.config_schema for d in catalog.backend_descriptors}
    env = dict(environ or {})

    def visit(current: Graph, prefix: str, lineage: tuple[str, ...]) -> None:
        plan = catalog.try_plan(current)
        if plan is None:
            return
        agents: dict[str, Agent] = {}
        if find_agent is not None:
            for ref in set(plan.agent_refs.values()):
                found = find_agent(ref)
                if found is not None:
                    agents[ref] = found
        for node_id in plan.agent_refs:
            out.extend(
                _node_paths(
                    plan,
                    node_id,
                    shown=prefix + node_id,
                    agents=agents,
                    catalog=catalog,
                    schema=schema,
                    schemas=schemas,
                    folder=folder,
                    allowed=allowed_dirs,
                    workspace=workspace,
                    scope_layers=scope_layers,
                    placeholders=placeholders,
                    env=env,
                )
            )
        if find_team is None:
            return
        settings_key = plan.conventions.node_settings_key
        nodes = {node.id: node for node in current.nodes}
        for node_id, ref in plan.team_refs.items():
            if ref in lineage:
                continue  # 순환 — 엔진이 자식 Run을 만들지 않는다
            child = _find_child(find_team, ref, plan.team_versions.get(node_id))
            if child is None or child.id in lineage:
                continue
            node = nodes.get(node_id)
            override = node.config.get(settings_key) if node is not None else None
            if isinstance(override, Mapping) and override:
                try:
                    child = with_team_settings(child, override)
                except Exception:  # 틀린 덮어쓰기 — 노드가 team.invalid_settings로 실패한다
                    continue
            visit(child, f"{prefix}{node_id}{nested_separator}", (*lineage, child.id))

    visit(graph, "", (graph.id,))
    return out


def _node_paths(
    plan: TeamPlan,
    node_id: str,
    *,
    shown: str,
    agents: Mapping[str, Agent],
    catalog: TeamCatalog,
    schema: Mapping[str, Any],
    schemas: Mapping[str, Any],
    folder: str,
    allowed: Sequence[str],
    workspace: WorkspaceSettings | None,
    scope_layers: Sequence[Layer],
    placeholders: Mapping[str, str] | None,
    env: Mapping[str, str],
) -> list[OutsideFolderPath]:
    """노드 하나의 유효 설정에서 폴더 밖 경로(``node_id`` = ``shown``, ``layer`` = 층 화면 이름)."""
    try:
        resolved = node_settings(
            plan,
            node_id,
            agents=agents,
            workspace=workspace,
            strategies=catalog.strategies,
            scope_layers=scope_layers,
        )
    except Exception:  # 층 계산 실패는 검사기(엔진·팀 규칙)가 알린다
        return []
    effective = resolved.effective
    labels = {layer.id: layer.label or layer.id for layer in effective.layers}
    value = effective.value.model_dump(mode="json", exclude_none=True)
    options = value.pop("backend_options", None)
    found_paths = outside_paths(
        value,
        schema,
        folder,
        allowed,
        placeholders=placeholders,
        environ=env,
        node_id=shown,
    )
    backend = effective.value.backend
    option_schema = schemas.get(backend) if backend else None
    if isinstance(options, Mapping) and option_schema:
        found_paths.extend(
            outside_paths(
                options,
                option_schema,
                folder,
                allowed,
                placeholders=placeholders,
                environ=env,
                node_id=shown,
                pointer_prefix="/backend_options",
            )
        )
    out: list[OutsideFolderPath] = []
    for path in found_paths:
        layer_id = _layer_of(path.pointer, effective.provenance)
        label = labels.get(layer_id, layer_id) if layer_id is not None else None
        out.append(path.model_copy(update={"layer": label}))
    return out
