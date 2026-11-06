"""엔진 시험: 기본 노드·연결 종류(``ac-nodes-core``)의 에이전트 노드가 이 백엔드로 실행된다.

엔진은 백엔드 id를 모른다. 레지스트리에 entry point로 들어온 백엔드를 에이전트 정의의 ``backend``로
고를 뿐이다(fake 백엔드 시험과 같은 모양: 넘겨주기 연쇄, 노드마다 세션, 대본 오류는 노드 실패).
"""

from __future__ import annotations

import importlib.metadata
from typing import Any

from agent_console_contracts import Agent, Graph, NodeRun
from agent_console_example_backend import BACKEND_ID
from agent_console_nodes_core import AGENT_LOOKUP
from agent_console_runtime import (
    BACKENDS_GROUP,
    DELEGATION_STRATEGIES_GROUP,
    EDGE_TYPES_GROUP,
    NODE_TYPES_GROUP,
    GraphRuntime,
    Registries,
    Services,
    load_registries,
)
from agent_console_runtime.testing import InMemoryRecorder, SequentialIds, StepClock

CORE = "agent-console-nodes-core"
GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP)
EXAMPLE = importlib.metadata.EntryPoint(
    name=BACKEND_ID, value="agent_console_example_backend:ScriptedBackend", group=BACKENDS_GROUP
)


def registries() -> Registries:
    """설치한 서버처럼: 기본 노드·연결 종류 + 이 예제 백엔드(다른 백엔드는 없다)."""
    core = [ep for ep in importlib.metadata.distribution(CORE).entry_points if ep.group in GROUPS]
    regs = Registries()
    reports = load_registries(regs, entry_points=[*core, EXAMPLE])
    assert all(r.ok for r in reports), reports
    assert [e.key for e in regs.backends.list()] == [BACKEND_ID]
    return regs


def agent(agent_id: str, reply: str) -> Agent:
    return Agent.model_validate(
        {
            "id": agent_id,
            "name": agent_id.upper(),
            "backend": BACKEND_ID,
            "backend_options": {"default_reply": reply},
        }
    )


def edge(eid: str, src: tuple[str, str], dst: tuple[str, str], kind: str) -> dict[str, Any]:
    return {
        "id": eid,
        "source": {"node": src[0], "port": src[1]},
        "target": {"node": dst[0], "port": dst[1]},
        "kind": kind,
        "config": {},
    }


def team() -> Graph:
    return Graph.model_validate(
        {
            "id": "team",
            "name": "팀",
            "nodes": [
                {"id": "you", "type": "user", "label": "나"},
                {"id": "a", "type": "agent", "label": "a", "config": {"agent_ref": "a"}},
                {"id": "b", "type": "agent", "label": "b", "config": {"agent_ref": "b"}},
            ],
            "edges": [
                edge("m", ("you", "says"), ("a", "in"), "message"),
                edge("h", ("a", "out"), ("b", "in"), "handoff"),
                edge("r", ("b", "out"), ("you", "hears"), "reply"),
            ],
        }
    )


async def run_team(*agents: Agent) -> tuple[Any, InMemoryRecorder]:
    found = {a.id: a for a in agents}
    recorder = InMemoryRecorder()
    runtime = GraphRuntime(
        registries(),
        recorder,
        clock=StepClock(),
        ids=SequentialIds("e"),
        services=Services({AGENT_LOOKUP: found.get}),
    )
    return await runtime.run(team(), {"text": "시작"}), recorder


async def test_handoff_chain_runs_on_example_backend() -> None:
    run, recorder = await run_team(agent("a", "a:$prompt"), agent("b", "b:$prompt"))
    assert run.status == "completed", run.error
    replies = [e.payload["text"] for e in recorder.events.list(run.id) if e.type == "run.reply"]
    assert replies == ["b:a:시작"]
    node_runs: dict[str, NodeRun] = {nr.node_id: nr for nr in recorder.runs.list_node_runs(run.id)}
    sessions = {node_runs[x].backend_session_id for x in "ab"}
    assert len(sessions) == 2
    assert None not in sessions
    started = [e for e in recorder.events.list(run.id) if e.type == "agent.session_started"]
    assert {e.payload["backend"] for e in started} == {BACKEND_ID}


async def test_bad_script_fails_the_node() -> None:
    broken = Agent.model_validate(
        {"id": "a", "name": "A", "backend": BACKEND_ID, "backend_options": {"nope": 1}}
    )
    run, recorder = await run_team(broken, agent("b", "b"))
    assert run.status == "failed"
    failed = [nr for nr in recorder.runs.list_node_runs(run.id) if nr.node_id == "a"]
    assert failed
    assert failed[0].status == "failed"
