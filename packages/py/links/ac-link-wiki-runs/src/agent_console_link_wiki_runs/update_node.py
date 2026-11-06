"""노드 종류 ``wiki-update``(X2 entry point, design §7R.3·7R.17): LLM 없이 위키 페이지를 고친다.

앞 노드의 결과(입력 포트 ``in``)를 설정의 틀(``ac-text-template``)에 채워 위키 페이지 하나를 쓴다.
쓰기 방식은 위키 도구 ``write``와 같다(``ac-wiki`` ``compose_write`` — 통째로 바꾸기·덧붙이기·절
바꾸기, 새 페이지는 페이지 틀로). 쓰기 규칙·쓰기 검사(X50)·비밀 검사·기록·검색 색인은 위키
저장소가 그대로 적용한다.

- 위키 서비스: 노드 서비스 ``WIKI_UPDATE_SERVICE``(``runs.services``로 이 연동 모듈이 준다 —
  ``WikiNodeServices``). 공간 = 이 Run의 ``project_id``(자식 Run은 부모 값, 없으면 단독 공간).
- 쓴 주체: ``WikiAuthor{kind: system, label: 노드 id, node_id, node_path, run_id, root_run_id,
  graph_id}``(``system_author``).
- 서비스가 없으면(위키 모듈·이 연동이 꺼짐) 그래프 검증 경고 ``wiki.update_unavailable``(계약
  ``KnownIssueCodes.WIKI_UPDATE_UNAVAILABLE``), 실행하면
  노드는 ``skipped``(이유 = 같은 코드) + ``log.warning`` 1건이고 나가는 연결은 지나가지 않는다.
- 규칙 거부·비밀 거부·경로 오류·절 없음 등은 노드 ``failed``(``ErrorInfo.code`` = 저장소 예외 코드,
  ``details`` = 값 원문 없는 상세). 어느 쪽이든 RunEvent ``wiki.write``(계약 ``WikiEventPayload``,
  본문 없음)를 낸다 — 도구 호출과 같은 모양이라 로그 대응표가 그대로 받는다.
- 출력 ``out``: ``{wiki, path, sha256, version, created, changed}``(본문 없음).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_contracts import (
    ErrorCodes,
    ErrorInfo,
    Issue,
    KnownIssueCodes,
    KnownUiWidgets,
    NodeTypeDescriptor,
    PortDef,
    PortSpec,
    Slug,
    UiHints,
    x_ui,
)
from agent_console_contracts.wiki import (
    WIKI_EVENT_PREFIX,
    KnownWikiAuthorKinds,
    WikiAuthor,
    WikiEventPayload,
)
from agent_console_runtime import NodeContext, NodeResult, ServiceKey, ValidationContext
from agent_console_text_template import render_template
from agent_console_wiki import WikiError, WikiRepository, compose_write, wiki_failure

from .ports import WikiServiceLike
from .provider import event_payload, open_targets

__all__ = [
    "IN_PORT",
    "NODE_TYPE_ID",
    "OUT_PORT",
    "TEAM_ROLE",
    "WIKI_UPDATE_SERVICE",
    "WIKI_UPDATE_VARIABLES",
    "WikiNodeServices",
    "WikiUpdateCodes",
    "WikiUpdateConfig",
    "WikiUpdateNode",
    "render_values",
    "system_author",
]

_log = logging.getLogger(__name__)

NODE_TYPE_ID: Final = "wiki-update"
"""디스크립터 id(= entry point 이름 = 레지스트리 key)."""
IN_PORT: Final = "in"
"""입력 포트(앞 노드 결과). 기본 연결 종류의 받는 포트 이름과 같다."""
OUT_PORT: Final = "out"
"""출력 포트(쓴 결과 요약)."""
TEAM_ROLE: Final = "agent"
"""노드 역할(연결 규칙 근거). 에이전트 자리의 처리 단계라 기본 연결 종류(넘기기·답변)로 잇는다."""

WIKI_UPDATE_SERVICE: Final = ServiceKey[WikiServiceLike]("link_wiki_runs.wiki_service")
"""노드 서비스: 위키 서비스(``wiki.service`` 모양). ``WikiNodeServices``가 준다."""

WIKI_UPDATE_VARIABLES: Final[tuple[tuple[str, str], ...]] = (
    ("input", "앞 노드가 넘긴 값(글이 아니면 JSON)"),
    ("node_id", "이 노드 id"),
    ("run_id", "실행 id"),
    ("graph_id", "팀 구성 id"),
    ("date", "실행 시각의 날짜(YYYY-MM-DD)"),
    ("time", "실행 시각(HH:MM)"),
)
"""틀 변수(이름, 설명). 앞 노드 값이 객체면 그 최상위 키도 변수다(위 이름이 이긴다)."""

_TEMPLATE_FIELDS: Final = ("path", "content", "section", "title", "message")
_STATUS_OK: Final = "ok"
_WRITE_OP: Final = "write"

WriteMode = Literal["append", "section", "replace"]
"""쓰기 방식(위키 도구 ``write``의 ``mode``와 같은 어휘)."""


class WikiUpdateCodes:
    """이 노드가 내는 코드(``Issue.code``·``ErrorInfo.code``)."""

    UNAVAILABLE: Final = KnownIssueCodes.WIKI_UPDATE_UNAVAILABLE
    """위키 서비스가 없다(위키 모듈 또는 위키·실행 연동이 꺼짐). 계약 문서 상수
    ``KnownIssueCodes.WIKI_UPDATE_UNAVAILABLE``(0.14.1)의 별칭."""


def _variables() -> list[dict[str, str]]:
    return [{"name": n, "description": d} for n, d in WIKI_UPDATE_VARIABLES]


class WikiUpdateConfig(BaseModel):
    """앞 노드의 결과를 위키 페이지에 씁니다. 에이전트(LLM)를 부르지 않습니다."""

    model_config = ConfigDict(extra="forbid", title="위키 고치기")

    wiki: Slug = Field(
        title="위키",
        description="고칠 위키입니다. 실행하는 프로젝트의 위키 중에서 고릅니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="결과를 남길 위키를 고르세요.",
            example="project-notes",
            widget=KnownUiWidgets.WIKI_REF,
            order=1,
        ),
    )
    path: str = Field(
        min_length=1,
        title="페이지 경로",
        description="쓸 페이지 경로입니다(확장자 없음). 중괄호 변수로 실행마다 바꿀 수 있습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="날짜별 페이지처럼 경로를 바꾸려면 변수를 넣으세요.",
            example="log/{date}",
            variables=_variables(),
            order=2,
        ),
    )
    mode: WriteMode = Field(
        default="append",
        title="쓰는 방식",
        description="끝에 덧붙이기, 한 절만 바꾸기, 페이지 전체 바꾸기 중 하나입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="기존 내용을 지우지 않으려면 덧붙이기를 고르세요.",
            example="append",
            enum_labels={
                "append": "끝에 덧붙이기",
                "section": "절 바꾸기",
                "replace": "전체 바꾸기",
            },
            order=3,
        ),
    )
    section: str | None = Field(
        default=None,
        title="절 제목",
        description="절 바꾸기에서 바꿀 제목입니다. 그 제목 아래 내용만 바꿉니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="쓰는 방식이 절 바꾸기일 때 적으세요.",
            example="최근 결과",
            variables=_variables(),
            order=4,
        ),
    )
    content: str = Field(
        default="{input}\n",
        title="내용 틀",
        description="쓸 내용입니다. 중괄호 input은 앞 노드가 넘긴 값입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="앞 노드 결과 앞뒤에 제목이나 날짜를 붙이려면 고치세요.",
            example="## {date}\n{input}\n",
            variables=_variables(),
            order=5,
        ),
    )
    page_template: Slug | None = Field(
        default=None,
        title="새 페이지 틀",
        description=(
            "페이지가 없을 때 이 틀로 만들고 내용을 그 뒤에 붙입니다. 비우면 내용만 씁니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="새 페이지에 위키 규칙의 머리말·목차를 넣고 싶을 때 고르세요.",
            example="daily-log",
        ),
    )
    title: str | None = Field(
        default=None,
        title="새 페이지 제목",
        description="새 페이지 틀에 넘길 제목입니다. 비우면 틀이 정한 제목입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="새 페이지 틀을 쓰면서 제목을 정하고 싶을 때 적으세요.",
            example="{date} 기록",
            variables=_variables(),
        ),
    )
    message: str | None = Field(
        default=None,
        title="기록 메모",
        description="페이지 기록에 남길 한 줄입니다. 비우면 남기지 않습니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="기록 탭에서 이 노드가 쓴 변경을 알아보기 쉽게 하려면 적으세요.",
            example="실행 {run_id} 결과",
            variables=_variables(),
        ),
    )


_PORTS: Final = PortSpec(
    inputs=[PortDef(name=IN_PORT, label="받는 값")],
    outputs=[PortDef(name=OUT_PORT, label="쓴 결과")],
)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def render_values(
    value: Any,
    *,
    node_id: str = "",
    run_id: str = "",
    graph_id: str = "",
    at: float | None = None,
) -> dict[str, str]:
    """틀 변수 값(``WIKI_UPDATE_VARIABLES``). 값이 객체면 그 최상위 키도 변수다(글이 아니면 JSON).

    시각은 ``at``(유닉스 초)의 로컬 날짜·시각(없으면 빈 값).

    >>> v = render_values({"title": "A", "n": 2}, node_id="w", at=None)
    >>> v["title"], v["n"], v["input"], v["node_id"], v["date"]
    ('A', '2', '{"title": "A", "n": 2}', 'w', '')
    """
    values: dict[str, str] = {}
    if isinstance(value, Mapping):
        values.update({str(k): _as_text(v) for k, v in value.items()})
    stamp = datetime.fromtimestamp(at) if at is not None else None
    values.update(
        input=_as_text(value),
        node_id=node_id,
        run_id=run_id,
        graph_id=graph_id,
        date=stamp.strftime("%Y-%m-%d") if stamp else "",
        time=stamp.strftime("%H:%M") if stamp else "",
    )
    return values


def system_author(ctx: NodeContext) -> WikiAuthor:
    """노드 맥락 → 쓴 주체(``kind=system``, ``label`` = 노드 id, 실행·노드·팀 구성 id)."""
    return WikiAuthor(
        kind=KnownWikiAuthorKinds.SYSTEM,
        node_id=ctx.node.id,
        node_path=list(ctx.node_path),
        run_id=ctx.run.id,
        root_run_id=ctx.run.root_run_id or ctx.run.id,
        graph_id=ctx.graph.id,
        label=ctx.node.id,
    )


class WikiNodeServices:
    """``runs.services`` 항목: 노드 서비스 ``WIKI_UPDATE_SERVICE``(위키 서비스가 있을 때만).

    Args:
        service: 지금 위키 서비스(``wiki.service``)를 돌려주는 함수.
    """

    def __init__(self, service: Callable[[], WikiServiceLike | None]) -> None:
        self._service = service

    def services(self, env: Any = None) -> dict[ServiceKey[Any], Any]:
        """``{WIKI_UPDATE_SERVICE: 서비스}``(서비스가 없으면 빈 표)."""
        found = self._service()
        return {} if found is None else {WIKI_UPDATE_SERVICE: found}


def _unavailable_message() -> str:
    return "위키 기능이 꺼져 있어 위키 고치기 노드를 실행하지 않습니다"


class WikiUpdateNode:
    """노드 종류 ``wiki-update``(X2 구현). 결정적이라 이어 가기에서 다시 실행해도 된다."""

    descriptor = NodeTypeDescriptor(
        id=NODE_TYPE_ID,
        version=1,
        title="위키 고치기",
        description=(
            "앞 노드의 결과를 위키 페이지에 덧붙이거나 바꿉니다. 에이전트를 부르지 않습니다."
        ),
        category="위키",
        role=TEAM_ROLE,
        rerunnable=True,
        opens_session=False,
        config_schema=WikiUpdateConfig.model_json_schema(),
        ui_schema={
            "ui:order": [
                "wiki",
                "path",
                "mode",
                "section",
                "content",
                "page_template",
                "title",
                "message",
            ],
            "mode": {"ui:widget": "radio"},
            "content": {"ui:widget": "textarea"},
        },
        static_ports=_PORTS,
        ui_hints=UiHints(icon="W", color="#0f766e"),
    )

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        """고정 포트(입력 ``in``, 출력 ``out``)."""
        return _PORTS

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        """절 바꾸기인데 절 제목이 없으면 오류, 위키 서비스가 없으면 경고."""
        issues: list[Issue] = []
        if ctx.services.get(WIKI_UPDATE_SERVICE) is None:
            issues.append(
                Issue(
                    severity="warning",
                    code=WikiUpdateCodes.UNAVAILABLE,
                    message=_unavailable_message(),
                    path="/wiki",
                )
            )
        try:
            cfg = WikiUpdateConfig.model_validate(dict(config))
        except ValidationError:
            return issues  # 형식 오류는 엔진의 JSON Schema 검증이 보고한다
        if cfg.mode == "section" and not (cfg.section or "").strip():
            issues.append(
                Issue(
                    severity="error",
                    code=ErrorCodes.VALIDATION_FAILED,
                    message="절 바꾸기에는 절 제목이 필요합니다",
                    path="/section",
                )
            )
        return issues

    async def _event(self, ctx: NodeContext, payload: WikiEventPayload) -> None:
        await ctx.emit(f"{WIKI_EVENT_PREFIX}{payload.op}", event_payload(payload))

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        """틀을 채워 페이지를 쓴다(위 모듈 설명)."""
        try:
            cfg = WikiUpdateConfig.model_validate(dict(ctx.config))
        except ValidationError as exc:
            return NodeResult(
                status="failed",
                error=ErrorInfo(
                    code=ErrorCodes.VALIDATION_FAILED,
                    message=f"노드 설정이 맞지 않습니다: {exc.error_count()}개 오류",
                    details={"paths": sorted({"/".join(map(str, e["loc"])) for e in exc.errors()})},
                ),
            )
        service = ctx.services.get(WIKI_UPDATE_SERVICE)
        if service is None:
            message = _unavailable_message()
            await ctx.emit(
                "log.warning",
                {"message": message, "details": {"code": WikiUpdateCodes.UNAVAILABLE}},
            )
            return NodeResult(
                status="skipped",
                error=ErrorInfo(code=WikiUpdateCodes.UNAVAILABLE, message=message),
            )
        space = ctx.run.project_id or None
        values = render_values(
            inputs.get(IN_PORT),
            node_id=ctx.node.id,
            run_id=ctx.run.id,
            graph_id=ctx.graph.id,
            at=ctx.now(),
        )
        text = {
            name: render_template(raw, values) if isinstance(raw, str) else None
            for name, raw in ((f, getattr(cfg, f)) for f in _TEMPLATE_FIELDS)
        }
        path = (text["path"] or "").strip()
        targets, reason = open_targets(service, space)
        target = targets.get(cfg.wiki)
        if target is None:
            return await self._missing(ctx, cfg.wiki, path, space, reason)
        return await self._write(ctx, service, space, target.repository, cfg, path, text)

    async def _missing(
        self, ctx: NodeContext, wiki: str, path: str, space: str | None, reason: str | None
    ) -> NodeResult:
        details: dict[str, Any] = {"wiki": wiki}
        if space:
            details["project_id"] = space
        if reason:
            details["reason"] = reason
        await self._event(
            ctx,
            WikiEventPayload(
                op=_WRITE_OP,
                wiki=wiki,
                path=path or None,
                status="wiki_unavailable",
                code=KnownIssueCodes.WIKI_WIKI_UNAVAILABLE,
            ),
        )
        return NodeResult(
            status="failed",
            error=ErrorInfo(
                code=KnownIssueCodes.WIKI_WIKI_UNAVAILABLE,
                message="이 실행 공간에 그 위키가 없습니다",
                details=details,
            ),
        )

    async def _write(
        self,
        ctx: NodeContext,
        service: WikiServiceLike,
        space: str | None,
        repo: WikiRepository,
        cfg: WikiUpdateConfig,
        path: str,
        text: Mapping[str, str | None],
    ) -> NodeResult:
        author = system_author(ctx)
        started = time.perf_counter()

        def work() -> tuple[Any, int]:
            plan = compose_write(
                repo,
                path,
                content=text["content"],
                mode=cfg.mode,
                section=text["section"],
                template=cfg.page_template if repo.current(path) is None else None,
                title=text["title"],
            )
            outcome = repo.write(
                path,
                plan.content,
                author=author,
                if_hash=plan.if_hash,
                create_only=plan.create_only,
                message=text["message"] or None,
            )
            return outcome, len(plan.content.encode("utf-8", errors="surrogatepass"))

        try:
            outcome, size = await asyncio.to_thread(work)
        except (WikiError, ValueError) as exc:
            failure = wiki_failure(exc)
            await self._event(
                ctx,
                WikiEventPayload.model_validate(
                    {
                        "op": _WRITE_OP,
                        "wiki": cfg.wiki,
                        "path": path or None,
                        "status": failure.status,
                        "code": failure.code,
                        "rule_ids": list(failure.rule_ids),
                        "duration_ms": (time.perf_counter() - started) * 1000,
                    }
                ),
            )
            details = dict(getattr(exc, "details", None) or {})
            details.setdefault("wiki", cfg.wiki)
            return NodeResult(
                status="failed",
                error=ErrorInfo(code=failure.code, message=str(exc), details=details),
            )
        rule_ids = list(dict.fromkeys(i.rule_id for i in outcome.issues if i.rule_id))
        version = outcome.version.version if outcome.version is not None else None
        await self._event(
            ctx,
            WikiEventPayload(
                op=_WRITE_OP,
                wiki=cfg.wiki,
                path=outcome.path,
                status=_STATUS_OK,
                version=version,
                bytes=size,
                sha256=outcome.content_hash,
                rule_ids=rule_ids,
                duration_ms=(time.perf_counter() - started) * 1000,
            ),
        )
        for issue in outcome.issues:
            await ctx.emit(
                "log.warning",
                {"message": issue.message, "details": {"code": issue.code, "page": outcome.path}},
            )
        if outcome.changed:
            try:
                service.notify(space, cfg.wiki, [outcome.path])
            except Exception:
                _log.exception("위키 변경 알림 실패: %s", cfg.wiki)
        result = {
            "wiki": cfg.wiki,
            "path": outcome.path,
            "sha256": outcome.content_hash,
            "version": version,
            "created": outcome.created,
            "changed": outcome.changed,
        }
        return NodeResult(status="succeeded", outputs={OUT_PORT: result}, structured=result)
