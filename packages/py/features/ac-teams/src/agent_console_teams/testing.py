"""ac-teams 테스트 도구: **임의 이름**의 노드·엣지 타입과 위임 방식 디스크립터.

기본 플러그인 이름(agent·user·subagent·delegate·handoff·loop·message·reply·ask_user 등)을 쓰지
않는다. 사이클 연결(`cycle`)·합쳐 실행할 수 있는 위임 방식(`composable`)도 임의 이름이다.
`Kit(names)`로 같은 의미의 디스크립터를 다른 이름으로 만들 수 있다(이름 무관 동작 확인).
공개 `testing` 하위 모듈이다(design §3R.2.2): `from agent_console_teams.testing import KITS, Kit`.
이 패키지를 쓰는 다른 프로젝트도 같은 디스크립터로 시험할 수 있다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts import (
    AgentSettings,
    CyclePolicy,
    DefinitionBinding,
    DelegationStrategyDescriptor,
    EdgeConnects,
    EdgeInteraction,
    EdgeInvocation,
    EdgePortPair,
    EdgeSpec,
    EdgeTypeDescriptor,
    Endpoint,
    Graph,
    NodeSpec,
    NodeTypeDescriptor,
    PortDef,
    PortSpec,
)

DEFAULT_NAMES: dict[str, str] = {
    # 노드 타입
    "worker": "actor-x",
    "person": "human-x",
    "material": "doc-x",
    "nest": "crew-x",
    # 엣지 타입
    "entry": "hello",
    "exit": "bye",
    "flow": "pass",
    "invoke": "boss",
    "invoke2": "boss-two",
    "attach": "attach-x",
    "ask": "askme",
    "loop": "again-x",
    "invoke3": "summon",
    # 위임 방식
    "s_inner": "inner",
    "s_deep": "deep",
    "s_other": "other",
    "s_far": "far",
    # 상호작용 종류
    "q": "q-kind",
    "perm": "perm-kind",
}

RENAMED: dict[str, str] = {k: f"zz-{v[::-1]}" for k, v in DEFAULT_NAMES.items()}


def _ports(inputs: list[str], outputs: list[str]) -> PortSpec:
    return PortSpec(
        inputs=[PortDef(name=n) for n in inputs], outputs=[PortDef(name=n) for n in outputs]
    )


@dataclass
class Kit:
    """테스트 디스크립터 묶음과 그래프 만들기 도우미."""

    names: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_NAMES))

    def __getitem__(self, key: str) -> str:
        return self.names[key]

    # ---------------------------------------------------------------- 디스크립터
    @property
    def node_types(self) -> list[NodeTypeDescriptor]:
        n = self.names
        return [
            NodeTypeDescriptor(
                id=n["worker"],
                title="일꾼",
                role="w-role",
                binds=DefinitionBinding(kind="agent", field="who"),
                static_ports=_ports(["inbox", "called", "kit"], ["outbox", "calls"]),
            ),
            NodeTypeDescriptor(
                id=n["person"],
                title="사람",
                role="p-role",
                dynamic_ports=True,
            ),
            NodeTypeDescriptor(
                id=n["material"],
                title="자료",
                role="m-role",
                executable=False,
                binds=DefinitionBinding(kind="resource", field="pick"),
                static_ports=_ports([], ["give"]),
            ),
            # 중첩 팀 노드(design §5R.7): 팀 구성 정의를 묶는다. 역할은 일꾼과 같다(같은 연결).
            NodeTypeDescriptor(
                id=n["nest"],
                title="묶음 팀",
                role="w-role",
                binds=DefinitionBinding(kind="graph", field="crew"),
                static_ports=_ports(["inbox"], ["outbox"]),
            ),
        ]

    @staticmethod
    def resolve_ports(desc: NodeTypeDescriptor, config: Mapping[str, Any]) -> PortSpec:
        """사람 노드: 고정 포트 + config `review.decisions`의 id마다 출력 포트."""
        review = config.get("review")
        decisions = review.get("decisions", []) if isinstance(review, Mapping) else []
        extra = [d["id"] for d in decisions if isinstance(d, Mapping) and "id" in d]
        return _ports(["ear", "asks", "look"], ["mouth", *extra])

    @property
    def edge_types(self) -> list[EdgeTypeDescriptor]:
        n = self.names
        w, p, m = "w-role", "p-role", "m-role"
        return [
            EdgeTypeDescriptor(
                id=n["entry"],
                title="들어옴",
                scheduling="entry",
                connects=EdgeConnects(source=[p], target=[w, p]),
                default_ports=EdgePortPair(source="mouth", target="inbox"),
            ),
            EdgeTypeDescriptor(
                id=n["exit"],
                title="나감",
                scheduling="exit",
                connects=EdgeConnects(source=[w, p], target=[p]),
                default_ports=EdgePortPair(source="outbox", target="ear"),
            ),
            EdgeTypeDescriptor(
                id=n["flow"],
                title="흐름",
                scheduling="flow",
                connects=EdgeConnects(source=[w, p], target=[w, p]),
            ),
            EdgeTypeDescriptor(
                id=n["invoke"],
                title="부르기",
                scheduling="none",
                invocation=EdgeInvocation(strategy=n["s_inner"]),
                connects=EdgeConnects(source=[w], target=[w]),
                default_ports=EdgePortPair(source="calls", target="called"),
            ),
            EdgeTypeDescriptor(
                id=n["invoke2"],
                title="깊게 부르기",
                scheduling="none",
                invocation=EdgeInvocation(strategy=n["s_deep"]),
                connects=EdgeConnects(source=[w], target=[w]),
                default_ports=EdgePortPair(source="calls", target="called"),
            ),
            EdgeTypeDescriptor(
                id=n["invoke3"],
                title="멀리 부르기",
                scheduling="none",
                invocation=EdgeInvocation(strategy=n["s_far"]),
                connects=EdgeConnects(source=[w], target=[w]),
                default_ports=EdgePortPair(source="calls", target="called"),
                config_schema={
                    "type": "object",
                    "properties": {"note": {"type": "string"}},
                    "additionalProperties": False,
                },
            ),
            EdgeTypeDescriptor(
                id=n["attach"],
                title="붙이기",
                scheduling="none",
                connects=EdgeConnects(source=[m], target=[w]),
                default_ports=EdgePortPair(source="give", target="kit"),
            ),
            EdgeTypeDescriptor(
                id=n["ask"],
                title="묻기",
                scheduling="none",
                interaction=EdgeInteraction(kinds=[n["q"], n["perm"]]),
                connects=EdgeConnects(source=[w], target=[p]),
                default_ports=EdgePortPair(source="outbox", target="asks"),
            ),
            EdgeTypeDescriptor(
                id=n["loop"],
                title="되감기",
                scheduling="flow",
                cycle=CyclePolicy(max_iterations=3),
                connects=EdgeConnects(source=[w, p], target=[w, p]),
                config_schema={
                    "type": "object",
                    "properties": {"max_iterations": {"type": "integer"}},
                },
            ),
        ]

    @property
    def strategies(self) -> list[DelegationStrategyDescriptor]:
        n = self.names
        return [
            DelegationStrategyDescriptor(
                id=n["s_inner"],
                title="안쪽",
                composable=True,
                member_fields=["model", "system_prompt", "tools"],
                max_depth=1,
                allows_outgoing_flow=False,
                requires_backend_capability="subagents",
                member_interaction_kinds=[n["perm"]],
            ),
            DelegationStrategyDescriptor(
                id=n["s_deep"],
                title="깊은",
                member_fields=["backend", "model", "system_prompt", "tools", "limits"],
                max_depth=None,
                allows_outgoing_flow=True,
            ),
            DelegationStrategyDescriptor(
                id=n["s_other"],
                title="다른",
                member_fields=["model"],
                max_depth=2,
            ),
            DelegationStrategyDescriptor(
                id=n["s_far"],
                title="먼",
                member_fields=list(AgentSettings.model_fields),
                max_depth=None,
                allows_outgoing_flow=False,
                requires_backend_capability="host_tools",
                member_interaction_kinds=None,
                composable=True,
                shares_session=False,
            ),
        ]

    @property
    def strategy_map(self) -> dict[str, DelegationStrategyDescriptor]:
        return {s.id: s for s in self.strategies}

    # ---------------------------------------------------------------- 그래프
    def worker(self, node_id: str, who: str | None = None, **config: Any) -> NodeSpec:
        data = dict(config)
        data["who"] = who or node_id
        return NodeSpec(id=node_id, type=self["worker"], label=node_id.upper(), config=data)

    def person(self, node_id: str = "me", **config: Any) -> NodeSpec:
        return NodeSpec(id=node_id, type=self["person"], label="나", config=dict(config))

    def material(self, node_id: str, pick: str) -> NodeSpec:
        return NodeSpec(id=node_id, type=self["material"], config={"pick": pick})

    def nest(self, node_id: str, crew: str, version: str | None = None) -> NodeSpec:
        """중첩 팀 노드(`crew` = 자식 팀 구성 id, `version` = 고정 버전)."""
        config: dict[str, Any] = {"crew": crew}
        if version is not None:
            config["version"] = version
        return NodeSpec(id=node_id, type=self["nest"], label=node_id.upper(), config=config)

    _PORTS: Mapping[str, tuple[str, str]] = field(
        default_factory=lambda: {
            "entry": ("mouth", "inbox"),
            "exit": ("outbox", "ear"),
            "flow": ("outbox", "inbox"),
            "invoke": ("calls", "called"),
            "invoke2": ("calls", "called"),
            "attach": ("give", "kit"),
            "ask": ("outbox", "asks"),
            "loop": ("outbox", "inbox"),
            "invoke3": ("calls", "called"),
        }
    )

    def edge(
        self,
        edge_id: str,
        role: str,
        src: str,
        dst: str,
        *,
        sport: str | None = None,
        dport: str | None = None,
        **config: Any,
    ) -> EdgeSpec:
        """`role`은 의미 키(entry·exit·flow·invoke·invoke2·invoke3·attach·ask·loop) — 실제 id는
        names에서."""
        dsp, ddp = self._PORTS[role]
        return EdgeSpec(
            id=edge_id,
            source=Endpoint(node=src, port=sport or dsp),
            target=Endpoint(node=dst, port=dport or ddp),
            kind=self[role],
            config=dict(config),
        )

    @staticmethod
    def graph(
        nodes: list[NodeSpec],
        edges: list[EdgeSpec],
        settings: Mapping[str, Any] | None = None,
        *,
        graph_id: str = "team",
    ) -> Graph:
        data: dict[str, Any] = {
            "id": graph_id,
            "name": "팀",
            "nodes": [n.model_dump(exclude_unset=True) for n in nodes],
            "edges": [e.model_dump(exclude_unset=True) for e in edges],
        }
        if settings is not None:
            data["settings"] = dict(settings)
        return Graph.model_validate(data)


KITS: tuple[Kit, ...] = (Kit(dict(DEFAULT_NAMES)), Kit(dict(RENAMED)))
"""기본 이름과 완전히 다른 이름 두 벌.

`@pytest.mark.parametrize("k", KITS)`로 같은 테스트를 돌린다.
"""
