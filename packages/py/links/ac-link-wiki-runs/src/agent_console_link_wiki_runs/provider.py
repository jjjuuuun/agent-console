"""위키 도구 공급자(X30 구현, design §7R.1.4·§7R.3): 묶음 칸의 접근 설정 → 플랫폼 도구 + 지침.

- 칸(리소스 종류 데이터의 ``contributes`` 첫 칸)이 없으면 아무것도 하지 않는다(리소스를 붙이지 않은
  에이전트에게는 도구도 지침도 없다, opt-in).
- 위키 서비스가 없으면 칸을 소비하지 않는다(백엔드가 적용하지 못한 칸 경고 R13.5가 그대로 난다).
- 칸에 쌓인 첨부(층 순서 = 먼 층 → 가까운 층)를 ``merge_access``로 합친다: 위키마다 가까운 층의
  허용 동작, 나머지 키(기본 위키·도구 이름·경로 안내·머리 줄 등)도 가까운 층이 정한 값(메모리
  ``merge_access``와 같은 규칙).
- 위키는 **그 실행 공간의 위키만**(루트 Run의 ``project_id`` → 그 프로젝트 공간, 없으면 단독 공간,
  ``wiki.service`` ``tool_targets``). 접근 설정에 있는데 공간에 없는 위키가 있으면 경고 1건
  (``wiki.wiki_unavailable``)을 내고 도구는 그대로 준다(그 위키 호출은 사유 코드로 실패).
- 지침(``ToolProvision.instructions``) = 도구 묶음 ``instructions()``(합친 규칙 지침 + 경로 안내).
- 쓴 주체 = ``WikiAuthor{kind: agent, agent_id, node_id, node_path, run_id, root_run_id, graph_id,
  label}``. ``label``은 실행 시점 에이전트 정의 ``name``(없으면 null) — 기록에 그대로 남는다.
- 도구 호출마다 RunEvent ``wiki.<op>``(payload = 계약 ``WikiEventPayload``, 본문·검색어 원문 없음)를
  이 노드 이름으로 낸다. 성공한 쓰기·옮기기·지우기 뒤에는 ``wiki.service.notify``(WS
  ``wiki.changed``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from pydantic import ValidationError

from agent_console_contracts import Agent, Issue, KnownIssueCodes
from agent_console_contracts.wiki import (
    KnownWikiAuthorKinds,
    WikiAccessConfig,
    WikiAccessEntry,
    WikiAuthor,
    WikiEventPayload,
)
from agent_console_nodes_core import ToolProvision, ToolProvisionContext
from agent_console_runtime import HostTool, HostToolResult
from agent_console_wiki import (
    WikiToolkit,
    WikiToolSpec,
    WikiToolTarget,
    WikiToolText,
    WikiWriteBudget,
)

from .ports import WikiServiceLike

__all__ = [
    "DEFAULT_PROVIDER_ID",
    "AgentLookup",
    "WikiRunsCodes",
    "WikiToolProvider",
    "agent_label",
    "as_host_tool",
    "author_for",
    "event_payload",
    "merge_access",
    "open_targets",
    "unavailable_issue",
]

_log = logging.getLogger(__name__)

DEFAULT_PROVIDER_ID: Final = "link-wiki-runs"
"""공급자 id(경고 details ``provider``, 지침 출처 ``tool_provider:<id>``)."""

_WIKIS: Final = "wikis"
_TOOLS: Final = "tools"
_MUTATING: Final = frozenset({"write", "move", "delete"})
_DELETE: Final = "delete"
_OK: Final = "ok"

type AgentLookup = Callable[[str], Agent | None]
"""에이전트 정의 id → 정의(노드 서비스 ``AGENT_LOOKUP`` 모양)."""


class WikiRunsCodes:
    """이 연동이 내는 경고 코드(``log.warning`` details ``code``)."""

    ACCESS_INVALID: Final = "wiki.access_invalid"
    """칸의 접근 설정을 합친 결과가 ``WikiAccessConfig`` 형식이 아니다(도구를 주지 않는다)."""


# ---------------------------------------------------------------- 층 합치기


def _configs(items: Any) -> list[Mapping[str, Any]]:
    """칸 값(항목 목록) → 접근 설정 원문 목록(층 순서). 항목 모양이 아니면 건너뛴다."""
    if not isinstance(items, Sequence) or isinstance(items, str | bytes):
        return []
    out: list[Mapping[str, Any]] = []
    for item in items:
        if isinstance(item, Mapping):
            config = item.get("config")
            if isinstance(config, Mapping):
                out.append(config)
    return out


def _wiki_map(config: Mapping[str, Any]) -> dict[str, list[Any]]:
    """한 첨부 안의 위키 id → 허용 동작(같은 위키가 여러 번이면 합친다 — 도구 묶음과 같은 뜻)."""
    found: dict[str, list[Any]] = {}
    raw = config.get(_WIKIS)
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        return found
    for entry in raw:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("wiki"), str):
            continue
        ops = entry.get("access")
        acc = found.setdefault(entry["wiki"], [])
        if ops is None:  # 생략 = 계약 기본값
            ops = WikiAccessEntry.model_fields["access"].get_default(call_default_factory=True)
        if isinstance(ops, Sequence) and not isinstance(ops, str | bytes):
            acc.extend(o for o in ops if o not in acc)
    return found


def merge_access(items: Any) -> tuple[WikiAccessConfig | None, list[Issue]]:
    """칸에 쌓인 첨부들(먼 층 → 가까운 층)을 접근 설정 하나로 합친다.

    - 위키마다 가장 가까운 층(뒤 항목)의 허용 동작을 쓴다. 순서는 가까운 층의 위키가 먼저.
    - ``tools``는 동작마다, 나머지 최상위 키는 키마다 가장 가까운 층이 정한 값을 쓴다.
    - 첨부가 없으면 ``(None, [])``. 합친 결과가 형식에 맞지 않으면 ``(None, [경고])``.

    >>> far = {"config": {"wikis": [{"wiki": "notes", "access": ["read"]},
    ...                             {"wiki": "specs", "access": ["read"]}],
    ...                   "tools": {"read": {"name": "notes_read", "description": "d"}}}}
    >>> near = {"config": {"wikis": [{"wiki": "notes", "access": ["read", "write"]}]}}
    >>> access, issues = merge_access([far, near])
    >>> [(w.wiki, w.access) for w in access.wikis], access.tools.read.name, issues
    ([('notes', ['read', 'write']), ('specs', ['read'])], 'notes_read', [])
    """
    configs = _configs(items)
    if not configs:
        return None, []
    merged: dict[str, Any] = {}
    tools: dict[str, Any] = {}
    wikis: dict[str, list[Any]] = {}
    for config in reversed(configs):  # 가까운 층부터: 먼저 정한 값이 이긴다
        for key, value in config.items():
            if key == _WIKIS:
                continue
            if key == _TOOLS and isinstance(value, Mapping):
                for op, tool in value.items():
                    tools.setdefault(str(op), tool)
                continue
            merged.setdefault(str(key), value)
        for wiki, ops in _wiki_map(config).items():
            wikis.setdefault(wiki, ops)
    merged[_WIKIS] = [{"wiki": wiki, "access": ops} for wiki, ops in wikis.items()]
    if tools:
        merged[_TOOLS] = tools
    try:
        return WikiAccessConfig.model_validate(merged), []
    except ValidationError as exc:
        where = sorted({"/" + "/".join(str(p) for p in err["loc"]) for err in exc.errors()})
        return None, [
            Issue(
                severity="warning",
                code=WikiRunsCodes.ACCESS_INVALID,
                message="위키 접근 설정을 합친 결과가 형식에 맞지 않아 위키 도구를 주지 않습니다",
                details={"paths": where},
            )
        ]


# ---------------------------------------------------------------- 맥락·결과


def agent_label(lookup: AgentLookup | None, agent_id: str | None) -> str | None:
    """실행 시점 에이전트 정의 이름(없거나 읽지 못하면 None)."""
    if lookup is None or not agent_id:
        return None
    try:
        agent = lookup(agent_id)
    except Exception:  # 정의 읽기 실패는 이름 없이 쓴다
        return None
    name = getattr(agent, "name", None)
    return name if isinstance(name, str) and name else None


def author_for(ctx: ToolProvisionContext, *, label: str | None = None) -> WikiAuthor:
    """노드 맥락 → 쓴 주체(``kind=agent``, 실행·노드·팀 구성 id, 기록 시점 이름)."""
    return WikiAuthor(
        kind=KnownWikiAuthorKinds.AGENT,
        agent_id=ctx.agent_id,
        node_id=ctx.node_id,
        node_path=list(ctx.node_path),
        run_id=ctx.run_id,
        root_run_id=ctx.root_run_id,
        graph_id=ctx.graph_id,
        label=label,
    )


def event_payload(payload: WikiEventPayload) -> dict[str, Any]:
    """RunEvent payload(JSON, 빈 값 생략). 계약 모델이라 본문·검색어 원문 필드가 없다."""
    return payload.model_dump(mode="json", exclude_none=True)


def as_host_tool(spec: WikiToolSpec) -> HostTool:
    """위키 도구 스펙 → 플랫폼 도구(호출 id는 ``call_handler``로 받아 이벤트에 싣는다)."""

    async def call(arguments: dict[str, Any], tool_use_id: str | None) -> HostToolResult:
        outcome = await spec.call(arguments, tool_use_id)
        return HostToolResult(text=outcome.text, is_error=outcome.is_error)

    async def handler(arguments: dict[str, Any]) -> HostToolResult:
        return await call(arguments, None)

    return HostTool(
        name=spec.name,
        description=spec.description,
        input_schema=dict(spec.input_schema),
        handler=handler,
        call_handler=call,
    )


def unavailable_issue(
    wikis: Sequence[str], *, project_id: str | None, reason: str | None = None
) -> Issue:
    """리소스가 가리킨 위키가 이 실행 공간에 없다는 경고(``wiki.wiki_unavailable``)."""
    details: dict[str, Any] = {"wikis": list(wikis)}
    if project_id:
        details["project_id"] = project_id
    if reason:
        details["reason"] = reason
    return Issue(
        severity="warning",
        code=KnownIssueCodes.WIKI_WIKI_UNAVAILABLE,
        message=(
            "리소스가 가리킨 위키 중 이 실행 공간에 없는 위키가 있어 그 위키의 도구 호출은 "
            "실패합니다"
        ),
        details=details,
    )


def open_targets(
    service: WikiServiceLike, space: str | None
) -> tuple[dict[str, WikiToolTarget], str | None]:
    """그 공간의 위키 → 도구 대상. 공간을 열 수 없으면 ``({}, 사유)``.

    사유 = 예외 ``code`` 또는 예외 이름. 라이브러리나 다른 공간으로 대신하지 않는다.
    """
    try:
        return dict(service.tool_targets(space)), None
    except Exception as exc:
        code = getattr(exc, "code", None)
        reason = code if isinstance(code, str) and code else type(exc).__name__
        _log.info("위키 공간을 열지 못함: %s (%s)", space, reason)
        return {}, reason


class WikiToolProvider:
    """X30 ``ToolProvider``: 위키 칸이 있는 노드에 위키 도구와 지침을 준다.

    Args:
        service: 지금 위키 서비스를 돌려주는 함수(None이면 칸을 소비하지 않는다).
        slot: 읽을 묶음 칸 이름(리소스 종류 데이터의 ``contributes`` 첫 칸).
        id: 공급자 id(경고 details ``provider``, 지침 출처).
        project_id: 루트 Run의 프로젝트 id = 위키 공간 이름(없으면 단독 공간).
        agent_lookup: 에이전트 정의 읽기(쓴 주체 ``label``). 없으면 ``label`` 없음.
        write_budget: 실행 하나의 쓰기 한도(이 공급자가 만든 도구 묶음이 모두 함께 쓴다).
        text: 도구 문구(없으면 ``ac-wiki`` 기본 데이터).
    """

    def __init__(
        self,
        service: Callable[[], WikiServiceLike | None],
        *,
        slot: str,
        id: str = DEFAULT_PROVIDER_ID,
        project_id: str | None = None,
        agent_lookup: AgentLookup | None = None,
        write_budget: WikiWriteBudget | None = None,
        text: WikiToolText | None = None,
    ) -> None:
        self.id = id
        self.slot = slot
        self.project_id = project_id or None
        self.agent_lookup = agent_lookup
        self.write_budget = write_budget
        self._service = service
        self._text = text

    def _notify(self, service: WikiServiceLike, payload: WikiEventPayload) -> None:
        """성공한 쓰기·옮기기·지우기 → ``notify``(실패는 기록만, 도구 결과를 막지 않는다)."""
        if payload.op not in _MUTATING or payload.status != _OK or not payload.wiki:
            return
        paths = [p for p in (payload.path, payload.to) if p]
        try:
            service.notify(self.project_id, payload.wiki, paths, deleted=payload.op == _DELETE)
        except Exception:
            _log.exception("위키 변경 알림 실패: %s", payload.wiki)

    def provide(self, ctx: ToolProvisionContext) -> ToolProvision:
        """이 노드의 위키 도구·지침(칸이 없거나 서비스가 없으면 빈 결과)."""
        if self.slot not in ctx.bundle.slots:
            return ToolProvision()
        service = self._service()
        if service is None:
            return ToolProvision()
        consumed = frozenset({self.slot})
        access, issues = merge_access(ctx.bundle.slots[self.slot])
        if access is None:
            return ToolProvision(consumed_slots=consumed, warnings=tuple(issues))
        targets, reason = open_targets(service, self.project_id)
        author = author_for(ctx, label=agent_label(self.agent_lookup, ctx.agent_id))

        async def on_event(event_type: str, payload: WikiEventPayload) -> None:
            await ctx.emit(event_type, event_payload(payload))
            self._notify(service, payload)

        kit = WikiToolkit(
            targets,
            access=access,
            author=author,
            text=self._text,
            on_event=on_event,
            write_budget=self.write_budget,
        )
        missing = kit.unavailable()
        if missing:
            issues = [
                *issues,
                unavailable_issue(missing, project_id=self.project_id, reason=reason),
            ]
        return ToolProvision(
            host_tools=tuple(as_host_tool(spec) for spec in kit.specs()),
            consumed_slots=consumed,
            warnings=tuple(issues),
            instructions=tuple(kit.instructions()),
        )
