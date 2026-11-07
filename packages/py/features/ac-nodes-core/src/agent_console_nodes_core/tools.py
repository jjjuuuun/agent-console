"""에이전트 도구 공급자(X30, design §5.7R.3): 다른 기능이 agent 노드의 모델에게 도구를 주는 길.

agent 노드는 도구가 무엇인지 모른다. Run마다 서비스 `TOOL_PROVIDERS`(공급자 목록)로 들어온
공급자에게 이 노드의 맥락(`ToolProvisionContext`)을 주고, 공급자가 돌려준 `ToolProvision`
(플랫폼 도구 `HostTool`·소비한 묶음 칸·경고)을 요청에 붙인다. 백엔드는
`capabilities.host_tools`로 받은 도구를 모델에게 그대로 준다(X3).

agent 노드 순서(`AgentNode`):
    1. 묶음 계산 → 공급자마다 `provide`(예외는 `tools.provider_failed` 경고 후 건너뜀).
    2. 공급 도구를 위임 기여 도구 뒤에 붙인다. 이름이 겹치면 뒤의 것(공급 도구)을 빼고
       `tools.duplicate_name` 경고.
    3. 소비된 칸을 백엔드 요청 묶음에서 뺀다(그 칸의 "백엔드가 받지 않는 칸" 경고도 뺀다).
    4. 백엔드가 `host_tools` 능력이 없으면 공급 도구를 빼고 `tools.backend_capability_missing`
       경고(실행은 계속).
    5. 공급자 지침(`ToolProvision.instructions`, 7R.5)을 요청 묶음 칸 `instructions` 끝에 공급자
       순서대로 붙인다(유효 시스템 지침 = 에이전트 지침 + 리소스 지침 뒤). 출처는
       `tool_provider:<id>`로 `agent.context_prepared`에 보인다. 백엔드가 그 칸을 받지 않으면
       지침을 빼고 `tools.instructions_unsupported` 경고.

공급자가 없으면(서비스가 없거나 빈 목록) 기존 실행과 같다.

공개 API:
    - ``ToolProvider``(프로토콜), ``ToolProvisionContext``, ``ToolProvision``
    - ``provide_tools``(공급자 여럿 부르기·격리·합치기 → ``MergedToolProvision``),
      ``drop_taken``(이미 쓴 이름 빼기)
    - 지침: ``attach_instructions``(묶음 칸 끝에 붙이기), ``instruction_source``(출처 ref),
      ``INSTRUCTION_SOURCE_PREFIX``
    - 경고 코드 ``ToolProviderCodes``
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, runtime_checkable

from agent_console_contracts import (
    BackendCapabilities,
    BundleSource,
    Issue,
    KnownResourceSlots,
    ResourceBundle,
)
from agent_console_runtime import CancelToken, HostTool

__all__ = [
    "INSTRUCTION_SOURCE_PREFIX",
    "MergedToolProvision",
    "ToolEmit",
    "ToolProvider",
    "ToolProviderCodes",
    "ToolProvision",
    "ToolProvisionContext",
    "attach_instructions",
    "drop_taken",
    "instruction_source",
    "provide_tools",
]


class ToolProviderCodes:
    """X30 경로가 내는 `Issue.code`(`log.warning` details `code`) 값."""

    PROVIDER_FAILED: Final = "tools.provider_failed"
    """공급자 `provide`가 예외를 던졌거나 `ToolProvision`이 아닌 값을 돌려줬다(건너뜀)."""
    DUPLICATE_NAME: Final = "tools.duplicate_name"
    """공급 도구 이름이 이미 쓰인 이름(위임 도구·앞선 공급 도구)과 겹쳐 뺐다."""
    BACKEND_CAPABILITY_MISSING: Final = "tools.backend_capability_missing"
    """백엔드가 `capabilities.host_tools`를 선언하지 않아 공급 도구를 뺐다(실행은 계속)."""
    INSTRUCTIONS_UNSUPPORTED: Final = "tools.instructions_unsupported"
    """백엔드가 지침 칸(`capabilities.resource_slots`의 `instructions`)을 받지 않아 공급자 지침을
    뺐다(도구는 그대로, 실행은 계속). 공급자마다 하나, details `provider`·`backend`."""


INSTRUCTION_SOURCE_PREFIX: Final = "tool_provider:"
"""공급자 지침의 묶음 출처(`BundleSource.ref`) 앞말. ref = 앞말 + 공급자 id."""


def instruction_source(provider_id: str) -> str:
    """공급자 id → 지침 출처 ref(`tool_provider:<id>`). `agent.context_prepared` 항목 id가 된다."""
    return f"{INSTRUCTION_SOURCE_PREFIX}{provider_id}"


type ToolEmit = Callable[[str, Mapping[str, Any]], Awaitable[None]]
"""(이벤트 type, payload) → 이 노드 이름으로 RunEvent를 낸다(엔진 예약 type은 안 됨)."""


@dataclass(frozen=True)
class ToolProvisionContext:
    """공급자가 받는 이 노드 실행 맥락(런타임 전용, 계약 아님).

    Attributes:
        run_id: 이 Run id.
        root_run_id: 맨 위 Run id(루트면 `run_id`와 같다).
        graph_id: 실행 중인 팀 구성 id(자식 Run이면 자식 팀).
        node_id: 이 노드 id.
        node_path: 이벤트 `node_path`(위임자가 부른 노드면 위임자 경로 포함).
        agent_id: 이 자리의 에이전트 정의 id(없으면 None).
        call: 호출 회차(위임자가 부른 NodeRun이면 0부터, 스케줄 실행은 0).
        iteration: 반복 회차(0부터).
        bundle: 이 노드의 유효 실행 묶음(칸 이름 → 값, 출처). 첨부가 없으면 빈 묶음.
        backend_capabilities: 이 노드가 부를 백엔드의 능력.
        emit: 이 노드 이름으로 RunEvent를 낸다(도구 호출마다 써도 된다).
        cancel: Run 취소 토큰.
    """

    run_id: str
    root_run_id: str
    graph_id: str
    node_id: str
    node_path: Sequence[str]
    agent_id: str | None
    call: int | None
    iteration: int
    bundle: ResourceBundle
    backend_capabilities: BackendCapabilities
    emit: ToolEmit
    cancel: CancelToken


@dataclass(frozen=True)
class ToolProvision:
    """공급자 한 번의 결과.

    Attributes:
        host_tools: 모델에게 줄 도구(이름은 요청 안에서 유일해야 한다, 겹치면 빠진다).
        consumed_slots: 이 공급자가 읽어 처리한 묶음 칸. 백엔드 요청 묶음에서 빠진다.
        warnings: 이 노드의 `log.warning`으로 낼 이슈(details에 공급자 id가 붙는다).
        instructions: 모델에게 줄 지침 글(7R.5). agent 노드가 유효 시스템 지침 뒤에 이 순서로
            붙인다(공급자 id 머리는 붙이지 않는다). 빈 글은 빠진다. 기본 빈 값 = 지침 없음.
    """

    host_tools: Sequence[HostTool] = ()
    consumed_slots: frozenset[str] = field(default_factory=frozenset)
    warnings: Sequence[Issue] = ()
    instructions: Sequence[str] = ()


@dataclass(frozen=True)
class MergedToolProvision(ToolProvision):
    """`provide_tools`가 합친 결과. `instructions`와 같은 길이로 각 지침을 낸 공급자 id를 둔다.

    Attributes:
        instruction_providers: `instructions[i]`를 낸 공급자 id.
    """

    instruction_providers: Sequence[str] = ()

    def sourced_instructions(self) -> list[tuple[str, str]]:
        """(공급자 id, 지침 글) 목록(순서 그대로)."""
        return list(zip(self.instruction_providers, self.instructions, strict=True))


@runtime_checkable
class ToolProvider(Protocol):
    """agent 노드 실행마다 도구를 주는 공급자.

    `id`는 경고·이벤트에 쓰는 이름(사용자 도메인 아님). `provide`는 백엔드를 부르기 전에 노드마다
    한 번 불린다. 동기 함수이며 무거운 일(저장소 조회 등)은 도구 핸들러가 호출 때 한다.
    """

    id: str

    def provide(self, ctx: ToolProvisionContext) -> ToolProvision: ...


def _warning(code: str, message: str, **details: Any) -> Issue:
    return Issue(severity="warning", code=code, message=message, details=details)


def _provider_id(provider: object) -> str:
    value = getattr(provider, "id", None)
    return value if isinstance(value, str) and value else type(provider).__name__


def provide_tools(
    providers: Iterable[ToolProvider], ctx: ToolProvisionContext
) -> MergedToolProvision:
    """공급자들을 순서대로 불러 결과를 합친다(공급자 하나의 실패가 다른 공급자를 막지 않는다).

    - 예외(`Exception`)나 `ToolProvision`이 아닌 반환은 `tools.provider_failed` 경고(예외 형식
      이름만, 메시지는 싣지 않는다 — 비밀이 섞일 수 있다)로 바꾸고 그 공급자를 건너뛴다.
    - `HostTool`이 아닌 도구 항목도 같은 경고로 뺀다.
    - 앞선 공급자와 이름이 겹치는 도구는 `tools.duplicate_name` 경고로 뺀다.
    - 공급자 경고는 details에 `provider`를 붙여 그대로 모은다.
    - 지침은 공급자 순서로 모은다. 문자열이 아닌 항목은 `tools.provider_failed` 경고로 빼고,
      공백뿐인 글은 조용히 뺀다.

    Returns:
        합친 결과(도구는 공급자 순서, 칸은 합집합, 경고는 발생 순서, 지침은 공급자 순서 +
        지침마다 공급자 id).
    """
    tools: list[HostTool] = []
    names: set[str] = set()
    consumed: set[str] = set()
    warnings: list[Issue] = []
    texts: list[str] = []
    owners: list[str] = []
    for provider in providers:
        pid = _provider_id(provider)
        try:
            got: object = provider.provide(ctx)
        except Exception as exc:  # 사용자 플러그인: 실행은 계속한다
            warnings.append(
                _warning(
                    ToolProviderCodes.PROVIDER_FAILED,
                    f"도구 공급자 {pid!r}가 실패해 건너뜁니다({type(exc).__name__})",
                    provider=pid,
                    error=type(exc).__name__,
                )
            )
            continue
        if not isinstance(got, ToolProvision):
            warnings.append(
                _warning(
                    ToolProviderCodes.PROVIDER_FAILED,
                    f"도구 공급자 {pid!r}의 결과 형식이 맞지 않아 건너뜁니다",
                    provider=pid,
                    error=type(got).__name__,
                )
            )
            continue
        for item in got.warnings:
            warnings.append(item.model_copy(update={"details": {**item.details, "provider": pid}}))
        consumed.update(got.consumed_slots)
        for item_text in got.instructions:
            text: object = item_text  # 공급자는 타입을 어길 수 있다(사용자 플러그인)
            if not isinstance(text, str):
                warnings.append(
                    _warning(
                        ToolProviderCodes.PROVIDER_FAILED,
                        f"도구 공급자 {pid!r}가 글이 아닌 지침을 줘 뺐습니다",
                        provider=pid,
                        error=type(text).__name__,
                    )
                )
                continue
            if text.strip():
                texts.append(text)
                owners.append(pid)
        for item_tool in got.host_tools:
            tool: object = item_tool  # 공급자는 타입을 어길 수 있다(사용자 플러그인)
            if not isinstance(tool, HostTool):
                warnings.append(
                    _warning(
                        ToolProviderCodes.PROVIDER_FAILED,
                        f"도구 공급자 {pid!r}가 도구 형식이 아닌 값을 줘 뺐습니다",
                        provider=pid,
                        error=type(tool).__name__,
                    )
                )
                continue
            if tool.name in names:
                warnings.append(_duplicate(tool.name, provider=pid))
                continue
            names.add(tool.name)
            tools.append(tool)
    return MergedToolProvision(
        host_tools=tuple(tools),
        consumed_slots=frozenset(consumed),
        warnings=tuple(warnings),
        instructions=tuple(texts),
        instruction_providers=tuple(owners),
    )


def attach_instructions(
    bundle: ResourceBundle | None,
    sourced: Sequence[tuple[str, str]],
    *,
    slot: str = KnownResourceSlots.INSTRUCTIONS,
) -> ResourceBundle | None:
    """공급자 지침을 묶음 칸 `slot` 끝에 붙인 사본(순수 함수, 원본은 그대로).

    칸 값은 글 목록이다(기존 값이 목록이 아니면 한 항목으로 감싼다). 출처에는 공급자마다
    `BundleSource(ref="tool_provider:<id>")`를 한 번씩 더한다.

    Args:
        bundle: 요청 묶음(없으면 새로 만든다).
        sourced: (공급자 id, 지침 글) 목록. 비면 `bundle`을 그대로 돌려준다.
        slot: 지침 칸 이름(기본 `KnownResourceSlots.INSTRUCTIONS`).

    Returns:
        지침을 붙인 묶음(`sourced`가 비면 입력 그대로, None이면 None).
    """
    if not sourced:
        return bundle
    base = bundle if bundle is not None else ResourceBundle()
    current = base.slots.get(slot)
    items: list[Any] = (
        [] if current is None else list(current) if isinstance(current, list) else [current]
    )
    items.extend(text for _, text in sourced)
    sources = list(base.sources.get(slot, []))
    seen = {s.ref for s in sources}
    for pid, _ in sourced:
        ref = instruction_source(pid)
        if ref not in seen:
            seen.add(ref)
            sources.append(BundleSource(ref=ref))
    return base.model_copy(
        update={"slots": {**base.slots, slot: items}, "sources": {**base.sources, slot: sources}}
    )


def _duplicate(name: str, **details: Any) -> Issue:
    return _warning(
        ToolProviderCodes.DUPLICATE_NAME,
        f"도구 이름 {name!r}가 이미 쓰여 공급 도구를 뺍니다",
        name=name,
        **details,
    )


def drop_taken(
    tools: Iterable[HostTool], taken: Iterable[str]
) -> tuple[list[HostTool], list[Issue]]:
    """이미 쓰인 이름(`taken`, 예: 위임 도구)과 겹치는 공급 도구를 뺀다.

    Returns:
        (남은 도구 순서 그대로, 뺀 도구마다 `tools.duplicate_name` 경고).
    """
    names = set(taken)
    kept: list[HostTool] = []
    issues: list[Issue] = []
    for tool in tools:
        if tool.name in names:
            issues.append(_duplicate(tool.name))
            continue
        names.add(tool.name)
        kept.append(tool)
    return kept, issues
