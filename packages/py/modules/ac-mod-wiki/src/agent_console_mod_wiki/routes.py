"""REST: 위키 화면 정보·위키·페이지·기록·검색·그래프·점검·변경·문법·틀·zip(design §7R.7·§7R.18.1).

경로는 접두 없이 만들고 호스트가 ``/api/v1``을 붙인다. 모든 경로가 ``?project=<공간 이름>``을 받는다
(없으면 단독 루트, 연동이 없는데 이름이 오면 409 ``wiki.spaces_unavailable``). 응답 모델은 계약
``agent_console_contracts.wiki``이고 OpenAPI에 실린다. 처리기는 동기 함수다(파일·DB 일은 스레드
풀에서, WS 알림은 ``LoopPublisher``가 루프로 옮긴다).

- ``GET /wiki/info`` · ``GET /wiki/changes``(공간 전체)
- ``GET·POST /wiki/wikis`` · ``GET·PUT·DELETE /wiki/wikis/{wiki}``
- ``GET …/pages`` · ``GET·PUT·DELETE …/pages/{path}`` · ``POST …/pages/{path}/preview`` ·
  ``POST …/pages/{path}/move`` · ``GET …/pages/{path}/history[/{version}]`` ·
  ``POST …/pages/{path}/restore``
- ``POST …/link-text`` · ``GET …/templates`` · ``POST …/templates/{id}/render``
- ``GET …/search`` · ``GET …/graph`` · ``GET …/lint`` · ``GET …/changes`` · ``GET …/syntax`` ·
  ``POST …/scan`` · ``POST …/export`` · ``POST …/import``

페이지 경로의 마지막 구성요소가 ``history``(또는 ``history/<수>``)인 페이지는 ``GET``으로 읽을 수
없다(기록 경로와 겹침 — ``PAGE_ROUTE_WORDS``). 쓰기·지우기는 된다.
"""

from __future__ import annotations

import asyncio
import urllib.parse
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import JSONResponse

from agent_console_contracts import ErrorCodes, ErrorResponse
from agent_console_contracts.wiki import (
    EffectiveWikiSyntax,
    KnownWikiImportStatuses,
    WikiChangePage,
    WikiCreateRequest,
    WikiDefinition,
    WikiGraph,
    WikiHistoryPage,
    WikiImportResult,
    WikiInfo,
    WikiLinkText,
    WikiLinkTextRequest,
    WikiLintReport,
    WikiMoveRequest,
    WikiMoveResult,
    WikiPageList,
    WikiPagePreview,
    WikiPagePreviewRequest,
    WikiPageTemplateInfo,
    WikiPageView,
    WikiPageWrite,
    WikiRestoreRequest,
    WikiScanResult,
    WikiSearchResult,
    WikiSummary,
    WikiTemplateRender,
    WikiTemplateRenderRequest,
    WikiView,
)
from agent_console_modkit.host import (
    TEXT_FILE_MEDIA_TYPE,
    IfMatchHeader,
    SpaceQuery,
    etag,
    if_match_version,
    with_issues,
)
from agent_console_wiki import WriteOutcome, export_zip, import_zip

from .errors import WikiRequestError
from .rules_routes import build_rules_router
from .service import WikiScope, WikiService, user_author

PAGE_ROUTE_WORDS: tuple[str, ...] = ("history",)
"""``GET …/pages/<경로>/<이 말>``이 기록 경로라 그 이름으로 끝나는 페이지를 ``GET``으로 읽을 수
없는 말(경로 어휘)."""

ZIP_MEDIA_TYPE = "application/zip"
MARKDOWN_MEDIA_TYPE = TEXT_FILE_MEDIA_TYPE

_ERROR_STATUSES = (400, 404, 409, 412, 422, 428, 500)

IfNoneMatchHeader = Annotated[
    str | None,
    Header(alias="If-None-Match", description="`*`이면 페이지가 없을 때만 만든다."),
]


def _errors(*extra: int) -> dict[int | str, dict[str, Any]]:
    return {s: {"model": ErrorResponse} for s in (*_ERROR_STATUSES, *extra)}


def _dump(model: Any) -> Any:
    return model.model_dump(mode="json", by_alias=True)


def _issue_dicts(issues: list[Any]) -> list[dict[str, Any]]:
    return [i.model_dump(mode="json", exclude_none=True) for i in issues]


def _ops(value: str | None) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def _view_json(view: WikiPageView, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        content=_dump(view), status_code=status_code, headers={"ETag": etag(view.content_hash)}
    )


def content_disposition(filename: str) -> str:
    """``attachment; filename="…"; filename*=UTF-8''…``(ASCII가 아닌 글자는 ``_``로 바꾼 이름과
    RFC 5987 이름 둘 다)."""
    plain = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in filename)
    quoted = urllib.parse.quote(filename, safe="")
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quoted}"


def build_router(service: Callable[[], WikiService]) -> APIRouter:
    """위키 모듈 라우터(규칙 경로 포함)."""
    router = APIRouter()

    def scope(space: str | None) -> WikiScope:
        return service().scope(space)

    def written(
        svc: WikiService,
        sc: WikiScope,
        wiki_id: str,
        outcome: WriteOutcome,
        *,
        deleted: bool = False,
    ) -> None:
        if outcome.changed or deleted:
            svc.notify(sc.name, wiki_id, [outcome.path], deleted=deleted)

    # ------------------------------------------------------------ 정보·공간 전체

    @router.get("/wiki/info", response_model=WikiInfo, responses=_errors())
    def wiki_info(space: SpaceQuery = None) -> WikiInfo:
        """위키 화면 정보(페이지 폴더·능력·한도·공간 이슈)."""
        svc = service()
        return svc.info(svc.scope(space))

    @router.get("/wiki/changes", response_model=WikiChangePage, responses=_errors())
    def space_changes(
        space: SpaceQuery = None,
        author_run: Annotated[str | None, Query(description="run_id 또는 root_run_id")] = None,
        op: Annotated[str | None, Query(description="동작(쉼표 목록, 열린 문자열)")] = None,
        limit: Annotated[int, Query(ge=1)] = 50,
        cursor: str | None = None,
    ) -> WikiChangePage:
        """공간의 모든 위키를 가로지르는 최근 변경(실행 상세의 "고친 위키 페이지")."""
        svc = service()
        return svc.changes(
            svc.scope(space), author_run=author_run, ops=_ops(op), limit=limit, cursor=cursor
        )

    # ------------------------------------------------------------ 위키 정의

    @router.get("/wiki/wikis", response_model=list[WikiSummary], responses=_errors())
    def list_wikis(space: SpaceQuery = None) -> list[WikiSummary]:
        """위키 목록(카드 값 — 페이지 수·끊긴 링크·고아·점검 수·최근 변경 — 을 요청 하나로)."""
        svc = service()
        return svc.summaries(svc.scope(space))

    @router.post("/wiki/wikis", response_model=WikiView, status_code=201, responses=_errors())
    def create_wiki(body: WikiCreateRequest, space: SpaceQuery = None) -> JSONResponse:
        """위키 만들기(정의만). 같은 id가 있으면 409 ``already_exists``."""
        svc = service()
        sc = svc.scope(space)
        stored = svc.create_wiki(sc, body)
        view, version = svc.view(sc, stored.id)
        return JSONResponse(_dump(view), status_code=201, headers={"ETag": etag(version)})

    @router.get("/wiki/wikis/{wiki_id}", response_model=WikiView, responses=_errors())
    def get_wiki(wiki_id: str, space: SpaceQuery = None) -> JSONResponse:
        """위키 정의 + 합친 규칙 요약 + 이슈 + ``ETag``(정의 버전)."""
        svc = service()
        view, version = svc.view(svc.scope(space), wiki_id)
        return JSONResponse(_dump(view), headers={"ETag": etag(version)})

    @router.put("/wiki/wikis/{wiki_id}", response_model=WikiView, responses=_errors())
    def put_wiki(
        wiki_id: str, body: WikiDefinition, if_match: IfMatchHeader = None, space: SpaceQuery = None
    ) -> JSONResponse:
        """위키 정의 저장(``If-Match`` 필수 — 없으면 428, 다르면 412)."""
        svc = service()
        sc = svc.scope(space)
        svc.save_wiki(sc, wiki_id, body, expected=if_match_version(if_match))
        view, version = svc.view(sc, wiki_id)
        return JSONResponse(_dump(view), headers={"ETag": etag(version)})

    @router.delete("/wiki/wikis/{wiki_id}", status_code=204, responses=_errors())
    def delete_wiki(
        wiki_id: str, if_match: IfMatchHeader = None, space: SpaceQuery = None
    ) -> Response:
        """위키 정의만 지운다(페이지 폴더는 남는다 — 같은 id로 다시 만들면 이어 쓴다)."""
        svc = service()
        svc.delete_wiki(svc.scope(space), wiki_id, expected=if_match_version(if_match))
        return Response(status_code=204)

    # ------------------------------------------------------------ 페이지 목록

    @router.get("/wiki/wikis/{wiki_id}/pages", response_model=WikiPageList, responses=_errors())
    def list_pages(
        wiki_id: str,
        space: SpaceQuery = None,
        prefix: str | None = None,
        tag: str | None = None,
    ) -> WikiPageList:
        """페이지 요약 목록(경로 순, 상한을 넘으면 ``truncated``·``total``)."""
        return service().repository_of(scope(space), wiki_id).list_pages(prefix=prefix, tag=tag)

    # ------------------------------------------------------------ 페이지 하나(고정 꼬리 먼저)

    @router.post(
        "/wiki/wikis/{wiki_id}/pages/{page:path}/preview",
        response_model=WikiPagePreview,
        responses=_errors(),
    )
    def preview_page(
        wiki_id: str, page: str, body: WikiPagePreviewRequest, space: SpaceQuery = None
    ) -> WikiPagePreview:
        """저장 전 시험(쓰기와 같은 판단, 쓴 주체 사람). 파일·기록·색인·알림을 건드리지 않는다."""
        repo = service().repository_of(scope(space), wiki_id)
        return repo.preview(page, body.content, author=user_author())

    @router.post(
        "/wiki/wikis/{wiki_id}/pages/{page:path}/move",
        response_model=WikiMoveResult,
        responses=_errors(),
    )
    def move_page(
        wiki_id: str, page: str, body: WikiMoveRequest, space: SpaceQuery = None
    ) -> JSONResponse:
        """옮기기(이름 바꾸기). 다른 페이지의 링크 문자열만 고친다. ``dry_run``이면 미리보기."""
        svc = service()
        sc = svc.scope(space)
        if not body.dry_run:
            svc.require_writable(sc)
        result = svc.repository_of(sc, wiki_id).move(
            page,
            body.to,
            author=user_author(),
            rewrite_links=body.rewrite_links,
            if_hash=body.if_hash,
            dry_run=body.dry_run,
            message=body.message,
        )
        if result.moved:
            paths = [result.from_, result.to, *(r.path for r in result.rewritten)]
            svc.notify(sc.name, wiki_id, paths)
        return with_issues(JSONResponse(_dump(result)), _issue_dicts(result.issues))

    @router.get(
        "/wiki/wikis/{wiki_id}/pages/{page:path}/history/{version}",
        response_class=Response,
        responses={**_errors(), 200: {"content": {MARKDOWN_MEDIA_TYPE: {}}}},
    )
    def version_content(
        wiki_id: str, page: str, version: int, space: SpaceQuery = None
    ) -> Response:
        """그 버전 본문(글, ``ETag`` = 그 버전 해시). 지운 버전은 404 ``wiki.version_not_found``."""
        found, data = service().repository_of(scope(space), wiki_id).version(page, version)
        return Response(
            content=data, media_type=MARKDOWN_MEDIA_TYPE, headers={"ETag": etag(found.sha256)}
        )

    @router.get(
        "/wiki/wikis/{wiki_id}/pages/{page:path}/history",
        response_model=WikiHistoryPage,
        responses=_errors(),
    )
    def page_history(
        wiki_id: str,
        page: str,
        space: SpaceQuery = None,
        limit: Annotated[int | None, Query(ge=1)] = None,
    ) -> WikiHistoryPage:
        """페이지 기록(최근 것부터, 파일이 없어도 기록이 있으면). ``pruned`` = 보관 수로 지운 버전
        있음. 기록 저장소가 없으면 409 ``wiki.history_unavailable``."""
        return service().repository_of(scope(space), wiki_id).page_history(page, limit=limit)

    @router.post(
        "/wiki/wikis/{wiki_id}/pages/{page:path}/restore",
        response_model=WikiPageView,
        responses=_errors(),
    )
    def restore_page(
        wiki_id: str, page: str, body: WikiRestoreRequest, space: SpaceQuery = None
    ) -> JSONResponse:
        """그 버전 본문으로 새 버전(``restore``). 쓰기 규칙을 통과해야 한다(없는 경로면 만들기)."""
        svc = service()
        sc = svc.scope(space)
        svc.require_writable(sc)
        repo = svc.repository_of(sc, wiki_id)
        outcome = repo.restore(page, body.version, author=user_author(), message=body.message)
        written(svc, sc, wiki_id, outcome)
        return with_issues(_view_json(repo.view(outcome.path)), _issue_dicts(outcome.issues))

    @router.get(
        "/wiki/wikis/{wiki_id}/pages/{page:path}", response_model=WikiPageView, responses=_errors()
    )
    def get_page(wiki_id: str, page: str, space: SpaceQuery = None) -> JSONResponse:
        """페이지 보기(본문·링크(UTF-16 범위)·백링크·제목들·이슈) + ``ETag``(본문 sha256). 없으면
        404 ``wiki.page_not_found``(details ``has_history``)."""
        return _view_json(service().repository_of(scope(space), wiki_id).view(page))

    @router.put(
        "/wiki/wikis/{wiki_id}/pages/{page:path}", response_model=WikiPageView, responses=_errors()
    )
    def put_page(
        wiki_id: str,
        page: str,
        body: WikiPageWrite,
        if_match: IfMatchHeader = None,
        if_none_match: IfNoneMatchHeader = None,
        space: SpaceQuery = None,
    ) -> JSONResponse:
        """쓰기(``If-Match`` = 본문 해시, ``If-None-Match: *`` = 없을 때만 만들기). 있는 페이지를
        ``If-Match`` 없이 고치면 428. 거부 = 422 ``wiki.rule_rejected``·``wiki.secret_rejected``,
        경고 = 저장 + ``X-Console-Issues``. 새 페이지면 201."""
        svc = service()
        sc = svc.scope(space)
        svc.require_writable(sc)
        repo = svc.repository_of(sc, wiki_id)
        create_only = (if_none_match or "").strip() == "*"
        if_hash = if_match_version(if_match)
        content = body.content
        if body.template and not content:
            content = repo.render_template(body.template).content
        if not create_only and if_hash is None and repo.current(page) is not None:
            raise WikiRequestError(
                "있는 페이지를 고칠 때는 If-Match(본문 해시)가 필요합니다.",
                code=ErrorCodes.VERSION_REQUIRED,
                details={"path": page},
            )
        outcome = repo.write(
            page,
            content,
            author=user_author(),
            if_hash=if_hash,
            create_only=create_only,
            message=body.message,
        )
        written(svc, sc, wiki_id, outcome)
        status = 201 if outcome.created else 200
        return with_issues(
            _view_json(repo.view(outcome.path), status_code=status), _issue_dicts(outcome.issues)
        )

    @router.delete("/wiki/wikis/{wiki_id}/pages/{page:path}", status_code=204, responses=_errors())
    def delete_page(
        wiki_id: str, page: str, if_match: IfMatchHeader = None, space: SpaceQuery = None
    ) -> Response:
        """지우기(파일 삭제 + 기록 ``delete``, ``If-Match`` 선택). 경고는 ``X-Console-Issues``."""
        svc = service()
        sc = svc.scope(space)
        svc.require_writable(sc)
        outcome = svc.repository_of(sc, wiki_id).delete(
            page, author=user_author(), if_hash=if_match_version(if_match)
        )
        written(svc, sc, wiki_id, outcome, deleted=True)
        return with_issues(Response(status_code=204), _issue_dicts(outcome.issues))

    # ------------------------------------------------------------ 링크 넣기·틀

    @router.post(
        "/wiki/wikis/{wiki_id}/link-text", response_model=WikiLinkText, responses=_errors()
    )
    def link_text(
        wiki_id: str, body: WikiLinkTextRequest, space: SpaceQuery = None
    ) -> WikiLinkText:
        """링크 넣기 글자(문법 데이터의 삽입 틀). 틀이 있는 규칙이 없으면 422
        ``wiki.link_insert_unavailable``."""
        repo = service().repository_of(scope(space), wiki_id)
        return repo.link_text(body.from_page, body.target, label=body.label, rule_id=body.rule_id)

    @router.get(
        "/wiki/wikis/{wiki_id}/templates",
        response_model=list[WikiPageTemplateInfo],
        responses=_errors(),
    )
    def templates(wiki_id: str, space: SpaceQuery = None) -> list[WikiPageTemplateInfo]:
        """합친 페이지 틀(어느 규칙에서 왔는지 + 변수 + 틀 본문)."""
        return service().repository_of(scope(space), wiki_id).rules.template_infos()

    @router.post(
        "/wiki/wikis/{wiki_id}/templates/{template_id}/render",
        response_model=WikiTemplateRender,
        responses=_errors(),
    )
    def render_template(
        wiki_id: str,
        template_id: str,
        body: WikiTemplateRenderRequest,
        space: SpaceQuery = None,
    ) -> WikiTemplateRender:
        """페이지 틀 채우기(쓰지 않음). 없는 틀은 404 ``not_found``."""
        repo = service().repository_of(scope(space), wiki_id)
        return repo.render_template(template_id, title=body.title, values=body.values)

    # ------------------------------------------------------------ 검색·그래프·점검·변경·문법

    @router.get(
        "/wiki/wikis/{wiki_id}/search", response_model=WikiSearchResult, responses=_errors()
    )
    def search(
        wiki_id: str,
        q: Annotated[str, Query(min_length=1)],
        space: SpaceQuery = None,
        prefix: str | None = None,
        tag: Annotated[list[str] | None, Query()] = None,
        limit: Annotated[int, Query(ge=1)] = 20,
    ) -> WikiSearchResult:
        """검색(조각은 비밀 가림 뒤 자름, ``marks`` = 조각 안 UTF-16 범위)."""
        svc = service()
        repo = svc.repository_of(svc.scope(space), wiki_id)
        cap = svc.options.max_search_results
        return repo.search(q, prefix=prefix, tags=tag or [], limit=min(limit, cap))

    @router.get("/wiki/wikis/{wiki_id}/graph", response_model=WikiGraph, responses=_errors())
    def graph(
        wiki_id: str,
        space: SpaceQuery = None,
        center: str | None = None,
        depth: Annotated[int, Query(ge=0)] = 1,
        limit: Annotated[int | None, Query(ge=1)] = None,
    ) -> WikiGraph:
        """링크 그래프(center 없음 = 전체, 칸 수 상한 ``graph_max_nodes``)."""
        return (
            service().repository_of(scope(space), wiki_id).graph(center, depth=depth, limit=limit)
        )

    @router.get("/wiki/wikis/{wiki_id}/lint", response_model=WikiLintReport, responses=_errors())
    def lint(wiki_id: str, space: SpaceQuery = None) -> WikiLintReport:
        """점검(기본 점검 + 점검 규칙 + 쓰기 규칙 사후 점검)."""
        return service().repository_of(scope(space), wiki_id).lint()

    @router.get("/wiki/wikis/{wiki_id}/changes", response_model=WikiChangePage, responses=_errors())
    def wiki_changes(
        wiki_id: str,
        space: SpaceQuery = None,
        author_run: Annotated[str | None, Query(description="run_id 또는 root_run_id")] = None,
        op: Annotated[str | None, Query(description="동작(쉼표 목록, 열린 문자열)")] = None,
        limit: Annotated[int, Query(ge=1)] = 50,
        cursor: str | None = None,
    ) -> WikiChangePage:
        """이 위키의 최근 변경(커서)."""
        svc = service()
        repo = svc.repository_of(svc.scope(space), wiki_id)
        return repo.changes(
            author_run=author_run,
            ops=_ops(op),
            limit=min(limit, svc.options.max_changes_page),
            cursor=cursor,
        )

    @router.get(
        "/wiki/wikis/{wiki_id}/syntax", response_model=EffectiveWikiSyntax, responses=_errors()
    )
    def syntax(wiki_id: str, space: SpaceQuery = None) -> EffectiveWikiSyntax:
        """유효 문법(값마다 출처, 컴파일 이슈)."""
        return service().repository_of(scope(space), wiki_id).syntax.effective

    @router.post("/wiki/wikis/{wiki_id}/scan", response_model=WikiScanResult, responses=_errors())
    def scan(wiki_id: str, space: SpaceQuery = None) -> WikiScanResult:
        """외부 변경 다시 읽기(기록에 ``external``·``import``·``delete``) + 검색 색인 맞추기."""
        svc = service()
        return svc.scan(svc.scope(space), wiki_id)

    # ------------------------------------------------------------ zip

    @router.post(
        "/wiki/wikis/{wiki_id}/export",
        response_class=Response,
        responses={**_errors(), 200: {"content": {ZIP_MEDIA_TYPE: {}}}},
    )
    def export(wiki_id: str, space: SpaceQuery = None) -> Response:
        """페이지 파일 zip(경로 순·고정 시각). ``Content-Disposition: attachment; filename=…``."""
        repo = service().repository_of(scope(space), wiki_id)
        return Response(
            content=export_zip(repo),
            media_type=ZIP_MEDIA_TYPE,
            headers={"Content-Disposition": content_disposition(f"{wiki_id}.zip")},
        )

    @router.post(
        "/wiki/wikis/{wiki_id}/import",
        response_model=WikiImportResult,
        responses=_errors(),
        openapi_extra={
            "requestBody": {"content": {ZIP_MEDIA_TYPE: {"schema": {"type": "string"}}}}
        },
    )
    async def import_pages(
        request: Request,
        wiki_id: str,
        space: SpaceQuery = None,
        policy: Literal["skip", "overwrite", "rename"] = "skip",
        dry_run: bool = False,
    ) -> WikiImportResult:
        """zip 가져오기(요청 본문 = zip 바이트, 같은 경로는 ``policy``). 쓰기 판단·기록·색인을
        그대로 거친다(쓴 주체 사람). ``dry_run``이면 쓰지 않는다."""
        data = await request.body()
        return await asyncio.to_thread(_import, service(), space, wiki_id, data, policy, dry_run)

    router.include_router(build_rules_router(service))
    return router


def _import(
    svc: WikiService,
    space: str | None,
    wiki_id: str,
    data: bytes,
    policy: Literal["skip", "overwrite", "rename"],
    dry_run: bool,
) -> WikiImportResult:
    sc = svc.scope(space)
    if not dry_run:
        svc.require_writable(sc)
    repo = svc.repository_of(sc, wiki_id)
    result = import_zip(
        repo,
        data,
        policy=policy,
        dry_run=dry_run,
        author=user_author(),
        limits=svc.options.export_limits.zip_limits(),
    )
    if not dry_run:
        paths = [i.to or i.path for i in result.items if i.status not in _UNWRITTEN]
        if paths:
            svc.notify(sc.name, wiki_id, paths)
    return result


_UNWRITTEN = frozenset({KnownWikiImportStatuses.SKIPPED, KnownWikiImportStatuses.REJECTED})

__all__ = ["PAGE_ROUTE_WORDS", "build_router", "content_disposition"]
