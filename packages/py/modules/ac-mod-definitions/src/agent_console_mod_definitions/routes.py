"""REST: 에이전트·팀 구성(그래프)·공통 설정 CRUD(design §5.2, §R9.5, §3R.1.3).

응답은 저장 원문("생략 = 상속": 쓰지 않은 키는 없다)과 ``ETag`` = ``version_hash``다. 모델로
직렬화하지 않는다(기본값·null이 채워져 생략과 명시를 구분할 수 없게 된다). 경로는 접두 없이
만들고 호스트가 ``/api/v1``을 붙인다.

- ``/agents`` GET·POST, ``/agents/{id}`` GET·PUT·DELETE
- ``/graphs`` GET(요약 목록)·POST, ``/graphs/{id}`` GET·PUT(``If-Match`` 필수)·DELETE,
  ``POST /graphs/{id}/duplicate``
- ``/settings`` GET(파일이 없으면 ``{}``)·PUT(``If-Match`` 선택)
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent_console_contracts import (
    Agent,
    DuplicateGraphRequest,
    ErrorResponse,
    Graph,
    GraphSummary,
    VersionedGraph,
    WorkspaceSettings,
)
from agent_console_modkit.host import IfMatchHeader, if_match_version, json_with_etag
from agent_console_store import AGENT_KIND, GRAPH_KIND, SETTINGS_KIND, NotFound, StoredDefinition

from .errors import IdMismatchError
from .service import DefinitionService

_ERROR_STATUSES = (400, 401, 403, 404, 413, 422, 500)

AGENT_LABEL = "에이전트 설정"
GRAPH_LABEL = "팀 구성"
SETTINGS_LABEL = "공통 설정"


def errors(*extra: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses``: 공통 오류 + 추가 상태(모두 ``ErrorResponse``)."""
    return {s: {"model": ErrorResponse} for s in (*_ERROR_STATUSES, *extra)}


def stored_document(stored: StoredDefinition, model: type[BaseModel]) -> Any:
    """원문 사본. ``model``로 검증만 한다(맞지 않으면 ``ValidationError`` → 422)."""
    stored.model(model)
    return copy.deepcopy(stored.document)


def definition_response(
    stored: StoredDefinition, model: type[BaseModel], *, status_code: int = 200
) -> JSONResponse:
    return json_with_etag(
        stored_document(stored, model), version=stored.version_hash, status_code=status_code
    )


def versioned_graph(stored: StoredDefinition, *, status_code: int = 200) -> JSONResponse:
    """``VersionedGraph`` 모양의 원문 응답(``graph`` = 저장 원문, ``ETag`` = ``version_hash``)."""
    body = {
        "graph": stored_document(stored, Graph),
        "version_hash": stored.version_hash,
        "saved_at": stored.saved_at,
    }
    return json_with_etag(body, version=stored.version_hash, status_code=status_code)


def same_id(path_id: str, body_id: str, what: str) -> None:
    if path_id != body_id:
        raise IdMismatchError(path_id, body_id, what)


def build_router(service: Callable[[], DefinitionService]) -> APIRouter:
    """정의 경로 라우터(``service``는 요청마다 부른다)."""
    router = APIRouter()
    agent, graph_kind, settings_kind = AGENT_KIND.name, GRAPH_KIND.name, SETTINGS_KIND.name

    # ------------------------------------------------------------ 에이전트

    @router.get("/agents", response_model=list[Agent], responses=errors())
    async def list_agents() -> JSONResponse:
        """저장 원문 목록(id 순). 읽을 수 없거나 계약에 맞지 않는 파일은 뺀다."""
        return json_with_etag(service().documents(agent, Agent))

    @router.post("/agents", response_model=Agent, status_code=201, responses=errors(409))
    async def create_agent(body: Agent) -> JSONResponse:
        """만들기. 저장 전 검사에 error가 있으면 422. 응답은 저장 원문(201, ``ETag``)."""
        svc = service()
        svc.check(agent, body, AGENT_LABEL)
        return definition_response(svc.store.create(agent, body), Agent, status_code=201)

    @router.get("/agents/{agent_id}", response_model=Agent, responses=errors())
    async def get_agent(agent_id: str) -> JSONResponse:
        """저장 원문 + ``ETag``."""
        return definition_response(service().store.get(agent, agent_id), Agent)

    @router.put("/agents/{agent_id}", response_model=Agent, responses=errors(412))
    async def put_agent(agent_id: str, body: Agent, if_match: IfMatchHeader = None) -> JSONResponse:
        """저장(요청에 쓴 키만 저장한다). 응답은 저장 원문 + 새 ``ETag``."""
        same_id(agent_id, body.id, "에이전트")
        svc = service()
        svc.check(agent, body, AGENT_LABEL)
        stored = svc.store.save(agent, body, expected_version=if_match_version(if_match))
        return definition_response(stored, Agent)

    @router.delete("/agents/{agent_id}", status_code=204, responses=errors(412))
    async def delete_agent(agent_id: str, if_match: IfMatchHeader = None) -> Response:
        """삭제(204). ``If-Match``는 선택(주면 지금 버전과 같아야 한다)."""
        service().store.delete(agent, agent_id, expected_version=if_match_version(if_match))
        return Response(status_code=204)

    # ------------------------------------------------------------ 팀 구성(그래프)

    @router.get("/graphs", response_model=list[GraphSummary], responses=errors())
    async def list_graphs(
        validate: Annotated[
            bool, Query(description="false면 검증 요약(`validation`)을 계산하지 않는다(null).")
        ] = True,
    ) -> list[GraphSummary]:
        """목록(본문 없음). ``entry_labels`` = 입구 노드 표시 이름, ``validation`` = 검증 요약.
        제공하는 모듈이 꺼져 있으면 둘 다 null."""
        return service().graph_summaries(validate=validate)

    @router.post("/graphs", response_model=VersionedGraph, status_code=201, responses=errors(409))
    async def create_graph(body: Graph) -> JSONResponse:
        """만들기. 저장 전 검사에 error가 있으면 422. 응답 ``graph``는 저장 원문(201)."""
        svc = service()
        svc.check(graph_kind, body, GRAPH_LABEL)
        return versioned_graph(svc.store.create(graph_kind, body), status_code=201)

    @router.get("/graphs/{graph_id}", response_model=VersionedGraph, responses=errors())
    async def get_graph(graph_id: str) -> JSONResponse:
        """``graph`` = 저장 원문 + ``ETag``."""
        return versioned_graph(service().store.get(graph_kind, graph_id))

    @router.put("/graphs/{graph_id}", response_model=VersionedGraph, responses=errors(412, 428))
    async def put_graph(graph_id: str, body: Graph, if_match: IfMatchHeader = None) -> JSONResponse:
        """저장. ``If-Match`` 없음 → 428 ``version_required``, 불일치 → 412 ``version_conflict``."""
        same_id(graph_id, body.id, "그래프")
        svc = service()
        svc.check(graph_kind, body, GRAPH_LABEL)
        stored = svc.store.save(graph_kind, body, expected_version=if_match_version(if_match))
        return versioned_graph(stored)

    @router.delete("/graphs/{graph_id}", status_code=204, responses=errors(412))
    async def delete_graph(graph_id: str, if_match: IfMatchHeader = None) -> Response:
        """삭제(204). ``If-Match``는 선택. 버전 이력은 남는다."""
        service().store.delete(graph_kind, graph_id, expected_version=if_match_version(if_match))
        return Response(status_code=204)

    @router.post(
        "/graphs/{graph_id}/duplicate",
        response_model=VersionedGraph,
        status_code=201,
        responses=errors(409),
    )
    async def duplicate_graph(graph_id: str, body: DuplicateGraphRequest) -> JSONResponse:
        """서버에서 복제한다. 새 id가 이미 있으면 409 ``already_exists``."""
        store = service().store
        source = store.get(graph_kind, graph_id).document
        stored = store.create(
            graph_kind,
            {**source, "id": body.id, "name": body.name},
            message=f"{graph_id}에서 복제",
        )
        return versioned_graph(stored, status_code=201)

    # ------------------------------------------------------------ 공통 설정

    @router.get("/settings", response_model=WorkspaceSettings, responses=errors())
    async def get_settings() -> JSONResponse:
        """저장 원문(쓰지 않은 키는 없다). 파일이 없으면 ``{}``(ETag 없음)."""
        try:
            stored = service().store.get(settings_kind, settings_kind)
        except NotFound:
            return json_with_etag({})
        return definition_response(stored, WorkspaceSettings)

    @router.put("/settings", response_model=WorkspaceSettings, responses=errors(412))
    async def put_settings(body: WorkspaceSettings, if_match: IfMatchHeader = None) -> JSONResponse:
        """저장(요청에 쓴 키만). ``If-Match``는 선택(주면 지금 버전과 같아야 한다)."""
        svc = service()
        svc.check(settings_kind, body, SETTINGS_LABEL)
        stored = svc.store.save(settings_kind, body, expected_version=if_match_version(if_match))
        return definition_response(stored, WorkspaceSettings)

    return router


__all__ = ["build_router", "definition_response", "errors", "same_id", "versioned_graph"]
