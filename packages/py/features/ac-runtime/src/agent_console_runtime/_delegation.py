"""X12 위임 방식(`DelegationStrategy`, design §R3.3).

노드(예: 에이전트 노드)가 나가는 연결 중 디스크립터 `invocation`이 있는 것의 도착 노드를 모아
`DelegationPlan`을 만들고, 연결의 `invocation.strategy` id로 위임 방식을 찾아 실행을 맡긴다.
엔진은 위임 방식을 부르지 않는다(스케줄 대상이 아닌 호출 대상은 노드 실행 안에서 돈다).

혼합 위임: 디스크립터 `composable`이 참이고 선택 프로토콜 `ComposableDelegation`
(`contribute`)을 만족하는 방식들은 한 위임자에서 합쳐 실행할 수 있다. 노드는 방식마다 `contribute`
결과(`DelegationContribution`)를 받아 `merge_contributions`로 합치고(이름 충돌은 오류 이슈)
`apply_contribution`으로 요청에 더해 백엔드를 한 번 부른다.

저장 시점 정적 검사(design §5.2R.7, 5.2R.37): 선택 프로토콜 `StaticDelegationChecks`
(`static_issues`)·`DelegationNameDeclarer`(`declared_names`)는 실행 시점 값(대상 유효 설정·
실행 묶음·백엔드 능력) 없이 그래프만으로 알 수 있는 문제를 저장 전에 낸다. 대상은
`DelegationMemberView`(정적 필드만)로 받는다. 이름 충돌 코드는 `duplicate_names_code(group)`이다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import (
    AgentSettings,
    DelegationStrategyDescriptor,
    Issue,
    ResourceBundle,
)

from ._host_tools import HostTool, duplicate_host_tool_names
from ._interfaces import AgentRequest, AgentResult, BackendEventSink, SubagentSpec

if TYPE_CHECKING:
    from ._context import NodeContext

DELEGATION_STRATEGIES_GROUP = "agent_console.delegation_strategies"
"""X12 entry point 그룹."""

DELEGATION_STRATEGIES_EXTENSION = "delegation_strategies"
"""X12 레지스트리 이름: `registries.extension(DELEGATION_STRATEGIES_EXTENSION)`
(= `registries.delegation_strategies`)."""


class DelegationMember(BaseModel):
    """위임 대상 하나(위임자 노드에서 `invocation` 연결로 이어진 도착 노드)."""

    node_id: str = Field(description="대상 노드 id.")
    edge_id: str = Field(description="위임자 → 대상 연결 id.")
    agent_id: str | None = Field(default=None, description="대상 에이전트 정의 id(actor).")
    role: str | None = Field(default=None, description="이 팀 안의 역할 이름.")
    delegate_when: str = Field(default="", description="언제 맡길지(위임자가 판단 근거로 본다).")
    settings: AgentSettings = Field(
        default_factory=AgentSettings, description="대상의 유효 설정(층 병합 결과)."
    )
    bundle: ResourceBundle | None = Field(default=None, description="대상의 실행 묶음.")
    config: dict[str, Any] = Field(default_factory=dict, description="연결(엣지) config.")


class DelegationPlan(BaseModel):
    """위임 실행 계획: 위임자 요청 + 대상 목록.

    `request`는 위임자 노드가 위임 없이 실행할 때 백엔드에 줄 요청 그대로다
    (유효 설정·프롬프트·세션·묶음).
    위임 방식은 이것을 바꿔(예: `subagents` 채움) 실행한다.
    """

    strategy: str = Field(description="위임 방식 id(X12 레지스트리 키).")
    delegator_node_id: str
    backend: str | None = Field(default=None, description="위임자 백엔드 id.")
    request: AgentRequest
    members: list[DelegationMember] = Field(default_factory=list)
    config: dict[str, Any] = Field(
        default_factory=dict, description="위임 방식 config(디스크립터 config_schema로 검증)."
    )


@runtime_checkable
class DelegationStrategy(Protocol):
    """위임 방식(X12). 구현은 플러그인이 `agent_console.delegation_strategies`로 등록한다.

    - `descriptor`: 혼합 그래프 검증 규칙(`max_depth`, `allows_outgoing_flow`, `member_fields`,
      `member_interaction_kinds`)의 근거. 검증은 `ac-teams`가 이 값으로 계산한다.
    - `validate(plan)`: 실행 직전 계획 검사(예: 백엔드 능력).
      error 이슈가 있으면 노드가 실패로 끝낸다.
    - `run(plan, ctx)`: 위임자를 실행하고 결과를 돌려준다. 대상의 이벤트는
      `ctx.emit(..., actor=대상 에이전트, node_path=ctx.child_path(대상 노드))`로, 대상의 답변은
      `ctx.emit_replies(대상 노드, outputs)`로 낸다.
    """

    descriptor: DelegationStrategyDescriptor

    def validate(self, plan: DelegationPlan) -> list[Issue]: ...

    async def run(self, plan: DelegationPlan, ctx: NodeContext) -> AgentResult: ...


type SinkWrapper = Callable[[BackendEventSink], BackendEventSink]
"""백엔드 sink를 감싸는 함수(예: 서브에이전트 결과 알림을 받아 대상 답변을 내는 sink)."""


class DelegationContribution(BaseModel):
    """합쳐 실행할 수 있는 위임 방식이 위임자 요청에 더할 것(`ComposableDelegation.contribute`).

    Attributes:
        subagents: 위임자 세션 안 하위 에이전트(백엔드 `capabilities.subagents` 필요).
        host_tools: 플랫폼 도구(백엔드 `capabilities.host_tools` 필요, 런타임 전용).
        options: `AgentRequest.options`에 더할 값(같은 키에 다른 값이면 합치기 오류).
        wrap_sink: 백엔드에 넘길 sink를 감쌀 함수. None이면 그대로. 여럿이면 순서대로 감싼다.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    subagents: list[SubagentSpec] = Field(default_factory=list)
    host_tools: list[HostTool] = Field(default_factory=list, exclude=True)
    options: dict[str, Any] = Field(default_factory=dict)
    wrap_sink: SinkWrapper | None = Field(default=None, exclude=True)


@runtime_checkable
class ComposableDelegation(DelegationStrategy, Protocol):
    """X12 선택 프로토콜: 다른 방식과 한 위임자에서 합쳐 실행할 수 있는 위임 방식(design §5R.3).

    디스크립터 `composable`이 참인 방식이 구현한다. `contribute`는 백엔드를 부르지 않고 요청에 더할
    것만 만든다. `run`은 이 방식 하나만 쓸 때 부른다.
    """

    def contribute(self, plan: DelegationPlan, ctx: NodeContext) -> DelegationContribution: ...


class DelegationNameGroups:
    """`declared_names`가 쓰는 이름 묶음 값(합쳐 실행할 때 서로 겹치면 안 되는 이름의 종류).

    값은 데이터다: 새 방식은 자기 묶음 이름을 써도 된다(충돌 코드는 `duplicate_names_code`).
    """

    HOST_TOOL: Final = "host_tool"
    """플랫폼 도구 이름(`DelegationContribution.host_tools[].name`)."""
    SUBAGENT: Final = "subagent"
    """하위 에이전트 이름(`DelegationContribution.subagents[].name`)."""


DUPLICATE_NAMES_CODE_TEMPLATE: Final = "delegation.duplicate_{group}_names"
"""이름 묶음 `group`의 충돌 `Issue.code` 형식(`ac-teams`도 같은 형식을 데이터로 갖는다)."""


def duplicate_names_code(group: str) -> str:
    """이름 묶음 → 충돌 코드(예: `host_tool` → `delegation.duplicate_host_tool_names`)."""
    return DUPLICATE_NAMES_CODE_TEMPLATE.format(group=group)


class DelegationIssueCodes:
    """위임 합치기(`merge_contributions`)가 내는 `Issue.code` 값."""

    DUPLICATE_HOST_TOOL_NAMES: Final = "delegation.duplicate_host_tool_names"
    DUPLICATE_SUBAGENT_NAMES: Final = "delegation.duplicate_subagent_names"
    CONFLICTING_OPTIONS: Final = "delegation.conflicting_options"


@runtime_checkable
class DelegationMemberView(Protocol):
    """정적 검사가 보는 위임 대상(실행 시점 값인 유효 설정·실행 묶음은 없다).

    `DelegationMember`와 `ac-teams.DelegationTarget`이 구조적으로 만족한다.
    """

    @property
    def node_id(self) -> str: ...

    @property
    def edge_id(self) -> str: ...

    @property
    def agent_id(self) -> str | None: ...

    @property
    def role(self) -> str | None: ...

    @property
    def delegate_when(self) -> str: ...

    @property
    def config(self) -> Mapping[str, Any]: ...


@runtime_checkable
class StaticDelegationChecks(Protocol):
    """X12 선택 프로토콜: 저장 시점 방식 고유 정적 검사(design §5.2R.7, 5.2R.37).

    `config`는 위임자 노드의 이 방식 config(노드 config `delegation[방식 id]`, 없으면 `{}`),
    `members`는 이 방식으로 이어진 대상이다. 방식 config 스키마 검사와 같은 대상 중복은 `ac-teams`
    일반 규칙이 하므로 여기서 다시 내지 않는다(스키마로 표현할 수 없는 규칙만).

    돌려준 이슈의 `path`는 방식 config 기준 JSON Pointer다(호출자가 `/delegation/<방식 id>`를
    앞에 붙인다). `edge_id`가 있으면 그 위임 연결의 이슈이고 `path`는 그대로 둔다. `node_id`가
    비면 호출자가 위임자 노드 id를 채운다. 실행 시점 `validate(plan)`은 그대로 실행 때 돈다.
    """

    def static_issues(
        self, config: Mapping[str, Any], members: Sequence[DelegationMemberView]
    ) -> list[Issue]: ...


@runtime_checkable
class DelegationNameDeclarer(Protocol):
    """X12 선택 프로토콜: 합쳐 실행할 때 겹치면 안 되는 이름을 미리 알린다(5.2R.37).

    `{묶음: [이름]}`(묶음 값 예: `DelegationNameGroups`). 한 위임자가 여러 방식을 쓰면 호출자가
    방식들의 이름을 묶음별로 모아 겹침을 `duplicate_names_code(묶음)` 오류로 낸다
    (`merge_contributions` 실행 시점 검사와 같은 코드). config가 맞지 않아 이름을 알 수 없으면
    그 묶음을 빼고 돌려준다.
    """

    def declared_names(
        self, config: Mapping[str, Any], members: Sequence[DelegationMemberView]
    ) -> Mapping[str, list[str]]: ...


def _duplicates(names: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    dup: set[str] = set()
    for name in names:
        (dup if name in seen else seen).add(name)
    return sorted(dup)


def merge_contributions(
    items: Sequence[DelegationContribution],
) -> tuple[DelegationContribution, list[Issue]]:
    """여러 방식의 `contribute` 결과를 하나로 합친다(순서대로 이어 붙이기, design §5R.6).

    Returns:
        (합친 결과, 오류 이슈). 이슈가 있으면 실행하지 않는다: 플랫폼 도구 이름 겹침
        (`delegation.duplicate_host_tool_names`), 하위 에이전트 이름 겹침, 같은 옵션 키에 다른 값.
    """
    subagents = [s for item in items for s in item.subagents]
    tools = [t for item in items for t in item.host_tools]
    options: dict[str, Any] = {}
    conflicts: list[str] = []
    for item in items:
        for key, value in item.options.items():
            if key in options and options[key] != value:
                conflicts.append(key)
            options.setdefault(key, value)
    wrappers = [item.wrap_sink for item in items if item.wrap_sink is not None]
    issues: list[Issue] = []
    tool_dups = duplicate_host_tool_names(tools)
    if tool_dups:
        issues.append(
            Issue(
                severity="error",
                code=DelegationIssueCodes.DUPLICATE_HOST_TOOL_NAMES,
                message=f"합친 위임 방식의 플랫폼 도구 이름이 겹칩니다: {', '.join(tool_dups)}",
                details={"names": tool_dups},
            )
        )
    sub_dups = _duplicates([s.name for s in subagents])
    if sub_dups:
        issues.append(
            Issue(
                severity="error",
                code=DelegationIssueCodes.DUPLICATE_SUBAGENT_NAMES,
                message=f"합친 위임 방식의 하위 에이전트 이름이 겹칩니다: {', '.join(sub_dups)}",
                details={"names": sub_dups},
            )
        )
    if conflicts:
        keys = sorted(set(conflicts))
        issues.append(
            Issue(
                severity="error",
                code=DelegationIssueCodes.CONFLICTING_OPTIONS,
                message=f"합친 위임 방식의 요청 옵션 값이 서로 다릅니다: {', '.join(keys)}",
                details={"keys": keys},
            )
        )

    def wrap(sink: BackendEventSink) -> BackendEventSink:
        for wrapper in wrappers:
            sink = wrapper(sink)
        return sink

    merged = DelegationContribution(
        subagents=subagents,
        host_tools=tools,
        options=options,
        wrap_sink=wrap if wrappers else None,
    )
    return merged, issues


def apply_contribution(request: AgentRequest, contribution: DelegationContribution) -> AgentRequest:
    """요청 사본에 `contribute` 결과를 더한다(기존 하위 에이전트·도구·옵션 뒤에 이어 붙임).

    옵션은 요청 값이 우선한다(노드가 준 값을 위임 방식이 덮지 않는다).
    """
    return request.model_copy(
        update={
            "subagents": [*request.subagents, *contribution.subagents],
            "host_tools": [*request.host_tools, *contribution.host_tools],
            "options": {**contribution.options, **request.options},
        }
    )
