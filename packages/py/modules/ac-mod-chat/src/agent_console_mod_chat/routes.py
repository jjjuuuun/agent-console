"""REST 경로(접두 없음, 호스트가 ``/api/v1`` 아래 붙인다, design §R5.1·§2R.10).

- 대화 목록 커서 페이지(6R.12, L-19): ``GET /conversations/page``(``ConversationPage``).
  옛 ``GET /conversations``는 그대로 두고 OpenAPI ``deprecated``. 기록 공간이 있는 조립의
  ``?project=``는 폴더 기록(``source=project``)을 끝까지 읽은 뒤 앱 DB 옛 기록(``source=app``)을
  잇는다(Q14).
- 대화 위치(요청 11/07 후속): ``GET /conversations/{id}/locate`` → ``ConversationLocation``
  (그 대화가 있는 기록 공간, null = 앱 기록). 서비스에 선택 메서드 ``locate``가 있으면 그것(등록
  프로젝트 기록 DB를 읽기만 한다), 없으면 호스트 대화가 있을 때 null. 대화 본문은 주지 않는다 -
  웹은 이 값을 ``?project=``로 붙여 대화 단위 경로를 부른다(``?project=`` 없는 상세가 다른 공간을
  대신 읽지 않는다).
- 대화: ``GET/POST /conversations``, ``GET/PATCH/DELETE /conversations/{id}``,
  ``GET /conversations/{id}/turns``, ``POST /conversations/{id}/messages``,
  ``GET /conversations/{id}/sessions``(세션 이어 가기 상태, 5.7R.33y3)
- 대기열: ``GET /conversations/{id}/queue``, ``DELETE …/queue/{queued_id}``,
  ``POST …/queue/{queued_id}/release``

프로젝트 기록 DB(5.7R.33y2): 모든 대화 경로는 ``?project=<등록 id>``를 받는다. 서비스에 선택
메서드 ``for_project``가 있으면(기록 공간 포트가 있는 조립) 그 프로젝트 기록 DB의 대화 서비스를
쓰고, 없으면 호스트 DB에서 ``project_id``로 거른다. 목록 ``?source=app`` = 그 ``project_id``를 가진
앱 DB 옛 기록(읽기 전용 표시).

라우트는 요청 파싱 → ``ChatService`` 호출 → 응답 변환만 한다. 대기열(``chat.busy_policy = queue``)은
저장소에 남고, 서버를 다시 시작하면 ``chat.queue_after_restart``대로 처리한다(턴 실행기를 주는
연동 모듈이 시작할 때).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from fastapi.concurrency import run_in_threadpool

from agent_console_chat import ChatService
from agent_console_contracts import (
    RECORD_SOURCES,
    AssignProjectRequest,
    AssignProjectResult,
    ChatTurn,
    Conversation,
    ConversationLocation,
    ConversationPage,
    ConversationSessions,
    ConversationSummary,
    CreateConversationRequest,
    ErrorResponse,
    PostMessageRequest,
    ProjectCounts,
    QueuedMessage,
    RecordsMoveRequest,
    RecordsMoveResult,
    RecordSource,
    Run,
    UpdateConversationRequest,
)
from agent_console_store import (
    ProjectAssignStore,
    assign_project,
    count_projects,
    decode_cursor,
    encode_cursor,
    page_across_sources,
)

from .move import ConversationMover

MAX_TURN_LIMIT = 500
DEFAULT_CONVERSATION_PAGE_LIMIT = 50
MAX_CONVERSATION_PAGE_LIMIT = 1000
MAX_CONVERSATION_QUERY_LENGTH = 200
"""``GET /conversations/page?q=`` 최대 글자 수(넘으면 422)."""

SOURCE_APP: RecordSource = "app"
"""목록 ``?source=app``: 앱 DB 옛 기록(그 ``project_id``를 가진 대화, 읽기 전용 표시)."""
ConversationSource = RecordSource

_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 413, 422, 500)
}


def errors(*extra: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses``: 공통 오류 + 추가 상태(모두 ``ErrorResponse``)."""
    return {**_ERRORS, **{s: {"model": ErrorResponse} for s in extra}}


def build_router(
    service: Callable[[], ChatService],
    *,
    require_graphs: Callable[[], None] = lambda: None,
    projects: Callable[[], ProjectAssignStore] | None = None,
    mover: Callable[[], ConversationMover] | None = None,
) -> APIRouter:
    """대화·대기열 라우터.

    Args:
        service: 대화 서비스를 돌려주는 함수(요청마다 부른다).
        require_graphs: 팀 구성을 읽어야 하는 요청(만들기·팀 구성 바꾸기) 전에 부른다. 팀 구성
            조회를 쓸 수 없으면 예외(예: ``feature_unavailable``)를 던진다.
        projects: 프로젝트 넣기·개수 포트(``project_id`` 열을 가진 저장소).
            없으면 두 경로를 만들지 않는다.
        mover: 앱 DB 옛 대화 옮기기(``POST /conversations/move-to-project``).
            없으면 경로를 만들지 않는다.
    """
    router = APIRouter()

    async def chat(project: str | None) -> ChatService:
        """요청의 대화 서비스: 프로젝트 기록 공간이 있으면 그 공간의 서비스.

        선택 메서드 ``for_project_ready``가 있으면 그것을 기다린다(재시작 정책 적용이 끝난 뒤의
        서비스 - 재시작 직후 첫 대기열 읽기도 정책이 적용된 상태).
        """
        host = service()
        if project is None:
            return host
        ready = getattr(host, "for_project_ready", None)
        if callable(ready):
            awaited: ChatService = await ready(project)
            return awaited
        method = getattr(host, "for_project", None)
        if not callable(method):
            return host
        found: ChatService = method(project)
        return found

    @router.get(
        "/conversations",
        response_model=list[ConversationSummary],
        responses=errors(),
        deprecated=True,
    )
    async def list_conversations(
        graph_id: str | None = None,
        archived: bool | None = None,
        project: str | None = None,
        source: ConversationSource = "project",
    ) -> list[ConversationSummary]:
        """대화 요약(최근 갱신순): 마지막 턴 상태·대기열 수·대기 중 상호작용 수.
        ``project`` = 그 프로젝트의 대화만(기록 공간이 있으면 그 기록 DB, 생략 = 모두),
        ``source=app`` = 그 ``project_id``를 가진 앱 DB 옛 기록."""
        target = service() if source == SOURCE_APP else await chat(project)
        return target.list(graph_id=graph_id, archived=archived, project_id=project)

    @router.get("/conversations/page", response_model=ConversationPage, responses=errors())
    async def page_conversations(
        cursor: str | None = None,
        limit: Annotated[
            int, Query(ge=1, le=MAX_CONVERSATION_PAGE_LIMIT)
        ] = DEFAULT_CONVERSATION_PAGE_LIMIT,
        graph_id: str | None = None,
        archived: bool | None = None,
        project: str | None = None,
        source: RecordSource = "project",
        q: Annotated[str | None, Query(max_length=MAX_CONVERSATION_QUERY_LENGTH)] = None,
    ) -> ConversationPage:
        """대화 요약 커서 페이지(``updated_at`` 내림차순 + ``id``).

        ``cursor`` = 이전 응답의 ``next_cursor``(불투명, 틀리면 400 ``bad_request``, 커서의 출처가
        ``source``보다 우선). ``project`` = 그 프로젝트의 대화(서버가 거름). 기록 공간이 있는
        조립이면 폴더 기록을 끝까지 읽은 뒤 ``next_cursor``가 앱 DB 옛 기록(``source=app``)의
        처음을 가리킨다(없으면 null). 한 페이지는 한 출처에서만 나온다.
        ``q`` = 제목 부분 일치(앞뒤 공백 제거·대소문자 무시, 비면 무시, 최대
        ``MAX_CONVERSATION_QUERY_LENGTH``자, 넘으면 422). 두 출처 모두에 같은 조건이 걸린다.
        """
        host = service()
        scoped = await chat(project)
        spaced = project is not None and scoped is not host

        def read_with(
            target: ChatService, inner: str | None, size: int
        ) -> tuple[list[ConversationSummary], str | None]:
            after = None if inner is None else decode_cursor(inner)
            items, last = target.page(
                after=after,
                limit=size,
                graph_id=graph_id,
                archived=archived,
                project_id=project,
                query=q,
            )
            return items, (None if last is None else encode_cursor(*last))

        def read(src: str, inner: str | None) -> tuple[list[ConversationSummary], str | None]:
            return read_with(host if src == SOURCE_APP else scoped, inner, limit)

        def has_any(src: str) -> bool:
            return src == SOURCE_APP and bool(read_with(host, None, 1)[0])

        order = RECORD_SOURCES if spaced else (source,)
        page = page_across_sources(cursor, source, order=order, read=read, has_any=has_any)
        return ConversationPage.model_validate(
            {"items": page.items, "next_cursor": page.next_cursor, "source": page.source}
        )

    if projects is not None:
        # 고정 경로는 ``/conversations/{conversation_id}``보다 먼저 등록한다.
        @router.get(
            "/conversations/project-counts", response_model=ProjectCounts, responses=errors()
        )
        async def conversation_project_counts() -> ProjectCounts:
            """``project_id``별 대화 수(보관한 대화 포함, 프로젝트 없음 = ``no_project``)."""
            return count_projects(projects())

        @router.post(
            "/conversations/assign-project", response_model=AssignProjectResult, responses=errors()
        )
        async def assign_conversation_project(body: AssignProjectRequest) -> AssignProjectResult:
            """대화를 프로젝트에 넣는다. ``ids``는 지금 프로젝트와 상관없이 옮기고,
            ``from_null``은 프로젝트 없는 대화만 넣는다. 없는 id는 ``skipped``(``not_found``)."""
            return assign_project(projects(), body)

    if mover is not None:

        @router.post(
            "/conversations/move-to-project",
            response_model=RecordsMoveResult,
            responses=errors(409),
        )
        async def move_conversations_to_project(body: RecordsMoveRequest) -> RecordsMoveResult:
            """앱 DB의 대화를 그 프로젝트 기록 DB로 옮긴다(대화 + 대기열, 연동이 있으면 그 대화의
            Run도 함께). 대상에 같은 id가 있으면 ``skipped``, 실행 중인 대화는 ``failed``
            (``conversation.move_busy``). 복사 -> 개수·값 확인 -> 원본 삭제(``remove_source``)이고
            실패하면 대상을 되돌린다. 기록 DB를 쓸 수 없으면 409 ``project.records_unavailable``."""
            return await run_in_threadpool(mover().move, body)

    @router.post(
        "/conversations", response_model=Conversation, status_code=201, responses=errors(409)
    )
    async def create_conversation(body: CreateConversationRequest) -> Conversation:
        """대화를 만든다. 팀 구성이 없으면 404, 팀 구성 조회를 쓸 수 없으면 409."""
        require_graphs()
        return (await chat(body.project_id)).create(body)

    @router.get("/conversations/{conversation_id}", response_model=Conversation, responses=errors())
    async def get_conversation(conversation_id: str, project: str | None = None) -> Conversation:
        return (await chat(project)).get(conversation_id)

    @router.get(
        "/conversations/{conversation_id}/locate",
        response_model=ConversationLocation,
        responses=errors(409),
    )
    async def locate_conversation(conversation_id: str) -> ConversationLocation:
        """그 대화가 있는 기록 공간(``project_id``, null = 앱 기록).

        없으면 404 ``not_found``, 여러 공간에 있으면 409 ``conversation.ambiguous``
        (``details.project_ids``)."""
        host = service()
        method = getattr(host, "locate", None)
        if callable(method):
            project_id: str | None = await run_in_threadpool(method, conversation_id)
            return ConversationLocation(project_id=project_id)
        host.get(conversation_id)  # 없으면 404
        return ConversationLocation(project_id=None)

    @router.patch(
        "/conversations/{conversation_id}", response_model=Conversation, responses=errors(409)
    )
    async def update_conversation(
        conversation_id: str, body: UpdateConversationRequest, project: str | None = None
    ) -> Conversation:
        """제목·보관·팀 구성 전환(`graph_id`, 새 팀 구성에 없는 노드의 세션은 버린다)."""
        if body.graph_id is not None:
            require_graphs()
        return (await chat(project)).update(conversation_id, body)

    @router.delete("/conversations/{conversation_id}", status_code=204, responses=errors())
    async def delete_conversation(conversation_id: str, project: str | None = None) -> Response:
        """대화를 지운다(실행 중 턴 취소, 대기열 버림). Run 기록은 남는다."""
        (await chat(project)).delete(conversation_id)
        return Response(status_code=204)

    @router.get(
        "/conversations/{conversation_id}/turns", response_model=list[ChatTurn], responses=errors()
    )
    async def list_turns(
        conversation_id: str,
        before: str | None = None,
        limit: Annotated[int | None, Query(ge=1, le=MAX_TURN_LIMIT)] = None,
        project: str | None = None,
    ) -> list[ChatTurn]:
        """턴 목록(오래된 순). `before` = 커서(턴의 `run_id`), 그 앞의 턴 중 최근 `limit`개."""
        return (await chat(project)).turns(conversation_id, before=before, limit=limit)

    @router.get(
        "/conversations/{conversation_id}/sessions",
        response_model=ConversationSessions,
        responses=errors(),
    )
    async def conversation_sessions(
        conversation_id: str, project: str | None = None
    ) -> ConversationSessions:
        """노드 세션을 이 앱에서 이어 갈 수 있나(design §PI.4.6.4). `continuable=false`면 보내기가
        409 `chat.session_unavailable`이다(`on_missing_session: "fresh"`로 새 세션 선택)."""
        return (await chat(project)).session_states(conversation_id)

    @router.post(
        "/conversations/{conversation_id}/messages",
        response_model=Run | QueuedMessage,
        status_code=202,
        responses=errors(409),
    )
    async def post_message(
        conversation_id: str, body: PostMessageRequest, project: str | None = None
    ) -> Run | QueuedMessage:
        """메시지 → 턴 시작(`Run`) 또는 대기열(`{queued: true, id, position, text}`).

        이 앱에 세션 기록이 없는 노드가 있으면 409 `chat.session_unavailable`
        (`details{conversation_id, node_ids}`) — `on_missing_session: "fresh"`면 그 노드만 새
        세션으로 시작한다.
        실행 중이고 `chat.busy_policy = reject`면 409 `conversation_busy`. 멈춘 항목이 남아 있으면
        `queue` 정책에서는 그 뒤에 줄을 선다. 턴 실행기가 연결되지 않았으면 409
        `feature_unavailable`.
        """
        target = await chat(project)
        result = await target.post_message(conversation_id, body)
        if isinstance(result, Run):
            # 시작하는 동안 대화가 지워졌으면 턴은 취소됐다(ac-chat) → 없는 대화로 알린다.
            target.get(conversation_id)
        return result

    @router.get(
        "/conversations/{conversation_id}/queue",
        response_model=list[QueuedMessage],
        responses=errors(),
    )
    async def list_queue(conversation_id: str, project: str | None = None) -> list[QueuedMessage]:
        """대기열(1 = 다음 차례, `held` = 재시작으로 멈춘 항목)."""
        return (await chat(project)).queue(conversation_id)

    @router.delete(
        "/conversations/{conversation_id}/queue/{queued_id}", status_code=204, responses=errors()
    )
    async def cancel_queued(
        conversation_id: str, queued_id: str, project: str | None = None
    ) -> Response:
        """대기열 항목 취소(204, 멈춘 항목 포함). 이미 실행됐거나 없으면 404."""
        (await chat(project)).cancel_queued(conversation_id, queued_id)
        return Response(status_code=204)

    @router.post(
        "/conversations/{conversation_id}/queue/{queued_id}/release",
        response_model=QueuedMessage,
        responses=errors(),
    )
    async def release_queued(
        conversation_id: str, queued_id: str, project: str | None = None
    ) -> QueuedMessage:
        """멈춘(held) 항목을 풀어 실행 순서에 넣는다([실행]). 쉬고 있고 맨 앞이면 곧 턴이 시작된다
        (WS `conversation.updated`로 알린다). 앞에 멈춘 항목이 있으면 그것이 풀리거나 지워질 때까지
        기다린다. 이미 풀린 항목도 200. 없으면 404.
        """
        return await (await chat(project)).release_queued(conversation_id, queued_id)

    return router


__all__ = [
    "MAX_CONVERSATION_QUERY_LENGTH",
    "MAX_TURN_LIMIT",
    "SOURCE_APP",
    "build_router",
    "errors",
]
