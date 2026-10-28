"""REST 경로(접두 없음, 호스트가 ``/api/v1`` 아래 붙인다, design §R5.1·§2R.10).

- 대화: ``GET/POST /conversations``, ``GET/PATCH/DELETE /conversations/{id}``,
  ``GET /conversations/{id}/turns``, ``POST /conversations/{id}/messages``
- 대기열: ``GET /conversations/{id}/queue``, ``DELETE …/queue/{queued_id}``,
  ``POST …/queue/{queued_id}/release``

라우트는 요청 파싱 → ``ChatService`` 호출 → 응답 변환만 한다. 대기열(``chat.busy_policy = queue``)은
저장소에 남고, 서버를 다시 시작하면 ``chat.queue_after_restart``대로 처리한다(턴 실행기를 주는
연동 모듈이 시작할 때).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from agent_console_chat import ChatService
from agent_console_contracts import (
    AssignProjectRequest,
    AssignProjectResult,
    ChatTurn,
    Conversation,
    ConversationSummary,
    CreateConversationRequest,
    ErrorResponse,
    PostMessageRequest,
    ProjectCounts,
    QueuedMessage,
    Run,
    UpdateConversationRequest,
)
from agent_console_store import ProjectAssignStore, assign_project, count_projects

MAX_TURN_LIMIT = 500

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
) -> APIRouter:
    """대화·대기열 라우터.

    Args:
        service: 대화 서비스를 돌려주는 함수(요청마다 부른다).
        require_graphs: 팀 구성을 읽어야 하는 요청(만들기·팀 구성 바꾸기) 전에 부른다. 팀 구성
            조회를 쓸 수 없으면 예외(예: ``feature_unavailable``)를 던진다.
        projects: 프로젝트 넣기·개수 포트(``project_id`` 열을 가진 저장소).
            없으면 두 경로를 만들지 않는다.
    """
    router = APIRouter()

    @router.get("/conversations", response_model=list[ConversationSummary], responses=errors())
    async def list_conversations(
        graph_id: str | None = None,
        archived: bool | None = None,
        project: str | None = None,
    ) -> list[ConversationSummary]:
        """대화 요약(최근 갱신순): 마지막 턴 상태·대기열 수·대기 중 상호작용 수.
        ``project`` = 그 ``project_id``인 대화만(불투명 문자열, 생략 = 모두)."""
        return service().list(graph_id=graph_id, archived=archived, project_id=project)

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

    @router.post(
        "/conversations", response_model=Conversation, status_code=201, responses=errors(409)
    )
    async def create_conversation(body: CreateConversationRequest) -> Conversation:
        """대화를 만든다. 팀 구성이 없으면 404, 팀 구성 조회를 쓸 수 없으면 409."""
        require_graphs()
        return service().create(body)

    @router.get("/conversations/{conversation_id}", response_model=Conversation, responses=errors())
    async def get_conversation(conversation_id: str) -> Conversation:
        return service().get(conversation_id)

    @router.patch(
        "/conversations/{conversation_id}", response_model=Conversation, responses=errors(409)
    )
    async def update_conversation(
        conversation_id: str, body: UpdateConversationRequest
    ) -> Conversation:
        """제목·보관·팀 구성 전환(`graph_id`, 새 팀 구성에 없는 노드의 세션은 버린다)."""
        if body.graph_id is not None:
            require_graphs()
        return service().update(conversation_id, body)

    @router.delete("/conversations/{conversation_id}", status_code=204, responses=errors())
    async def delete_conversation(conversation_id: str) -> Response:
        """대화를 지운다(실행 중 턴 취소, 대기열 버림). Run 기록은 남는다."""
        service().delete(conversation_id)
        return Response(status_code=204)

    @router.get(
        "/conversations/{conversation_id}/turns", response_model=list[ChatTurn], responses=errors()
    )
    async def list_turns(
        conversation_id: str,
        before: str | None = None,
        limit: Annotated[int | None, Query(ge=1, le=MAX_TURN_LIMIT)] = None,
    ) -> list[ChatTurn]:
        """턴 목록(오래된 순). `before` = 커서(턴의 `run_id`), 그 앞의 턴 중 최근 `limit`개."""
        return service().turns(conversation_id, before=before, limit=limit)

    @router.post(
        "/conversations/{conversation_id}/messages",
        response_model=Run | QueuedMessage,
        status_code=202,
        responses=errors(409),
    )
    async def post_message(conversation_id: str, body: PostMessageRequest) -> Run | QueuedMessage:
        """메시지 → 턴 시작(`Run`) 또는 대기열(`{queued: true, id, position, text}`).

        실행 중이고 `chat.busy_policy = reject`면 409 `conversation_busy`. 멈춘 항목이 남아 있으면
        `queue` 정책에서는 그 뒤에 줄을 선다. 턴 실행기가 연결되지 않았으면 409
        `feature_unavailable`.
        """
        chat = service()
        result = await chat.post_message(conversation_id, body)
        if isinstance(result, Run):
            # 시작하는 동안 대화가 지워졌으면 턴은 취소됐다(ac-chat) → 없는 대화로 알린다.
            chat.get(conversation_id)
        return result

    @router.get(
        "/conversations/{conversation_id}/queue",
        response_model=list[QueuedMessage],
        responses=errors(),
    )
    async def list_queue(conversation_id: str) -> list[QueuedMessage]:
        """대기열(1 = 다음 차례, `held` = 재시작으로 멈춘 항목)."""
        return service().queue(conversation_id)

    @router.delete(
        "/conversations/{conversation_id}/queue/{queued_id}", status_code=204, responses=errors()
    )
    async def cancel_queued(conversation_id: str, queued_id: str) -> Response:
        """대기열 항목 취소(204, 멈춘 항목 포함). 이미 실행됐거나 없으면 404."""
        service().cancel_queued(conversation_id, queued_id)
        return Response(status_code=204)

    @router.post(
        "/conversations/{conversation_id}/queue/{queued_id}/release",
        response_model=QueuedMessage,
        responses=errors(),
    )
    async def release_queued(conversation_id: str, queued_id: str) -> QueuedMessage:
        """멈춘(held) 항목을 풀어 실행 순서에 넣는다([실행]). 쉬고 있고 맨 앞이면 곧 턴이 시작된다
        (WS `conversation.updated`로 알린다). 앞에 멈춘 항목이 있으면 그것이 풀리거나 지워질 때까지
        기다린다. 이미 풀린 항목도 200. 없으면 404.
        """
        return await service().release_queued(conversation_id, queued_id)

    return router


__all__ = ["MAX_TURN_LIMIT", "build_router", "errors"]
