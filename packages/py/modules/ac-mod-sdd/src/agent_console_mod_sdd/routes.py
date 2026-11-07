"""REST: 스펙·문서·작업·계획·추적·문서 틀·가져오기/내보내기(design §6R.7·§6R.18).

경로는 접두 없이 만들고 호스트가 ``/api/v1``을 붙인다. 모든 경로가 ``?project=<공간 이름>``을 받는다
(없으면 단독 루트, 연동이 없는데 이름이 오면 409 ``sdd.spaces_unavailable``). 응답 모델은 계약
``agent_console_contracts.sdd``이고 OpenAPI에 실린다.

- ``GET /sdd/info`` · ``GET /sdd/templates`` · ``GET /sdd/templates/variables`` ·
  ``POST /sdd/templates/check``
- 문서 틀 하나(``template_routes``, 6R.20a): ``POST /sdd/templates`` ·
  ``GET·PUT·DELETE /sdd/templates/{id}`` · ``…/variables`` · ``…/files[/{path}]`` ·
  ``…/versions[/{hash}[/files[/{path}]]]`` · ``POST …/versions/{hash}/restore``
- ``GET·POST /sdd/specs`` · ``POST /sdd/specs/import`` · ``GET /sdd/import/files``
- ``GET·PUT·DELETE /sdd/specs/{id}`` · ``POST /sdd/specs/{id}/check``
- ``GET·PUT /sdd/specs/{id}/documents/{doc}`` · ``POST …/documents/{doc}/state``
- ``GET /sdd/specs/{id}/tasks`` · ``PATCH /sdd/specs/{id}/tasks/{key}``
- ``GET /sdd/specs/{id}/plan`` · ``/trace`` · ``/variables`` · ``/syntax``
- ``GET …/tasks/{key}/actions`` · ``POST …/tasks/{key}/actions/{integration}/{action}`` ·
  ``POST …/bulk-actions`` · ``POST …/bulk-start`` · ``POST …/automation/{stop|resume}``
- ``POST /sdd/specs/{id}/save-as-template`` · ``POST /sdd/specs/{id}/export``
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent_console_contracts import ErrorCodes, ErrorResponse, Issue
from agent_console_contracts.sdd import (
    AutomationState,
    BulkActionsRequest,
    BulkActionsResult,
    BulkStartRequest,
    BulkStartResult,
    DocumentStateChange,
    EffectiveSyntax,
    ImportFileListing,
    KnownTaskActionStatuses,
    KnownTransitionActors,
    ParsedTask,
    RulesCheckRequest,
    RulesCheckResult,
    SaveAsTemplateRequest,
    SaveAsTemplateResult,
    SddInfo,
    SpecCreateRequest,
    SpecDefinition,
    SpecDocumentContent,
    SpecDocumentWrite,
    SpecExportRequest,
    SpecExportResult,
    SpecImportRequest,
    SpecSummary,
    SpecTemplateSummary,
    SpecView,
    TaskAction,
    TaskActionKey,
    TaskActionRequest,
    TaskActionResult,
    TaskPatch,
    TaskPatchResult,
    TaskPlan,
    TemplateVariable,
    TraceMatrix,
)
from agent_console_modkit.host import IfMatchHeader, SpaceQuery, if_match_version
from agent_console_sdd import (
    SpecNotFoundError,
    check_rules,
    export_documents,
    find_task,
    import_documents,
    list_import_files,
    plan,
    run_input_variables,
    trace,
)

from .errors import SddRequestError
from .secrets import SCAN_REJECT, SecretRejectedError
from .service import SddScope, SddService, gather_actions
from .template_routes import build_template_router

_ERROR_STATUSES = (400, 401, 403, 404, 409, 422, 500)
_HUMAN = KnownTransitionActors.HUMAN
_STOP = "stop"
_RESUME = "resume"

IfNoneMatchHeader = Annotated[
    str | None,
    Header(alias="If-None-Match", description="`*`이면 본문 파일이 없을 때만 만든다."),
]


def errors(*extra: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses``: 공통 오류 + 추가 상태(모두 ``ErrorResponse``)."""
    return {s: {"model": ErrorResponse} for s in (*_ERROR_STATUSES, *extra)}


def _dump(model: BaseModel) -> Any:
    return model.model_dump(mode="json", by_alias=True)


def _json(model: BaseModel, *, version: str | None = None, status_code: int = 200) -> JSONResponse:
    headers = {"ETag": f'"{version}"'} if version else None
    return JSONResponse(content=_dump(model), status_code=status_code, headers=headers)


def _roles_fields(syntax: EffectiveSyntax) -> list[str]:
    task = syntax.syntax.task
    roles = task.roles if task is not None and task.roles else {}
    return list(roles)


def _parse_fields(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in values:
        key, sep, value = raw.partition("=")
        if not sep or not key:
            raise SddRequestError(
                "field 질의는 '<필드>=<값>' 모양이어야 합니다.", details={"param": "field"}
            )
        out[key] = value
    return out


def _filter_tasks(
    tasks: list[ParsedTask],
    *,
    status: list[str],
    stage: list[str],
    fields: dict[str, str],
    ready: bool | None,
    q: str | None,
) -> list[ParsedTask]:
    needle = q.casefold() if q else None
    out: list[ParsedTask] = []
    for t in tasks:
        if status and t.status not in status:
            continue
        if stage and (t.stage is None or t.stage.id not in stage):
            continue
        if any(t.fields.get(k) != v for k, v in fields.items()):
            continue
        if ready is not None and t.ready != ready:
            continue
        if needle is not None and not any(
            needle in (text or "").casefold() for text in (t.key, t.id, t.title)
        ):
            continue
        out.append(t)
    return out


def build_router(service: Callable[[], SddService]) -> APIRouter:
    """스펙 경로 라우터(``service()``는 요청마다 부른다)."""
    router = APIRouter()

    def scope(space: str | None) -> SddScope:
        return service().scope(space)

    def task_of(sc: SddScope, spec_id: str, key: str) -> tuple[Any, ParsedTask]:
        loaded = sc.repository.load(spec_id)
        task = find_task(loaded.index, key)
        if task is None:
            raise SpecNotFoundError("task", key)
        return loaded, task

    # ------------------------------------------------------------ 정보·문서 틀

    @router.get("/sdd/info", response_model=SddInfo, responses=errors())
    async def get_info(space: SpaceQuery = None) -> SddInfo:
        """화면 정보: 스펙 폴더·한도·능력(포트 유무로 계산)·라벨 표시 규칙."""
        svc = service()
        return svc.info(svc.scope(space))

    @router.get("/sdd/templates", response_model=list[SpecTemplateSummary], responses=errors())
    async def list_templates(space: SpaceQuery = None) -> list[SpecTemplateSummary]:
        """이 공간의 문서 틀 목록(공간 이름이 없으면 앱 라이브러리, 정의 모듈이 꺼지면 단독
        루트)."""
        return scope(space).repository.template_summaries()

    @router.get(
        "/sdd/templates/variables", response_model=list[TemplateVariable], responses=errors()
    )
    async def template_variables(
        template: Annotated[
            str | None, Query(description="문서 틀 id. 생략하면 문서 없는 새 틀 기준.")
        ] = None,
        space: SpaceQuery = None,
    ) -> list[TemplateVariable]:
        """문서 틀 기준 실행 입력 틀 변수 표(§6R.18 Q9). 틀을 생략하면 문서 변수 없이 고정 변수와
        사용자 설정·기본 문법의 역할 필드만."""
        repo = scope(space).repository
        if template is None:
            return run_input_variables([], fields=_roles_fields(repo.syntax(None)))
        tpl = repo.get_template(template).template
        return run_input_variables(tpl.documents, fields=_roles_fields(repo.syntax(tpl)))

    @router.post("/sdd/templates/check", response_model=RulesCheckResult, responses=errors())
    async def check_template(body: RulesCheckRequest, space: SpaceQuery = None) -> RulesCheckResult:
        """규칙 검사(저장하지 않음, 깨진 규칙도 이슈로)."""
        svc = service()
        sc = svc.scope(space)
        issues = check_rules(
            body.rules,
            operators=sc.repository.operators,
            documents=body.documents,
            settings=svc.settings(),
        )
        return RulesCheckResult(issues=issues)

    # ------------------------------------------------------------ 스펙 목록·만들기

    @router.get("/sdd/specs", response_model=list[SpecSummary], responses=errors())
    async def list_specs(space: SpaceQuery = None) -> list[SpecSummary]:
        """스펙 목록 요약(문서 상태·작업 수·준비 수·지금 단계)."""
        return scope(space).repository.summaries()

    @router.post("/sdd/specs", response_model=SpecView, status_code=201, responses=errors())
    async def create_spec(body: SpecCreateRequest, space: SpaceQuery = None) -> JSONResponse:
        """만들기(같은 공간의 문서 틀 복사 또는 빈 스펙)."""
        svc = service()
        sc = svc.scope(space)
        stored = sc.repository.create(
            name=body.name,
            id=body.id,
            template=body.template,
            description=body.description or None,
        )
        svc.notify(sc.name, stored.id, version_hash=stored.version_hash)
        view = await svc.view(sc, stored.id)
        return _json(view, version=view.version_hash, status_code=201)

    @router.post("/sdd/specs/import", response_model=SpecView, status_code=201, responses=errors())
    async def import_spec(body: SpecImportRequest, space: SpaceQuery = None) -> JSONResponse:
        """폴더 안 마크다운 파일을 새 스펙 문서로 복사한다(원본과 연결하지 않음)."""
        svc = service()
        sc = svc.scope(space)
        files = _files_of(sc)
        got = import_documents(files, body.files, reserved=sc.reserved)
        stored = sc.repository.create(
            name=body.name, id=body.id, documents=got.documents, contents=got.contents
        )
        svc.notify(sc.name, stored.id, version_hash=stored.version_hash)
        view = await svc.view(sc, stored.id)
        return _json(view, version=view.version_hash, status_code=201)

    @router.get("/sdd/import/files", response_model=ImportFileListing, responses=errors())
    async def import_files(
        path: Annotated[str, Query(description="폴더 기준 상대 경로(빈 값 = 루트).")] = "",
        space: SpaceQuery = None,
    ) -> ImportFileListing:
        """가져오기용 폴더 안 파일 목록과 바로 아래 하위 폴더(재귀 없음 — 하위 폴더는 다시
        ``path``로 연다, 숨김·링크·예약 폴더 제외, 서버가 루프백일 때만, §6R.18 Q13·6R.20d)."""
        svc = service()
        if not svc.ports.loopback():
            raise SddRequestError(
                "서버가 루프백 주소가 아니어서 폴더 파일 목록을 보이지 않습니다.",
                code=ErrorCodes.FOLDERS_REMOTE_DISABLED,
            )
        sc = svc.scope(space)
        return list_import_files(
            _files_of(sc),
            path,
            extensions=svc.options.import_extensions,
            limit=svc.options.import_limit,
            reserved=sc.reserved,
        )

    # ------------------------------------------------------------ 스펙 하나

    @router.get("/sdd/specs/{spec_id}", response_model=SpecView, responses=errors())
    async def get_spec(spec_id: str, space: SpaceQuery = None) -> JSONResponse:
        """보기(정의·파싱 결과·풀린 라벨·규칙 이슈·작업 연결·자동 진행 상태) + ``ETag``."""
        svc = service()
        view = await svc.view(svc.scope(space), spec_id)
        return _json(view, version=view.version_hash)

    @router.put("/sdd/specs/{spec_id}", response_model=SpecView, responses=errors(412, 428))
    async def put_spec(
        spec_id: str, body: SpecDefinition, if_match: IfMatchHeader = None, space: SpaceQuery = None
    ) -> JSONResponse:
        """규칙·문서 목록 저장(``If-Match`` 필수 — 없으면 428)."""
        if body.id != spec_id:
            raise SddRequestError(
                "경로의 id와 본문의 스펙 id가 다릅니다.",
                details={"path_id": spec_id, "body_id": body.id},
            )
        svc = service()
        sc = svc.scope(space)
        raw = body.model_dump(mode="json", by_alias=True, exclude_unset=True)
        raw["kind"] = sc.repository.spec_kind
        stored = sc.repository.store.save(
            sc.repository.spec_kind,
            raw,
            expected_version=if_match_version(if_match),
            message="스펙 저장",
        )
        svc.notify(sc.name, spec_id, version_hash=stored.version_hash)
        view = await svc.view(sc, spec_id)
        return _json(view, version=view.version_hash)

    @router.delete("/sdd/specs/{spec_id}", status_code=204, responses=errors(412))
    async def delete_spec(
        spec_id: str, if_match: IfMatchHeader = None, space: SpaceQuery = None
    ) -> Response:
        """삭제(정의와 본문 파일, 실행 기록은 그대로)."""
        service().delete_spec(space, spec_id, expected_version=if_match_version(if_match))
        return Response(status_code=204)

    @router.post("/sdd/specs/{spec_id}/check", response_model=RulesCheckResult, responses=errors())
    async def check_spec(
        spec_id: str, body: RulesCheckRequest, space: SpaceQuery = None
    ) -> RulesCheckResult:
        """저장 전 규칙 검사(문서 목록을 주지 않으면 스펙의 문서). 실행 프로필 검사 포함."""
        svc = service()
        sc = svc.scope(space)
        loaded = sc.repository.load(spec_id)
        documents: list[Any] = list(body.documents) or [
            d.model_dump(mode="json", by_alias=True) for d in loaded.spec.documents
        ]
        issues = check_rules(
            body.rules,
            operators=sc.repository.operators,
            documents=documents,
            settings=svc.settings(),
        )
        ctx = svc.context(sc, loaded)
        issues.extend(await svc.profile_issues(ctx, svc.rules_profiles(body.rules)))
        return RulesCheckResult(issues=issues)

    # ------------------------------------------------------------ 문서 본문·상태

    def document_content(
        svc: SddService, document_id: str, file: str, data: bytes, content_hash: str
    ) -> SpecDocumentContent:
        text = data.decode("utf-8", errors="replace")
        return SpecDocumentContent(
            document_id=document_id,
            file=file,
            content=text,
            content_hash=content_hash,
            issues=svc.document_findings(text, document=document_id),
        )

    @router.get(
        "/sdd/specs/{spec_id}/documents/{doc_id}",
        response_model=SpecDocumentContent,
        responses=errors(),
    )
    async def get_document(spec_id: str, doc_id: str, space: SpaceQuery = None) -> JSONResponse:
        """본문 읽기 + ``ETag`` = 본문 해시. 파일이 없으면 404 ``sdd.document_missing``(만들지
        않음)."""
        svc = service()
        found = svc.scope(space).repository.read_document(spec_id, doc_id)
        body = document_content(svc, found.document_id, found.file, found.data, found.content_hash)
        return _json(body, version=found.content_hash)

    @router.put(
        "/sdd/specs/{spec_id}/documents/{doc_id}",
        response_model=SpecDocumentContent,
        responses=errors(412),
    )
    async def put_document(
        spec_id: str,
        doc_id: str,
        body: SpecDocumentWrite,
        if_match: IfMatchHeader = None,
        if_none_match: IfNoneMatchHeader = None,
        space: SpaceQuery = None,
    ) -> JSONResponse:
        """본문 쓰기(``If-Match`` = 본문 해시, ``If-None-Match: *`` = 없을 때만 만들기). 비밀 검사는
        사용자 설정 ``secret_scan``(warn = 저장 + 이슈, reject = 422)."""
        svc = service()
        sc = svc.scope(space)
        findings = svc.document_findings(body.content, document=doc_id)
        if findings and svc.secret_mode() == SCAN_REJECT:
            raise SecretRejectedError(findings)
        create_only = (if_none_match or "").strip() == "*"
        stored, written = sc.repository.write_document(
            spec_id,
            doc_id,
            body.content,
            expected_hash=if_match_version(if_match),
            create_only=create_only,
            by=_HUMAN,
        )
        svc.notify(sc.name, spec_id, version_hash=stored.version_hash)
        out = document_content(
            svc, written.document_id, written.file, written.data, written.content_hash
        )
        return _json(out, version=written.content_hash)

    @router.post(
        "/sdd/specs/{spec_id}/documents/{doc_id}/state",
        response_model=SpecView,
        responses=errors(412),
    )
    async def change_state(
        spec_id: str,
        doc_id: str,
        body: DocumentStateChange,
        if_match: IfMatchHeader = None,
        space: SpaceQuery = None,
    ) -> JSONResponse:
        """문서 상태 전환(전환 규칙 403 ``sdd.transition_denied``, 관문 422
        ``sdd.gate_blocked``)."""
        svc = service()
        sc = svc.scope(space)
        stored = sc.repository.change_document_state(
            spec_id,
            doc_id,
            body.to,
            by=_HUMAN,
            note=body.note,
            expected_version=if_match_version(if_match),
        )
        svc.notify(sc.name, spec_id, version_hash=stored.version_hash)
        view = await svc.view(sc, spec_id)
        return _json(view, version=view.version_hash)

    # ------------------------------------------------------------ 작업

    @router.get("/sdd/specs/{spec_id}/tasks", response_model=list[ParsedTask], responses=errors())
    async def list_tasks(
        spec_id: str,
        status: Annotated[
            list[str] | None, Query(description="작업 상태 id(여러 번 = 또는).")
        ] = None,
        stage: Annotated[list[str] | None, Query(description="단계 id(여러 번 = 또는).")] = None,
        field: Annotated[
            list[str] | None, Query(description="`<필드>=<값>`(여러 번 = 그리고).")
        ] = None,
        ready: Annotated[bool | None, Query(description="준비된 작업만(true)·아닌 것만.")] = None,
        q: Annotated[str | None, Query(description="키·id·제목에 든 글(대소문자 무시).")] = None,
        space: SpaceQuery = None,
    ) -> list[ParsedTask]:
        """작업 목록(작업 연결 포함, 서버 거르기)."""
        svc = service()
        sc = svc.scope(space)
        loaded = sc.repository.load(spec_id)
        picked = _filter_tasks(
            list(loaded.index.tasks),
            status=status or [],
            stage=stage or [],
            fields=_parse_fields(field or []),
            ready=ready,
            q=q,
        )
        return await svc.with_links(svc.context(sc, loaded), picked)

    @router.patch(
        "/sdd/specs/{spec_id}/tasks/{key}", response_model=TaskPatchResult, responses=errors()
    )
    async def patch_task(
        spec_id: str, key: str, body: TaskPatch, space: SpaceQuery = None
    ) -> TaskPatchResult:
        """작업 머리 줄 하나 고치기(줄 해시 충돌 409 ``sdd.task_changed``, 관문 422)."""
        svc = service()
        sc = svc.scope(space)
        result = sc.repository.patch_task(
            spec_id,
            key,
            expected_line_hash=body.expected_line_hash,
            status=body.status,
            fields=body.fields,
            by=_HUMAN,
        )
        svc.notify(sc.name, spec_id, version_hash=result.version_hash)
        return result

    @router.get("/sdd/specs/{spec_id}/plan", response_model=TaskPlan, responses=errors())
    async def get_plan(spec_id: str, space: SpaceQuery = None) -> TaskPlan:
        """계획(끝나지 않은 작업의 위상 층·병목·순환)."""
        loaded = scope(space).repository.load(spec_id)
        return plan(loaded.index, loaded.compiled)

    @router.get("/sdd/specs/{spec_id}/trace", response_model=TraceMatrix, responses=errors())
    async def get_trace(spec_id: str, space: SpaceQuery = None) -> TraceMatrix:
        """추적 표(요구 → 작업 → 연결 → 검증 결과, 빈 곳)."""
        svc = service()
        sc = svc.scope(space)
        loaded = sc.repository.load(spec_id)
        ctx = svc.context(sc, loaded)
        links = await svc.links(ctx, loaded.index.tasks)
        results = await svc.results(ctx)
        return trace(loaded.index, links, results, syntax=loaded.compiled)

    @router.get(
        "/sdd/specs/{spec_id}/variables", response_model=list[TemplateVariable], responses=errors()
    )
    async def spec_variables(spec_id: str, space: SpaceQuery = None) -> list[TemplateVariable]:
        """실행 입력 틀 변수 표(문서 목록 + 유효 문법 역할 필드)."""
        loaded = scope(space).repository.load(spec_id)
        return run_input_variables(loaded.spec.documents, fields=_roles_fields(loaded.syntax))

    @router.get("/sdd/specs/{spec_id}/syntax", response_model=EffectiveSyntax, responses=errors())
    async def spec_syntax(spec_id: str, space: SpaceQuery = None) -> EffectiveSyntax:
        """유효 작업 문법(값마다 출처 — 기본·설정·스펙)."""
        return scope(space).repository.load(spec_id).syntax

    # ------------------------------------------------------------ 작업 연동(X43)

    @router.get(
        "/sdd/specs/{spec_id}/tasks/{key}/actions",
        response_model=list[TaskAction],
        responses=errors(),
    )
    async def task_actions(spec_id: str, key: str, space: SpaceQuery = None) -> list[TaskAction]:
        """그 작업에서 고를 수 있는 동작(연동이 없으면 빈 목록)."""
        svc = service()
        sc = svc.scope(space)
        loaded, task = task_of(sc, spec_id, key)
        return await gather_actions(svc.integrations(), svc.context(sc, loaded), task)

    @router.post(
        "/sdd/specs/{spec_id}/tasks/{key}/actions/{integration}/{action}",
        response_model=TaskActionResult,
        responses=errors(),
    )
    async def invoke_action(
        spec_id: str,
        key: str,
        integration: str,
        action: str,
        body: TaskActionRequest | None = None,
        space: SpaceQuery = None,
    ) -> TaskActionResult:
        """동작 실행(연동에 위임). 모르는 연동은 409 ``sdd.action_unavailable``.

        연동이 ``blocked``·``failed``(오류 이슈)를 돌려주면 그 이슈 코드의 HTTP 오류로 바꾼다(관문
        422 ``sdd.gate_blocked`` ``details{gate_id, message, document_ids}``, 공간에 없는 팀 구성
        422 ``project.not_imported`` 등 — 6R.15). 한꺼번에 시작은 결과 목록에 그대로 싣는다."""
        svc = service()
        sc = svc.scope(space)
        target = next((i for i in svc.integrations() if i.id == integration), None)
        if target is None:
            raise _unavailable(integration, action)
        loaded, task = task_of(sc, spec_id, key)
        args = body.args if body is not None else {}
        result = await target.invoke(svc.context(sc, loaded), task, action, args)
        issue = result.issue
        if (
            result.status in (KnownTaskActionStatuses.BLOCKED, KnownTaskActionStatuses.FAILED)
            and issue is not None
            and issue.severity == "error"
        ):
            raise SddRequestError(issue.message, code=issue.code, details=issue.details)
        return result

    @router.post(
        "/sdd/specs/{spec_id}/bulk-actions", response_model=BulkActionsResult, responses=errors()
    )
    async def bulk_actions(
        spec_id: str, body: BulkActionsRequest, space: SpaceQuery = None
    ) -> BulkActionsResult:
        """여러 작업의 동작 합집합과 작업별 가능 목록(연동이 없으면 빈 목록, §6R.18 Q6)."""
        svc = service()
        sc = svc.scope(space)
        loaded = sc.repository.load(spec_id)
        ctx = svc.context(sc, loaded)
        integrations = svc.integrations()
        union: dict[tuple[str, str], TaskAction] = {}
        per_task: dict[str, list[TaskActionKey]] = {}
        for key in body.task_keys:
            task = find_task(loaded.index, key)
            if task is None:
                per_task[key] = []
                continue
            enabled: list[TaskActionKey] = []
            for item in await gather_actions(integrations, ctx, task):
                if not isinstance(item, TaskAction):
                    continue
                ident = (item.integration, item.id)
                known = union.get(ident)
                if known is None or (known.disabled is not None and item.disabled is None):
                    union[ident] = item
                if item.disabled is None:
                    enabled.append(TaskActionKey(integration=item.integration, id=item.id))
            per_task[key] = enabled
        return BulkActionsResult(actions=list(union.values()), per_task=per_task)

    @router.post(
        "/sdd/specs/{spec_id}/bulk-start", response_model=BulkStartResult, responses=errors()
    )
    async def bulk_start(
        spec_id: str, body: BulkStartRequest, space: SpaceQuery = None
    ) -> BulkStartResult:
        """고른 작업을 한 동작으로 시작(상한 ``max_bulk_start``, 안 맞는 작업은
        ``sdd.action_unavailable``)."""
        svc = service()
        limit = svc.options.max_bulk_start
        if len(body.task_keys) > limit:
            raise SddRequestError(
                f"한 번에 {limit}개까지 시작할 수 있습니다.",
                code=ErrorCodes.VALIDATION_FAILED,
                details={"limit": limit, "count": len(body.task_keys)},
            )
        sc = svc.scope(space)
        target = next((i for i in svc.integrations() if i.id == body.action.integration), None)
        if target is None:
            raise _unavailable(body.action.integration, body.action.id)
        loaded = sc.repository.load(spec_id)
        ctx = svc.context(sc, loaded)
        items: list[TaskActionResult] = []
        for key in body.task_keys:
            task = find_task(loaded.index, key)
            if task is None:
                items.append(_failed(key, ErrorCodes.SDD_NOT_FOUND, "작업을 찾을 수 없습니다."))
                continue
            offered = await target.actions(ctx, task)
            match = next((a for a in offered if a.id == body.action.id), None)
            if (
                match is not None
                and match.disabled is not None
                and match.disabled.code == ErrorCodes.SDD_GATE_BLOCKED
            ):
                # 관문이 막은 동작 = blocked(design §6R.1.5 "작업별 started·blocked·failed", 6R.15)
                items.append(
                    TaskActionResult(
                        task_key=key, status=KnownTaskActionStatuses.BLOCKED, issue=match.disabled
                    )
                )
                continue
            if match is None or match.disabled is not None:
                items.append(
                    _failed(
                        key, ErrorCodes.SDD_ACTION_UNAVAILABLE, "이 작업에서 쓸 수 없는 동작입니다."
                    )
                )
                continue
            try:
                items.append(await target.invoke(ctx, task, body.action.id, body.args))
            except Exception:
                items.append(_failed(key, ErrorCodes.INTERNAL, "동작을 시작하지 못했습니다."))
        return BulkStartResult(items=items)

    @router.post(
        "/sdd/specs/{spec_id}/automation/{op}",
        response_model=AutomationState,
        responses=errors(),
    )
    async def automation(spec_id: str, op: str, space: SpaceQuery = None) -> AutomationState:
        """자동 진행 멈춤(``stop``)·다시 시작(``resume``). 지원하는 연동이 없으면 404."""
        svc = service()
        control = svc.automation()
        if control is None or op not in (_STOP, _RESUME):
            raise SddRequestError(
                "자동 진행을 쓸 수 없습니다.", code=ErrorCodes.NOT_FOUND, details={"op": op}
            )
        sc = svc.scope(space)
        loaded = sc.repository.load(spec_id)
        auto = loaded.spec.rules.automation
        if op == _RESUME and (auto is None or not auto.enabled):
            raise SddRequestError(
                "스펙 규칙에서 자동 진행이 꺼져 있어 다시 시작할 수 없습니다.",
                code=ErrorCodes.SDD_ACTION_UNAVAILABLE,
                details={"op": op},
            )
        state = await control.control(svc.context(sc, loaded), op)
        svc.notify(sc.name, spec_id, automation=True)
        if state is None:
            raise SddRequestError(
                "자동 진행 상태가 없습니다.", code=ErrorCodes.NOT_FOUND, details={"op": op}
            )
        return state

    # ------------------------------------------------------------ 틀로 저장·내보내기

    @router.post(
        "/sdd/specs/{spec_id}/save-as-template",
        response_model=SaveAsTemplateResult,
        status_code=201,
        responses=errors(),
    )
    async def save_as_template(
        spec_id: str, body: SaveAsTemplateRequest, space: SpaceQuery = None
    ) -> SaveAsTemplateResult:
        """스펙 → 문서 틀(기본 라이브러리, 겹침 ``fail`` 409 ``sdd.template_exists``)."""
        svc = service()
        sc = svc.scope(space)
        dest, ref = svc.template_target(body.target)
        result = sc.repository.save_as_template(
            spec_id,
            name=body.name,
            id=body.id,
            include_content=body.include_content,
            on_conflict=body.on_conflict,
            target=dest,
        )
        return result.model_copy(update={"target": ref})

    @router.post("/sdd/specs/{spec_id}/export", response_model=SpecExportResult, responses=errors())
    async def export_spec(
        spec_id: str, body: SpecExportRequest, space: SpaceQuery = None
    ) -> SpecExportResult:
        """스펙 문서를 폴더 안 경로로 복사한다(저장소 폴더 안은 거부)."""
        sc = scope(space)
        files = _files_of(sc)
        spec = sc.repository.get(spec_id).spec
        contents = sc.repository.read_files(spec_id)
        return export_documents(
            spec, contents, files, body.to_dir, overwrite=body.overwrite, reserved=sc.reserved
        )

    # 문서 틀 하나(6R.20a): 고정 경로(/sdd/templates/variables 등) 뒤에 붙여 그쪽이 먼저 맞는다.
    router.include_router(build_template_router(service))
    return router


def _files_of(sc: SddScope) -> Any:
    if sc.files is None:
        raise SddRequestError(
            "이 공간은 폴더 파일에 접근할 수 없습니다.", code=ErrorCodes.FEATURE_UNAVAILABLE
        )
    return sc.files


def _unavailable(integration: str, action: str) -> SddRequestError:
    return SddRequestError(
        "이 작업에서 쓸 수 없는 동작입니다.",
        code=ErrorCodes.SDD_ACTION_UNAVAILABLE,
        details={"integration": integration, "action": action},
    )


def _failed(key: str, code: str, message: str) -> TaskActionResult:
    return TaskActionResult(
        task_key=key,
        status="failed",
        issue=Issue(severity="error", code=code, message=message),
    )


__all__ = ["build_router", "errors"]
