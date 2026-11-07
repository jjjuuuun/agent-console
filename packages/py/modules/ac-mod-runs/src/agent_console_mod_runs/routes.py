"""REST 경로(접두 없음, 호스트가 ``/api/v1`` 아래 붙인다, design §5.2·§R14.4·§2R.10).

- 실행: ``POST/GET /runs``, ``GET /runs/{id}``, ``POST /runs/{id}/cancel``,
  ``GET /runs/{id}/events``(``node=`` 서버 거르기, 6R.12)
- 실행 목록 커서 페이지(6R.12, B-11·L-19): ``GET /runs/page``(``RunPage``). 옛 ``GET /runs``는
  그대로 두고 OpenAPI ``deprecated``. 프로젝트 기록 공간이 있는 조립에서 ``?project=``는 폴더 기록
  (``source=project``)을 끝까지 읽은 뒤 앱 DB 옛 기록(``source=app``)을 잇는다(Q14, 두 DB를 섞지
  않음). 커서 = ``<출처>.<저장소 커서>``(``agent_console_store.page_across_sources``).
- 상호작용: ``GET /runs/{id}/interactions``, ``POST /runs/{id}/interactions/{iid}/respond``,
  ``GET /interactions``
- 이어 가기: ``GET /runs/{id}/resume-options``, ``POST /runs/{id}/resume``
- 백엔드 준비 상태(ux-overhaul §15.8): ``GET /backends/status``·``GET /backends/{id}/status``·
  ``POST /backends/{id}/probe``(능력 없으면 409 ``backend.probe_unsupported``), 응답은
  ``Cache-Control: no-store``. 실행 기록·이벤트에 남기지 않는다.
- 백엔드 계정 로그인(ux-overhaul §15.9, F14): ``POST /backends/{id}/login``·
  ``GET /backends/login/current``·``GET /backends/login/{sid}``·
  ``POST /backends/login/{sid}/input``·``DELETE /backends/login/{sid}``·
  ``POST /backends/{id}/logout``. 응답은 ``no-store``,
  입력값은 응답·로그·오류에 나오지 않는다. 로그인 서비스가 꺼져 있으면(``backend_login.enabled``
  거짓) 이 경로가 없고 ``/backends``·``/backends/status``에서 로그인 능력·동작을 뺀다.
- 디스크립터: ``/node-types``(+ ``POST …/ports``)·``/edge-types``·``/backends``(+ ``/models``)·
  ``/delegation-strategies``·``/interaction-kinds``·``/condition-operators``
- 관측 탭 이벤트 접두어(5.5R.13): ``GET /observe-event-prefixes``(설치자 옵션
  ``observe_event_prefixes``, 기본 = 패키지 데이터 ``data/observe_event_prefixes.json``)
- 자식 Run(design §5R.7·§5R.11): ``GET /runs?root=<id>``(그 루트 아래 모든 자손),
  ``GET /runs/{id}``의 ``children``(직접 자식, 만든 순). 취소는 엔진이 자식에 전파한다.
- 에이전트 활동: ``GET /agents/{id}/activity``
- 프로젝트 기록 DB(5.7R.33y2, design §PI.4.6.3·.5·.7): Run 경로는 ``?project=<등록 id>``를 받는다.
  기록 공간 포트가 있으면 그 프로젝트 기록 DB에서 읽고(파일이 없으면 빈 목록), 없으면 호스트 DB에서
  ``project_id``로 거른다. 목록 ``?source=app`` = 그 ``project_id``를 가진 앱 DB 옛 기록(읽기 전용
  표시). ``POST /runs/{id}/mark-interrupted?project=`` = 끝나지 않은 Run을 끊긴 것으로(다른 앱의
  Run 포함).

라우트는 요청 파싱 → 서비스 호출 → 응답 변환만 한다. 흐름(``/runs/{id}/trace``)·넘김 집계
(``/runs/handoffs``)는 ``link-runs-trace``가 붙인다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from agent_console_contracts import (
    RECORD_SOURCES,
    AssignProjectRequest,
    AssignProjectResult,
    BackendDescriptor,
    BackendLoginInput,
    BackendLoginSession,
    BackendLoginStartRequest,
    BackendLogoutResult,
    BackendProbeRequest,
    BackendProbeResult,
    BackendReadiness,
    ConditionOperatorDescriptor,
    CreateRunRequest,
    DelegationStrategyDescriptor,
    EdgeTypeDescriptor,
    ErrorResponse,
    Interaction,
    InteractionKindDescriptor,
    InteractionStatus,
    ModelInfo,
    NodeTypeDescriptor,
    PortSpec,
    ProjectCounts,
    RecordsMoveRequest,
    RecordsMoveResult,
    RecordSource,
    ResolvePortsRequest,
    RespondInteractionRequest,
    ResumeOptions,
    ResumeRunRequest,
    Run,
    RunEvent,
    RunPage,
    RunSnapshot,
    RunStatus,
)
from agent_console_registry import UnknownExtensionError
from agent_console_runtime import BackendLoginService, BackendReadinessService, LoginInputError
from agent_console_store import (
    ProjectAssignStore,
    assign_project,
    count_projects,
    page_across_sources,
)

from .errors import (
    BackendNotFoundError,
    LoginPayloadTooLargeError,
    NodeTypeNotFoundError,
    PortConfigError,
    RunNotFoundError,
    RunQueryError,
    issues_from_errors,
)
from .interactions import InteractionService
from .login_gate import descriptor_without_login, readiness_without_login
from .move import RunMover
from .observe import DEFAULT_OBSERVE_EVENT_PREFIXES
from .service import RunService

DEFAULT_RUN_LIST_LIMIT = 200
DEFAULT_RUN_PAGE_LIMIT = 50
"""``GET /runs/page`` 기본 ``limit``."""
MAX_RUN_LIST_LIMIT = 1000
MAX_RUN_QUERY_LENGTH = 200
"""``GET /runs/page?q=`` 최대 글자 수(넘으면 422)."""
MAX_ACTIVITY_LIMIT = 1000

Limit = Annotated[int, Query(ge=1, le=MAX_RUN_LIST_LIMIT)]

SOURCE_PROJECT: RecordSource = "project"
SOURCE_APP: RecordSource = "app"
"""목록 ``?source=app``: 앱 DB 옛 기록(그 ``project_id``를 가진 행, 읽기 전용 표시)."""
RunSource = RecordSource
"""목록 출처(기본 ``project`` = 그 프로젝트 기록 DB, design §PI.4.6.8). 계약 ``RecordSource``."""


def parse_label_filters(values: Sequence[str] | None) -> dict[str, str]:
    """질의 ``label=<키>=<값>``(여러 번 = AND) → 사전. 첫 ``=``에서 나눈다(값에 ``=`` 가능).

    >>> parse_label_filters(["sdd.spec=pay", "sdd.task=2.1=b"])
    {'sdd.spec': 'pay', 'sdd.task': '2.1=b'}

    Raises:
        RunQueryError: ``=``이 없거나 키가 비었다. 같은 키에 다른 값을 두 번 주었다.
    """
    out: dict[str, str] = {}
    for raw in values or ():
        key, sep, value = raw.partition("=")
        if not sep or not key:
            raise RunQueryError("label은 '<키>=<값>' 모양이어야 합니다")
        if key in out and out[key] != value:
            raise RunQueryError("같은 label 키에 값이 둘입니다")
        out[key] = value
    return out


_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 413, 422, 500)
}


def errors(*extra: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses``: 공통 오류 + 추가 상태(모두 ``ErrorResponse``)."""
    return {**_ERRORS, **{s: {"model": ErrorResponse} for s in extra}}


def build_router(
    service: Callable[[], RunService],
    interactions: Callable[[], InteractionService],
    *,
    runs: Callable[[], Any],
    events: Callable[[], Any],
    activity_limit: int = 100,
    readiness: Callable[[], BackendReadinessService] | None = None,
    login: Callable[[], BackendLoginService] | None = None,
    observe_event_prefixes: Sequence[str] = DEFAULT_OBSERVE_EVENT_PREFIXES,
    projects: Callable[[], ProjectAssignStore] | None = None,
    mover: Callable[[], RunMover] | None = None,
) -> APIRouter:
    """실행 모듈 라우터.

    Args:
        service: 실행 서비스.
        interactions: 상호작용 서비스.
        runs: Run 조회(저장소 Run 리포지토리).
        events: 이벤트 조회(저장소 이벤트 리포지토리).
        activity_limit: 에이전트 활동 기본 개수.
        readiness: 백엔드 준비 상태·연결 테스트 서비스. None이면 그 세 경로를 붙이지 않는다.
        login: 백엔드 로그인 서비스. None이면 로그인·로그아웃 경로 6개를 붙이지 않는다.
        projects: 프로젝트 넣기·개수 포트(``project_id``를 가진 Run 저장소).
            None이면 두 경로를 붙이지 않는다.
        mover: 앱 DB 옛 기록 옮기기(``POST /runs/move-to-project``). None이면 경로를 붙이지 않는다.
        observe_event_prefixes: ``GET /observe-event-prefixes``가 내는 관측 탭 이벤트 type 접두어
            (기본 = 패키지 기본 데이터, 빈 목록 = 관측 탭 끔).
    """
    prefixes = list(observe_event_prefixes)
    router = APIRouter()

    def require_run(run_id: str, project: str | None = None) -> Run:
        found = service().current_run(run_id, project)
        if found is None:
            raise RunNotFoundError(run_id)
        return found

    # ------------------------------------------------------------ 실행

    @router.post("/runs", response_model=Run, status_code=202, responses=errors())
    async def create_run(body: CreateRunRequest) -> Run:
        """Run 시작(202). 그래프·준비자 검증 실패면 422 ``validation_failed``
        (``details.issues``). 그래프는 그 Run의 정의 출처(``project_id``가 있으면
        ``runs.scopes``의 ``run_definitions``)에서 읽는다."""
        handle = await service().start_graph(
            body.graph_id,
            body.input,
            version_hash=body.version_hash,
            origin=body.origin,
            project_id=body.project_id,
            labels=body.labels or None,
        )
        return handle.run

    @router.get("/runs", response_model=list[Run], responses=errors(), deprecated=True)
    async def list_runs(
        graph_id: str | None = None,
        conversation_id: str | None = None,
        agent_id: str | None = None,
        status: RunStatus | None = None,
        root: str | None = None,
        project: str | None = None,
        root_only: bool = False,
        source: RunSource = "project",
        limit: Limit = DEFAULT_RUN_LIST_LIMIT,
    ) -> list[Run]:
        """최신 생성순. 필터는 모두 AND. ``agent_id`` = 그 에이전트가 actor로 남긴 이벤트가 있는
        Run. ``root`` = 그 루트 Run 아래 모든 자식 Run(손자 포함, 루트 자신은 빠짐).
        ``project`` = 그 프로젝트의 Run만(기록 공간이 있으면 그 기록 DB, 없으면 ``project_id``로
        거름), ``source=app`` = 그 ``project_id``를 가진 앱 DB 옛 기록, ``root_only`` = 루트 Run만
        (``limit``은 이 조건을 건 뒤에 적용된다)."""
        filters: dict[str, Any] = {
            "graph_id": graph_id,
            "conversation_id": conversation_id,
            "agent": agent_id,
            "status": [status] if status is not None else None,
            "root_run_id": root,
            "root_only": root_only,
            "limit": limit,
        }
        svc = service()
        if source == SOURCE_APP or project is None or svc.records is None:
            host = svc.records.host.runs if svc.records is not None else runs()
            found: list[Run] = host.list(**filters, project_id=project)
            return found
        return list(svc.reader(project).list(**filters))

    @router.get("/runs/page", response_model=RunPage, responses=errors())
    async def page_runs(
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=MAX_RUN_LIST_LIMIT)] = DEFAULT_RUN_PAGE_LIMIT,
        project: str | None = None,
        root_only: bool = False,
        status: Annotated[list[RunStatus] | None, Query()] = None,
        graph_id: str | None = None,
        label: Annotated[list[str] | None, Query()] = None,
        source: RecordSource = "project",
        agent_id: str | None = None,
        conversation_id: str | None = None,
        root: str | None = None,
        since: float | None = None,
        q: Annotated[str | None, Query(max_length=MAX_RUN_QUERY_LENGTH)] = None,
    ) -> RunPage:
        """실행 목록 커서 페이지(``created_at`` 내림차순 + ``id``). 조건은 모두 AND.

        - ``cursor`` = 이전 응답의 ``next_cursor``(불투명, 모양이 틀리면 400 ``bad_request``).
          커서에 출처가 들어 있어 ``source``보다 우선한다.
        - ``status``·``label=<키>=<값>``은 여러 번 줄 수 있다(상태는 OR, 라벨은 AND, 라벨은 루트
          Run에만 있다).
        - ``agent_id``·``conversation_id``·``root``는 옛 ``GET /runs``와 같은 뜻이다(6R.19):
          ``agent_id`` = 그 에이전트가 actor로 남긴 이벤트가 있는 Run, ``root`` = 그 루트 Run 아래
          모든 자손(루트 자신은 빠짐).
        - ``since`` = ``created_at``이 그 값(epoch 초) 이상인 Run(하한 포함).
        - ``q`` = 부분 일치 검색(앞뒤 공백 제거, 비면 무시, 최대 ``MAX_RUN_QUERY_LENGTH``자):
          run id·``graph_id``·입력 최상위 문자열 값. ASCII 대소문자 무시, ``%``·``_``는 글자
          그대로. 팀 구성 이름·대화 제목은 찾지 않는다(다른 기능·DB의 값이라 클라이언트가 맡는다,
          6R.19 결정).
        - 행마다 ``has_children``(직접 자식 Run 유무)를 채운다(페이지 행을 한 번에 센다).
        - ``project`` = 그 프로젝트의 Run. 기록 공간이 있는 조립이면 폴더 기록 DB를 끝까지 읽은 뒤
          ``next_cursor``가 앱 DB 옛 기록(``source=app``)의 처음을 가리킨다(옛 기록이 없으면 null).
          한 페이지는 한 출처에서만 나오고 응답 ``source``가 그 출처다. ``source=app``으로 바로 옛
          기록만 읽을 수도 있다. 공간이 없는 조립(기능 단독)은 호스트 DB 하나를 ``project_id``로
          거르고 잇지 않는다.
        """
        filters: dict[str, Any] = {
            "limit": limit,
            "root_only": root_only,
            "status": status or None,
            "graph_id": graph_id,
            "labels": parse_label_filters(label) or None,
            "agent": agent_id,
            "conversation_id": conversation_id,
            "root_run_id": root,
            "since": since,
            "query": q,
        }
        svc = service()
        spaced = project is not None and svc.records is not None and svc.records.spaced

        def host_page(inner: str | None, size: int) -> tuple[list[Run], str | None]:
            host = svc.records.host.runs if svc.records is not None else runs()
            found: tuple[list[Run], str | None] = host.page(
                **{**filters, "limit": size}, cursor=inner, project_id=project
            )
            return found

        def read(src: str, inner: str | None) -> tuple[list[Run], str | None]:
            if src == SOURCE_APP or not spaced:
                return host_page(inner, limit)
            found: tuple[list[Run], str | None] = svc.reader(project).page(**filters, cursor=inner)
            return found

        def has_any(src: str) -> bool:
            return src == SOURCE_APP and bool(host_page(None, 1)[0])

        order = RECORD_SOURCES if spaced else (source,)
        page = page_across_sources(cursor, source, order=order, read=read, has_any=has_any)
        return RunPage.model_validate(
            {"items": page.items, "next_cursor": page.next_cursor, "source": page.source}
        )

    if projects is not None:
        # 고정 경로는 ``/runs/{run_id}``보다 먼저 등록한다.
        @router.get("/runs/project-counts", response_model=ProjectCounts, responses=errors())
        async def run_project_counts() -> ProjectCounts:
            """``project_id``별 루트 Run 수(자식 제외, 프로젝트 없음 = ``no_project``)."""
            return count_projects(projects())

        @router.post("/runs/assign-project", response_model=AssignProjectResult, responses=errors())
        async def assign_run_project(body: AssignProjectRequest) -> AssignProjectResult:
            """Run을 프로젝트에 넣는다. 루트 Run이면 자식도 함께. ``ids``는 지금 프로젝트와 상관없이
            옮기고 ``from_null``은 프로젝트 없는 Run만 넣는다.
            실행 중인 트리는 ``busy``로 건너뛴다."""
            return assign_project(projects(), body)

    if mover is not None:

        @router.post(
            "/runs/move-to-project", response_model=RecordsMoveResult, responses=errors(409)
        )
        async def move_runs_to_project(body: RecordsMoveRequest) -> RecordsMoveResult:
            """앱 DB의 Run 기록을 그 프로젝트 기록 DB로 옮긴다(루트 Run + 자손·노드·이벤트·
            상호작용).
            대상에 같은 id가 있으면 ``skipped``, 실행 중인 묶음은 ``failed``(``run.move_busy``).
            복사 -> 개수·값 확인 -> 원본 삭제(``remove_source``) 순서이고 실패하면 대상을 되돌린다.
            기록 DB를 쓸 수 없으면 409 ``project.records_unavailable``, 모르는 프로젝트는 404."""
            return await run_in_threadpool(mover().move, body)

    @router.get("/runs/{run_id}", response_model=RunSnapshot, responses=errors())
    async def get_run(run_id: str, project: str | None = None) -> RunSnapshot:
        """Run·NodeRun·마지막 이벤트 seq와 직접 자식 Run(``children``, 만든 순 — 중첩 팀).
        ``project`` = 그 프로젝트 기록 DB에서(없으면 호스트 DB)."""
        if project is not None and service().records is not None:
            reader = service().reader(project)
            found = reader.get(run_id)
            if found is None:
                raise RunNotFoundError(run_id)
            kids: list[Run] = reader.list(parent_run_id=run_id)
            kids.sort(key=lambda child: (child.created_at, child.id))
            return RunSnapshot(
                run=found,
                node_runs=reader.list_node_runs(run_id),
                last_seq=reader.last_seq(run_id),
                children=kids,
            )
        run = runs().get(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        children: list[Run] = runs().list(parent_run_id=run_id)
        children.sort(key=lambda child: (child.created_at, child.id))
        return RunSnapshot(
            run=run,
            node_runs=runs().list_node_runs(run_id),
            last_seq=events().last_seq(run_id),
            children=children,
        )

    @router.post("/runs/{run_id}/mark-interrupted", response_model=Run, responses=errors(409))
    async def mark_interrupted(run_id: str, project: str | None = None) -> Run:
        """끝나지 않은 Run을 끊긴 것으로 표시한다(``interrupted``, 대기 요청 닫음). 다른 앱
        (``Run.host_id``가 다름)이 남긴 Run도 사용자가 누를 때만 바꾼다(K33-30). 이 앱에서 돌고
        있으면 끊는다. 이미 끝났으면 그대로(멱등). 기록 DB를 쓸 수 없으면 409
        ``project.records_unavailable``. 없으면 404."""
        found = service().mark_interrupted(run_id, project)
        if found is None:
            raise RunNotFoundError(run_id)
        return found

    @router.post("/runs/{run_id}/cancel", response_model=Run, responses=errors())
    async def cancel_run(run_id: str, project: str | None = None) -> Run:
        """취소 요청. 이미 끝난 Run은 그대로 돌려준다(멱등). 진행 중인 자식 Run도 함께 멈춘다
        (엔진이 전파). 자식 Run을 직접 취소하면 그 자식만 멈추고 부른 노드가 결과를 받는다."""
        handle = service().runtime.get(run_id)
        if handle is not None:
            handle.cancel("cancelled via api")
            return handle.run
        return require_run(run_id, project)

    @router.get("/runs/{run_id}/events", response_model=list[RunEvent], responses=errors())
    async def run_events(
        run_id: str,
        actor: str | None = None,
        type_prefix: str | None = None,
        since_seq: Annotated[int, Query(ge=0)] = 0,
        project: str | None = None,
        node: str | None = None,
    ) -> list[RunEvent]:
        """이 실행의 이벤트(seq 순). ``actor``(에이전트별 로그)·``type_prefix``(예: ``hook.``)·
        ``node``(``node_path``에 그 노드 id가 있는 이벤트 — 하위 그래프 안 이벤트 포함, 6R.12)."""
        require_run(run_id, project)
        query: dict[str, Any] = {"since_seq": since_seq, "actor": actor, "type_prefix": type_prefix}
        if node is not None:
            query["node"] = node
        if project is not None and service().records is not None:
            return list(service().reader(project).events(run_id, **query))
        found: list[RunEvent] = events().list(run_id, **query)
        return found

    # ------------------------------------------------------------ 상호작용

    @router.get("/runs/{run_id}/interactions", response_model=list[Interaction], responses=errors())
    async def run_interactions(run_id: str, project: str | None = None) -> list[Interaction]:
        """이 실행의 상호작용(대기·닫힘 모두, 오래된 순)."""
        require_run(run_id, project)
        if project is not None and service().records is not None:
            return list(service().reader(project).interactions(run_id=run_id))
        return interactions().list(run_id=run_id)

    @router.post(
        "/runs/{run_id}/interactions/{interaction_id}/respond",
        response_model=Interaction,
        responses=errors(409),
    )
    async def respond(
        run_id: str, interaction_id: str, body: RespondInteractionRequest
    ) -> Interaction:
        """응답(토큰 필요). 없음 404, 이미 닫힘 409 ``interaction_closed``(``details.interaction``),
        응답 형식 오류 422 ``validation_failed``. 동시에 답하면 하나만 성공한다."""
        return await interactions().respond(run_id, interaction_id, body.response)

    @router.get("/interactions", response_model=list[Interaction], responses=errors())
    async def list_interactions(
        status: InteractionStatus | None = None,
        conversation_id: str | None = None,
        root: str | None = None,
        project: str | None = None,
        limit: Limit = DEFAULT_RUN_LIST_LIMIT,
    ) -> list[Interaction]:
        """상호작용 목록, 최신순. ``status=pending``이면 대기 목록. ``root`` = 그 Run과 아래 모든
        자식 Run의 상호작용(루트 기준, 중첩 팀 안의 요청 포함). ``project`` = 그 프로젝트 기록
        DB에서(없으면 호스트 DB)."""
        if project is not None and service().records is not None:
            found = (
                service()
                .reader(project)
                .interactions(status=status, conversation_id=conversation_id, root_run_id=root)
            )
        else:
            found = interactions().list(
                status=status, conversation_id=conversation_id, root_run_id=root
            )
        return list(reversed(found))[:limit]

    # ------------------------------------------------------------ 이어 가기

    @router.get("/runs/{run_id}/resume-options", response_model=ResumeOptions, responses=errors())
    async def resume_options(run_id: str, project: str | None = None) -> ResumeOptions:
        """끊긴 노드 목록과 노드 타입 디스크립터의 ``rerunnable``, 끊기기 직전 상태(``status``).

        끊긴(``interrupted``) Run이 아니거나 이미 이어 간 Run이면 ``nodes``가 비어 있다. 없으면 404.
        """
        return service().resume_for(project).options(run_id)

    @router.post(
        "/runs/{run_id}/resume", response_model=Run, status_code=202, responses=errors(409)
    )
    async def resume_run(run_id: str, body: ResumeRunRequest, project: str | None = None) -> Run:
        """고른 노드를 저장된 입력으로 다시 실행하는 **새 Run**(202, ``origin = resume``,
        ``resumed_from``). 대화 턴이면 이어 가기 처리기(``runs.resume_handlers``)가 같은 대화의 새
        턴으로 시작한다.

        끊긴 노드가 아니거나 ``rerunnable``이 아닌 노드: 422 ``validation_failed``. 끊긴 Run이 아님·
        이미 이어 감·당시 팀 구성 없음·대화의 마지막 턴이 아님: 409 ``run_not_resumable``. 대화에
        실행 중인 턴: 409 ``conversation_busy``. 없음 404.
        """
        return await service().resume_for(project).resume(run_id, body.node_ids)

    # ------------------------------------------------------------ 디스크립터

    @router.get("/node-types", response_model=list[NodeTypeDescriptor], responses=errors())
    async def list_node_types() -> list[NodeTypeDescriptor]:
        return service().node_types()

    @router.post("/node-types/{type_id}/ports", response_model=PortSpec, responses=errors())
    async def resolve_ports(type_id: str, body: ResolvePortsRequest) -> PortSpec:
        try:
            node_type = service().registries.node_types.get(type_id)
        except UnknownExtensionError:
            raise NodeTypeNotFoundError(type_id) from None
        try:
            return node_type.resolve_ports(body.config)
        except ValidationError as exc:
            issues = issues_from_errors(exc.errors(include_input=False, include_url=False))
            raise PortConfigError(issues) from None
        except (ValueError, TypeError, KeyError) as exc:
            raise PortConfigError(error=exc.__class__.__name__) from None

    @router.get("/edge-types", response_model=list[EdgeTypeDescriptor], responses=errors())
    async def list_edge_types() -> list[EdgeTypeDescriptor]:
        return service().edge_types()

    @router.get("/backends", response_model=list[BackendDescriptor], responses=errors())
    async def list_backends() -> list[BackendDescriptor]:
        """등록된 실행 백엔드 디스크립터. 로그인 서비스가 꺼져 있으면 로그인 능력·방법을 뺀다."""
        found = service().backends()
        return found if login is not None else [descriptor_without_login(d) for d in found]

    if readiness is not None:
        _backend_readiness_routes(router, readiness, login_enabled=login is not None)

    @router.get("/backends/{backend_id}/models", response_model=list[ModelInfo], responses=errors())
    async def list_models(backend_id: str) -> list[ModelInfo]:
        try:
            backend = service().registries.backends.get(backend_id)
        except UnknownExtensionError:
            raise BackendNotFoundError(backend_id) from None
        return await backend.list_models()

    @router.get(
        "/delegation-strategies",
        response_model=list[DelegationStrategyDescriptor],
        responses=errors(),
    )
    async def list_strategies() -> list[DelegationStrategyDescriptor]:
        return service().strategies()

    @router.get(
        "/interaction-kinds", response_model=list[InteractionKindDescriptor], responses=errors()
    )
    async def list_interaction_kinds() -> list[InteractionKindDescriptor]:
        """상호작용 종류(X15) 디스크립터. 모듈은 종류 이름을 모른다."""
        return service().interaction_kinds()

    @router.get(
        "/condition-operators",
        response_model=list[ConditionOperatorDescriptor],
        responses=errors(),
    )
    async def list_condition_operators() -> list[ConditionOperatorDescriptor]:
        """조건 연산자(X22) 디스크립터(id 순). 조건 편집 화면이 연산자 목록으로 쓴다."""
        return service().condition_operators()

    # ------------------------------------------------------------ 에이전트 활동

    @router.get("/observe-event-prefixes", response_model=list[str], responses=errors())
    async def list_observe_event_prefixes() -> list[str]:
        """실행 상세 [관측] 탭이 모을 실행 이벤트 type 접두어(설치자 옵션
        ``observe_event_prefixes``, 빈 목록 = 관측 탭 끔)."""
        return list(prefixes)

    @router.get("/agents/{agent_id}/activity", response_model=list[RunEvent], responses=errors())
    async def agent_activity(
        agent_id: str,
        limit: Annotated[int, Query(ge=1, le=MAX_ACTIVITY_LIMIT)] = activity_limit,
    ) -> list[RunEvent]:
        """이 에이전트(actor)가 낸 최근 이벤트, 실행을 가로질러 최신순
        (묶음은 화면이 ``run_id``로)."""
        found: list[RunEvent] = events().list_by_actor(agent_id, limit=limit)
        return found

    if login is not None:  # /backends/{id}/… 뒤에 붙인다(경로 겹침 없음)
        _backend_login_routes(router, login)

    return router


NO_STORE = "no-store"
"""준비 상태·연결 테스트 응답의 ``Cache-Control``(매번 새로 본다)."""


def _backend_readiness_routes(
    router: APIRouter,
    readiness: Callable[[], BackendReadinessService],
    *,
    login_enabled: bool = True,
) -> None:
    """``/backends/status``·``/backends/{id}/status``·``POST /backends/{id}/probe``.

    ``login_enabled``가 거짓이면(로그인 경로 없음) 상태의 ``login``·``logout`` 동작을 뺀다.
    """

    def gate(found: BackendReadiness) -> BackendReadiness:
        return found if login_enabled else readiness_without_login(found)

    @router.get(
        "/backends/status",
        response_model=list[BackendReadiness],
        responses=errors(),
        summary="모든 실행 백엔드의 준비 상태",
    )
    async def list_backend_status(response: Response) -> list[BackendReadiness]:
        """등록된 모든 실행 백엔드의 정적 점검(인증·설정 확인). 모델·네트워크를 부르지 않는다.

        점검을 지원하지 않는 백엔드(`capabilities.status=false`)는 `state: unknown`이다.
        응답에 비밀 값은 없다(있음/없음과 출처 이름만, 글자 필드는 가림을 거친다).
        """
        response.headers["Cache-Control"] = NO_STORE
        return [gate(item) for item in await readiness().status_all()]

    @router.get(
        "/backends/{backend_id}/status",
        response_model=BackendReadiness,
        responses=errors(),
        summary="실행 백엔드 하나의 준비 상태",
    )
    async def get_backend_status(backend_id: str, response: Response) -> BackendReadiness:
        """정적 점검(모델·네트워크 호출 없음). 지원하지 않으면 404가 아니라 `state: unknown`.

        등록되지 않은 id는 404 `not_found`.
        """
        response.headers["Cache-Control"] = NO_STORE
        return gate(await readiness().status(backend_id))

    @router.post(
        "/backends/{backend_id}/probe",
        response_model=BackendProbeResult,
        responses=errors(409),
        summary="실행 백엔드 연결 테스트(실제 호출 한 번)",
    )
    async def probe_backend(
        backend_id: str, response: Response, body: BackendProbeRequest | None = None
    ) -> BackendProbeResult:
        """가장 짧은 실제 호출 한 번으로 연결을 확인한다(모델 비용이 조금 들 수 있다).

        - 백엔드가 지원하지 않으면(`capabilities.probe=false`) 409 `backend.probe_unsupported`
          (`details.backend`).
        - 같은 백엔드에 진행 중인 테스트가 있으면 새로 부르지 않고 그 결과를 함께 받는다.
        - `timeout_s`는 서버 상한(`mod-runs.backend_probe_timeout_max_s`, 기본 20초)으로 잘린다.
          시간을 넘기면 `ok: false, reason: timeout`.
        - 결과는 실행 기록·이벤트에 남지 않고 서버가 기억하지 않는다. 서버 로그에는 백엔드 id·
          ok·reason·소요 시간만 남는다.
        """
        response.headers["Cache-Control"] = NO_STORE
        timeout = body.timeout_s if body is not None else None
        return await readiness().probe(backend_id, timeout)


LOGIN_INPUT_MAX_BYTES = 4096
"""``POST /backends/login/{sid}/input`` 본문 최대 바이트."""

_LOGIN_INPUT_SCHEMA = BackendLoginInput.model_json_schema()


def _backend_login_routes(router: APIRouter, login: Callable[[], BackendLoginService]) -> None:
    """백엔드 계정 로그인·로그아웃 경로 6개(ux-overhaul §15.9)."""

    @router.post(
        "/backends/{backend_id}/login",
        response_model=BackendLoginSession,
        status_code=201,
        responses=errors(409),
        summary="실행 백엔드 계정 로그인 시작",
    )
    async def start_backend_login(
        backend_id: str, response: Response, body: BackendLoginStartRequest | None = None
    ) -> BackendLoginSession:
        """로그인 과정을 시작하고 세션을 돌려준다(서버 전체에서 진행 중인 세션은 하나).

        - 실행 명령·인자는 서버 설정에서만 온다(요청으로 바꿀 수 없다).
        - 지원하지 않으면(`capabilities.login=false`, 모르는 `method_id`) 409
          `backend.login_unsupported`.
        - 다른 세션이 진행 중이면 409 `backend.login_busy`(`details.session_id`).
        - 백엔드가 거절하면 그 코드(예: 409 `backend.subscription_auth_disabled`).
        - 시작 중 오류는 `phase: failed`, `reason: start_failed` 세션(201)으로 돌려준다.
        - `timeout_s`는 서버 상한(`mod-runs.backend_login.timeout_max_s`)으로 잘린다.
        """
        response.headers["Cache-Control"] = NO_STORE
        method = body.method_id if body is not None else None
        timeout = body.timeout_s if body is not None else None
        return await login().start(backend_id, method, timeout)

    @router.get(
        "/backends/login/current",
        response_model=BackendLoginSession,
        responses={**errors(), 204: {"description": "진행 중인 로그인이 없다"}},
        summary="진행 중인 로그인 세션",
    )
    async def current_backend_login(response: Response) -> Any:
        """진행 중인 로그인 세션. 없으면 204. 조회는 하트비트로 친다."""
        found = login().current()
        if found is None:
            return Response(status_code=204, headers={"Cache-Control": NO_STORE})
        response.headers["Cache-Control"] = NO_STORE
        return found

    @router.get(
        "/backends/login/{session_id}",
        response_model=BackendLoginSession,
        responses=errors(),
        summary="로그인 세션 상태(폴링)",
    )
    async def get_backend_login(session_id: str, response: Response) -> BackendLoginSession:
        """세션 상태. 화면은 1초마다 부른다(하트비트). `heartbeat_s` 넘게 부르지 않으면 서버가
        취소한다. 끝난 세션은 `retain_s` 동안만 보이고 그 뒤 404 `backend.login_session_not_found`.
        """
        response.headers["Cache-Control"] = NO_STORE
        return login().get(session_id)

    @router.post(
        "/backends/login/{session_id}/input",
        status_code=202,
        responses=errors(409),
        summary="로그인 세션에 글자·키 보내기",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": _LOGIN_INPUT_SCHEMA}},
            }
        },
    )
    async def send_backend_login_input(session_id: str, request: Request) -> Response:
        """붙여 넣은 코드(`text`) 또는 키(`key`) 하나를 보낸다(202, 본문 없음). 본문은
        `BackendLoginInput`.

        - 본문은 4KB 이하(넘으면 413). 글자는 앞뒤 공백을 자르고 인쇄 가능 문자만 받는다.
        - 키는 세션의 `accepts_keys` 안만. 형식이 틀리거나 받을 수 없으면 422 `validation_failed`
          (`details.reason`). 오류 본문에 보낸 값은 들어가지 않는다(서버가 본문을 직접 검사한다).
        - 보낸 값은 응답·서버 로그·오류에 나오지 않고 세션 응답에서 가려진다.
        """
        raw = await request.body()
        if len(raw) > LOGIN_INPUT_MAX_BYTES:
            raise LoginPayloadTooLargeError(LOGIN_INPUT_MAX_BYTES)
        try:
            body = BackendLoginInput.model_validate_json(raw or b"{}")
        except ValidationError:  # 기본 검증 오류는 입력값을 되돌려 보내므로 쓰지 않는다
            raise LoginInputError(LoginInputError.TEXT_INVALID) from None
        await login().send_input(session_id, text=body.text, key=body.key)
        return Response(status_code=202, headers={"Cache-Control": NO_STORE})

    @router.delete(
        "/backends/login/{session_id}",
        response_model=BackendLoginSession,
        responses=errors(),
        summary="로그인 취소",
    )
    async def cancel_backend_login(session_id: str, response: Response) -> BackendLoginSession:
        """진행 중이면 하위 과정을 멈추고 `phase: cancelled`. 끝난 세션은 그대로 돌려준다.
        로그인 정보는 바뀌지 않는다."""
        response.headers["Cache-Control"] = NO_STORE
        return await login().cancel(session_id)

    @router.post(
        "/backends/{backend_id}/logout",
        response_model=BackendLogoutResult,
        responses=errors(409),
        summary="실행 백엔드 계정 로그아웃(연결 해제)",
    )
    async def logout_backend(backend_id: str, response: Response) -> BackendLogoutResult:
        """이 PC의 백엔드 로그인을 지운다(확인 창은 화면 몫).

        - 지원하지 않으면(`capabilities.logout=false`) 409 `backend.logout_unsupported`.
        - 같은 백엔드의 로그인이 진행 중이면 409 `backend.login_busy`.
        - 실패는 `ok: false` + `reason`. 실행 기록·이벤트에 남지 않는다.
        """
        response.headers["Cache-Control"] = NO_STORE
        return await login().logout(backend_id)


__all__ = [
    "DEFAULT_RUN_LIST_LIMIT",
    "DEFAULT_RUN_PAGE_LIMIT",
    "LOGIN_INPUT_MAX_BYTES",
    "MAX_RUN_LIST_LIMIT",
    "MAX_RUN_QUERY_LENGTH",
    "NO_STORE",
    "build_router",
    "errors",
    "parse_label_filters",
]
