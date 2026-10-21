"""예제 위임 방식 `example.round_robin`: entry point 선언·디스크립터·검사·엔진 실행·혼합 금지·제거.

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 엔진·기본 노드(에이전트 노드·위임 연결)·
fake 백엔드는 dev 의존이고, 이 위임 방식은 레지스트리에 직접 등록한다(entry point를 읽지 않는다).
"""

from __future__ import annotations

import importlib.metadata
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_console_backend_fake import FakeBackend
from agent_console_contracts import (
    Agent,
    EdgeSpec,
    Graph,
    NodeRun,
    NodeSpec,
    Run,
    WorkspaceSettings,
)
from agent_console_example_delegation import (
    STRATEGY_ID,
    RoundRobinCodes,
    RoundRobinConfig,
    RoundRobinDelegation,
    fill,
)
from agent_console_nodes_core import AGENT_LOOKUP, WORKSPACE_SETTINGS
from agent_console_runtime import (
    DELEGATION_STRATEGIES_GROUP,
    EDGE_TYPES_GROUP,
    NODE_TYPES_GROUP,
    AgentRequest,
    DelegationMember,
    DelegationPlan,
    GraphRuntime,
    Registries,
    Services,
    edge_type_descriptors,
    load_registries,
    node_type_descriptors,
)
from agent_console_runtime.testing import InMemoryRecorder, SequentialIds, StepClock
from agent_console_teams import TeamIssueCodes, validate_team

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
WORKSPACE = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "fake"}})
GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP)


# ---------------------------------------------------------------- 실행 스택(기본 노드 + fake)


@dataclass
class Stack:
    registries: Registries
    recorder: InMemoryRecorder
    agents: dict[str, Agent]
    runtime: GraphRuntime | None = None

    async def run(self, graph: Graph, text: str) -> Run:
        if self.runtime is None:  # 스택 하나에 런타임 하나(Run id가 겹치지 않게)
            services = Services({AGENT_LOOKUP: self.agents.get, WORKSPACE_SETTINGS: WORKSPACE})
            self.runtime = GraphRuntime(
                self.registries,
                self.recorder,
                clock=StepClock(),
                ids=SequentialIds("e"),
                services=services,
            )
        return await self.runtime.run(graph, {"text": text})

    def node_runs(self, run: Run) -> dict[str, NodeRun]:
        return {nr.node_id: nr for nr in self.recorder.runs.list_node_runs(run.id)}

    def replies(self, run: Run) -> list[str]:
        events = self.recorder.events.list(run.id)
        return [str(ev.payload["text"]) for ev in events if ev.type == "run.reply"]

    def issues(self, graph: Graph) -> list[tuple[str, str]]:
        strategies = [e.item.descriptor for e in self.registries.delegation_strategies.list()]
        found = validate_team(
            graph,
            node_types=node_type_descriptors(self.registries),
            edge_types=edge_type_descriptors(self.registries),
            strategies=strategies,
            agents=self.agents,
            workspace=WORKSPACE,
        )
        return [(i.severity, i.code) for i in found]


def make_stack(*, installed: bool = True) -> Stack:
    """기본 노드 플러그인(entry point) + fake 백엔드 + (설치했으면) 이 위임 방식."""
    regs = Registries()
    eps = [
        ep
        for ep in importlib.metadata.distribution("agent-console-nodes-core").entry_points
        if ep.group in GROUPS
    ]
    assert all(r.ok for r in load_registries(regs, entry_points=eps))
    regs.backends.register("fake", FakeBackend(ids=SequentialIds("s"), clock=StepClock()))
    if installed:
        regs.delegation_strategies.register(STRATEGY_ID, RoundRobinDelegation())
    agents = [
        _agent("lead", "(리더가 직접 답함)"),
        _agent("writer", "초안($prompt)"),
        _agent("checker", "검토($prompt)"),
        _agent("broken", "", fail={"code": "t.broken", "message": "고장"}),
    ]
    return Stack(regs, InMemoryRecorder(), {a.id: a for a in agents})


def _agent(agent_id: str, response: str, **rule: Any) -> Agent:
    options = {"default": {"response": response, **rule}}
    return Agent.model_validate({"id": agent_id, "name": agent_id, "backend_options": options})


def _node(node_id: str, **config: Any) -> NodeSpec:
    return NodeSpec.model_validate(
        {
            "id": node_id,
            "type": "agent",
            "label": node_id,
            "config": {"agent_ref": node_id, **config},
        }
    )


def _edge(eid: str, src: str, sp: str, dst: str, tp: str, kind: str, **config: Any) -> EdgeSpec:
    return EdgeSpec.model_validate(
        {
            "id": eid,
            "source": {"node": src, "port": sp},
            "target": {"node": dst, "port": tp},
            "kind": kind,
            "config": config,
        }
    )


def team(*members: str, kind: str = "delegate", **lead_config: Any) -> Graph:
    """나 → 리더 ⇢(위임 연결, 방식 = 이 예제) 대상들, 리더 → 답변."""
    nodes = [NodeSpec(id="you", type="user", label="나"), _node("lead", **lead_config)]
    edges = [
        _edge("m", "you", "says", "lead", "in", "message"),
        _edge("r", "lead", "out", "you", "hears", "reply"),
    ]
    for member in members:
        nodes.append(_node(member))
        edges.append(
            _edge(
                f"lead->{member}",
                "lead",
                "delegates",
                member,
                "delegated",
                kind,
                strategy=STRATEGY_ID,
            )
        )
    return Graph(id="team", name="팀", nodes=nodes, edges=edges)


# ---------------------------------------------------------------- 등록·디스크립터·검사


def test_entry_point_declared_in_strategy_group_with_descriptor_id() -> None:
    meta = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    eps = meta["project"]["entry-points"][DELEGATION_STRATEGIES_GROUP]
    assert eps == {STRATEGY_ID: "agent_console_example_delegation:RoundRobinDelegation"}


def test_descriptor_rules_are_values() -> None:
    d = RoundRobinDelegation.descriptor
    assert d.id == STRATEGY_ID
    assert d.composable is False  # 다른 방식과 섞을 수 없다
    assert d.requires_backend_capability is None  # 위임자 백엔드를 부르지 않는다
    assert d.config_schema == RoundRobinConfig.model_json_schema()


def _plan(config: dict[str, Any] | None = None, *members: str) -> DelegationPlan:
    return DelegationPlan(
        strategy=STRATEGY_ID,
        delegator_node_id="lead",
        request=AgentRequest(agent=Agent(id="lead", name="L"), prompt="일"),
        members=[DelegationMember(node_id=m, edge_id=f"lead->{m}") for m in members],
        config=config or {},
    )


def test_validate_reports_missing_members_and_bad_config() -> None:
    strategy = RoundRobinDelegation()
    assert strategy.validate(_plan(None, "a")) == []
    assert [i.code for i in strategy.validate(_plan())] == [RoundRobinCodes.NO_MEMBERS]
    bad = strategy.validate(_plan({"separator": 3, "nope": True}, "a"))
    assert [i.code for i in bad] == [RoundRobinCodes.INVALID_CONFIG]


def test_fill_is_safe_substitution() -> None:
    assert fill("[{target}] {result}", {"target": "a", "result": "ok"}) == "[a] ok"
    assert fill("{target.__class__} {unknown}", {"target": "a"}) == "{target.__class__} {unknown}"


# ---------------------------------------------------------------- 엔진 실행(기본 노드)


async def test_members_run_in_order_as_own_node_runs() -> None:
    stack = make_stack()
    graph = team("writer", "checker")
    assert [c for s, c in stack.issues(graph) if s == "error"] == []
    run = await stack.run(graph, "안내문")
    assert run.status == "completed", run.error
    assert stack.replies(run) == ["[writer] 초안(안내문)\n\n[checker] 검토(안내문)"]
    runs = stack.node_runs(run)
    for member in ("writer", "checker"):
        assert runs[member].invoked_by == ["lead"]
        assert runs[member].status == "succeeded"


async def test_config_changes_format_and_failure_handling() -> None:
    stack = make_stack()
    keep_going = team("broken", "writer")
    run = await stack.run(keep_going, "x")
    assert run.status == "completed", run.error
    assert stack.replies(run) == ["[broken] (실패: t.broken)\n\n[writer] 초안(x)"]

    custom = team(
        "writer", delegation={STRATEGY_ID: {"item_template": "{role}={result}", "separator": " | "}}
    )
    run = await stack.run(custom, "y")
    assert stack.replies(run) == ["writer=초안(y)"]

    strict = team("broken", "writer", delegation={STRATEGY_ID: {"stop_on_failure": True}})
    run = await stack.run(strict, "z")
    lead = stack.node_runs(run)["lead"]
    assert lead.status == "failed"
    assert lead.error is not None
    assert lead.error.code == RoundRobinCodes.MEMBER_FAILED
    assert "writer" not in stack.node_runs(run)  # 멈춘 뒤 다음 대상은 부르지 않는다


# ---------------------------------------------------------------- 혼합 금지·제거


def test_mixing_with_another_strategy_is_team_mixed_strategies() -> None:
    """composable이 아니므로 같은 리더의 다른 방식(서브에이전트) 대상과 섞으면 검증 오류."""
    stack = make_stack()
    graph = team("writer")
    graph.nodes.append(_node("checker"))
    graph.edges.append(_edge("sub", "lead", "delegates", "checker", "delegated", "subagent"))
    assert ("error", TeamIssueCodes.MIXED_STRATEGIES) in stack.issues(graph)


async def test_removed_plugin_warns_and_lead_fails_to_run() -> None:
    """README 주장 고정: 제거(등록 없음)하면 팀 구성은 남고, 저장 전 검증이 알리고 실행은 막힌다."""
    stack = make_stack(installed=False)
    graph = team("writer")
    issues = stack.issues(graph)
    assert ("warning", TeamIssueCodes.UNKNOWN_STRATEGY) in issues
    run = await stack.run(graph, "x")
    lead = stack.node_runs(run)["lead"]
    assert lead.status == "failed"
    assert lead.error is not None
    assert lead.error.code == "agent.unknown_strategy"
