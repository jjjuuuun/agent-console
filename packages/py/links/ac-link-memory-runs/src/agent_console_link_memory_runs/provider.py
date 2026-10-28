"""메모리 도구 공급자(X30 구현, design §5.7R.3): 묶음 칸의 접근 설정 → 플랫폼 도구 ``HostTool``.

- 칸(리소스 종류 데이터의 ``contributes`` 첫 칸)이 없으면 아무것도 하지 않는다(리소스를 붙이지 않은
  에이전트에게는 도구가 없다, opt-in).
- 메모리 서비스가 없으면 칸을 소비하지 않는다(백엔드가 적용하지 못한 칸 경고 R13.5가 그대로 난다).
- 칸에 쌓인 첨부(층 순서 = 먼 층 → 가까운 층)를 ``merge_access``로 합친다: 범위 종류마다 가까운
  층의 허용 동작, 나머지 키(기본 범위·도구 이름·머리 줄 등)도 가까운 층이 정한 값.
- 도구 호출마다 RunEvent ``memory.<op>``(payload = 계약 ``MemoryEventPayload``, 본문·검색어 원문
  없음)를 이 노드 이름으로 낸다. 도구 호출 id(``tool_use_id``)는 ``HostTool.call_handler``로 받는다.
- 범위 id는 맥락(``MemoryAccessContext``)에서 계산한다. ``project_id``는 루트 Run의 값이다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from pydantic import ValidationError

from agent_console_contracts import Issue
from agent_console_contracts.memory import (
    MemoryAccessConfig,
    MemoryAccessContext,
    MemoryEventPayload,
    MemoryScopeAccess,
)
from agent_console_memory import ToolSpec, ToolText, WriteBudget
from agent_console_nodes_core import ToolProvision, ToolProvisionContext
from agent_console_runtime import HostTool, HostToolResult

from .ports import MemoryServiceLike

__all__ = [
    "DEFAULT_PROVIDER_ID",
    "MemoryRunsCodes",
    "MemoryToolProvider",
    "access_context",
    "as_host_tool",
    "event_payload",
    "merge_access",
]

DEFAULT_PROVIDER_ID: Final = "link-memory-runs"
"""공급자 id(경고 details ``provider``)."""

_SCOPES: Final = "scopes"
_TOOLS: Final = "tools"


class MemoryRunsCodes:
    """이 연동이 내는 경고 코드(``log.warning`` details ``code``)."""

    ACCESS_INVALID: Final = "memory.access_invalid"
    """칸의 접근 설정을 합친 결과가 ``MemoryAccessConfig`` 형식이 아니다(도구를 주지 않는다)."""


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


def _scope_map(config: Mapping[str, Any]) -> dict[str, list[Any]]:
    """한 첨부 안의 범위 종류 → 허용 동작(같은 종류가 여러 번이면 합친다, ``allowed``와 같은 뜻)."""
    found: dict[str, list[Any]] = {}
    raw = config.get(_SCOPES)
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        return found
    for entry in raw:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("kind"), str):
            continue
        ops = entry.get("access")
        acc = found.setdefault(entry["kind"], [])
        if ops is None:  # 생략 = 계약 기본값
            ops = MemoryScopeAccess.model_fields["access"].get_default(call_default_factory=True)
        if isinstance(ops, Sequence) and not isinstance(ops, str | bytes):
            acc.extend(o for o in ops if o not in acc)
    return found


def merge_access(items: Any) -> tuple[MemoryAccessConfig | None, list[Issue]]:
    """칸에 쌓인 첨부들(먼 층 → 가까운 층)을 접근 설정 하나로 합친다.

    - 범위 종류마다 가장 가까운 층(뒤 항목)의 허용 동작을 쓴다. 순서는 가까운 층의 범위가 먼저.
    - ``tools``는 동작마다, 나머지 최상위 키는 키마다 가장 가까운 층이 정한 값을 쓴다.
    - 첨부가 없으면 ``(None, [])``. 합친 결과가 형식에 맞지 않으면 ``(None, [경고])``.

    >>> far = {"config": {"scopes": [{"kind": "team", "access": ["read"]},
    ...                              {"kind": "shared", "access": ["read"]}],
    ...                   "tools": {"read": {"name": "team_read", "description": "d"}}}}
    >>> near = {"config": {"scopes": [{"kind": "team", "access": ["read", "write"]}]}}
    >>> access, issues = merge_access([far, near])
    >>> [(s.kind, s.access) for s in access.scopes], access.tools.read.name, issues
    ([('team', ['read', 'write']), ('shared', ['read'])], 'team_read', [])
    """
    configs = _configs(items)
    if not configs:
        return None, []
    merged: dict[str, Any] = {}
    tools: dict[str, Any] = {}
    scopes: dict[str, list[Any]] = {}
    for config in reversed(configs):  # 가까운 층부터: 먼저 정한 값이 이긴다
        for key, value in config.items():
            if key == _SCOPES:
                continue
            if key == _TOOLS and isinstance(value, Mapping):
                for op, tool in value.items():
                    tools.setdefault(str(op), tool)
                continue
            merged.setdefault(str(key), value)
        for kind, ops in _scope_map(config).items():
            scopes.setdefault(kind, ops)
    merged[_SCOPES] = [{"kind": kind, "access": ops} for kind, ops in scopes.items()]
    if tools:
        merged[_TOOLS] = tools
    try:
        return MemoryAccessConfig.model_validate(merged), []
    except ValidationError as exc:
        where = sorted({"/" + "/".join(str(p) for p in err["loc"]) for err in exc.errors()})
        return None, [
            Issue(
                severity="warning",
                code=MemoryRunsCodes.ACCESS_INVALID,
                message=(
                    "메모리 접근 설정을 합친 결과가 형식에 맞지 않아 메모리 도구를 주지 않습니다"
                ),
                details={"paths": where},
            )
        ]


def access_context(
    ctx: ToolProvisionContext, *, project_id: str | None = None, root_graph_id: str | None = None
) -> MemoryAccessContext:
    """노드 맥락 → 메모리 접근 맥락(범위 id 틀이 읽는 값, 없는 값은 빈 문자열).

    Args:
        ctx: 공급자가 받은 노드 맥락(``graph_id``는 이 노드를 실행한 Run의 팀 구성).
        project_id: 루트 Run의 프로젝트 id.
        root_graph_id: 루트 Run의 팀 구성 id. 없으면 루트 Run 노드는 ``ctx.graph_id``, 자식 Run
            노드는 빈 값.
    """
    if root_graph_id is None:
        root_graph_id = ctx.graph_id if ctx.run_id == ctx.root_run_id else ""
    return MemoryAccessContext(
        run_id=ctx.run_id,
        root_run_id=ctx.root_run_id,
        graph_id=ctx.graph_id,
        root_graph_id=root_graph_id,
        project_id=project_id or "",
        agent_id=ctx.agent_id or "",
        node_id=ctx.node_id,
        node_path=list(ctx.node_path),
    )


def event_payload(payload: MemoryEventPayload) -> dict[str, Any]:
    """RunEvent payload(JSON, 빈 값 생략). 계약 모델이라 본문·검색어 원문 필드가 없다."""
    return payload.model_dump(mode="json", exclude_none=True)


def as_host_tool(spec: ToolSpec) -> HostTool:
    """메모리 도구 스펙 → 플랫폼 도구(호출 id는 ``call_handler``로 받아 이벤트에 싣는다)."""

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


class MemoryToolProvider:
    """X30 ``ToolProvider``: 메모리 칸이 있는 노드에 메모리 도구를 준다.

    Args:
        service: 지금 메모리 서비스를 돌려주는 함수(None이면 칸을 소비하지 않는다).
        slot: 읽을 묶음 칸 이름(리소스 종류 데이터의 ``contributes`` 첫 칸).
        id: 공급자 id(경고 details ``provider``).
        project_id: 루트 Run의 프로젝트 id(범위 틀 ``{/project_id}``).
        root_graph_id: 루트 Run의 팀 구성 id(범위 틀 ``{/root_graph_id}``).
        write_budget: 실행 하나의 쓰기 한도(이 공급자가 만든 도구 묶음이 모두 함께 쓴다).
        text: 도구 문구(없으면 ``ac-memory`` 기본 데이터).
    """

    def __init__(
        self,
        service: Callable[[], MemoryServiceLike | None],
        *,
        slot: str,
        id: str = DEFAULT_PROVIDER_ID,
        project_id: str | None = None,
        root_graph_id: str | None = None,
        write_budget: WriteBudget | None = None,
        text: ToolText | None = None,
    ) -> None:
        self.id = id
        self.slot = slot
        self.project_id = project_id
        self.root_graph_id = root_graph_id
        self.write_budget = write_budget
        self._service = service
        self._text = text

    def provide(self, ctx: ToolProvisionContext) -> ToolProvision:
        """이 노드의 메모리 도구(칸이 없거나 서비스가 없으면 빈 결과)."""
        if self.slot not in ctx.bundle.slots:
            return ToolProvision()
        service = self._service()
        if service is None:
            return ToolProvision()
        consumed = frozenset({self.slot})
        access, issues = merge_access(ctx.bundle.slots[self.slot])
        if access is None:
            return ToolProvision(consumed_slots=consumed, warnings=tuple(issues))
        context = access_context(ctx, project_id=self.project_id, root_graph_id=self.root_graph_id)

        async def on_event(event_type: str, payload: MemoryEventPayload) -> None:
            await ctx.emit(event_type, event_payload(payload))

        toolkit = service.toolkit(
            access, context, on_event=on_event, write_budget=self.write_budget, text=self._text
        )
        tools = tuple(as_host_tool(spec) for spec in toolkit.specs())
        return ToolProvision(host_tools=tools, consumed_slots=consumed, warnings=tuple(issues))
