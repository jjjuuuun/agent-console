"""턴 세션 규칙(`TurnSessions`) 주입: 수집·정리를 규칙에 맡기고, 기본은 `RootRunSessions`."""

from collections.abc import Iterable, Mapping

from agent_console_chat import ChatService, RootRunSessions, TurnSessions
from agent_console_chat.testing import (
    FakeLauncher,
    MemoryConversations,
    MemoryEvents,
    MemoryGraphs,
    MemoryRuns,
)
from agent_console_contracts import (
    CreateConversationRequest,
    Graph,
    NodeSpec,
    PostMessageRequest,
    Run,
    RunEvent,
    SessionRef,
    UpdateConversationRequest,
)

REF = SessionRef(backend="fake", session_id="s")


def _graph(graph_id: str, *nodes: str) -> Graph:
    return Graph(id=graph_id, name=graph_id, nodes=[NodeSpec(id=n, type="agent") for n in nodes])


class PathRules:
    """예제 규칙: 키 `"<노드>:<무엇>"`, 첫 구간이 노드 id면 남긴다."""

    def __init__(self, found: dict[str, SessionRef] | None = None, *, fail: bool = False) -> None:
        self.found = found or {}
        self.fail = fail
        self.collected: list[str] = []

    def collect(self, run: Run) -> dict[str, SessionRef]:
        self.collected.append(run.id)
        if self.fail:
            raise RuntimeError("조회 실패")
        return dict(self.found)

    def prune(
        self, sessions: Mapping[str, SessionRef], node_ids: Iterable[str]
    ) -> dict[str, SessionRef]:
        keep = set(node_ids)
        return {k: v for k, v in sessions.items() if k.split(":", 1)[0] in keep}


def _service(rules: TurnSessions | None, *graphs: Graph) -> tuple[ChatService, FakeLauncher]:
    runs, events = MemoryRuns(), MemoryEvents()
    launcher = FakeLauncher(runs, events)
    service = ChatService(
        MemoryConversations(),
        MemoryGraphs(graphs),
        launcher=launcher,
        runs=runs,
        events=events,
        sessions=rules,
    )
    return service, launcher


async def test_injected_rules_collect_prune_and_pass_to_next_turn() -> None:
    rules = PathRules({"t:a": REF, "gone:b": REF, "pl": REF})
    service, launcher = _service(rules, _graph("g", "t", "pl"), _graph("h", "t"))
    conv = service.create(CreateConversationRequest(graph_id="g"))
    run = await service.post_message(conv.id, PostMessageRequest(text="하나"))
    assert isinstance(run, Run)
    launcher.finish(run.id)
    await service.wait_idle()
    assert rules.collected == [run.id]
    assert service.get(conv.id).sessions == {"t:a": REF, "pl": REF}
    run2 = await service.post_message(conv.id, PostMessageRequest(text="둘"))
    assert isinstance(run2, Run)
    assert launcher.started[1].sessions == {"t:a": REF, "pl": REF}
    launcher.finish(run2.id)
    await service.wait_idle()
    # 팀 구성 전환도 같은 규칙으로 거른다(경로 키 유지)
    updated = service.update(conv.id, UpdateConversationRequest(graph_id="h"))
    assert updated.sessions == {"t:a": REF}


async def test_collect_failure_keeps_conversation_going() -> None:
    service, launcher = _service(PathRules(fail=True), _graph("g", "pl"))
    conv = service.create(CreateConversationRequest(graph_id="g"))
    run = await service.post_message(conv.id, PostMessageRequest(text="하나"))
    assert isinstance(run, Run)
    launcher.finish(run.id)
    await service.wait_idle()
    assert service.get(conv.id).sessions == {}
    assert not service.is_busy(conv.id)


async def test_connect_sets_rules_and_none_restores_default() -> None:
    service, launcher = _service(None, _graph("g", "pl"))
    rules = PathRules({"pl:x": REF})
    service.connect(launcher=launcher, sessions=rules)
    conv = service.create(CreateConversationRequest(graph_id="g"))
    run = await service.post_message(conv.id, PostMessageRequest(text="하나"))
    assert isinstance(run, Run)
    launcher.finish(run.id)
    await service.wait_idle()
    assert service.get(conv.id).sessions == {"pl:x": REF}


def test_root_run_sessions_default_reads_own_events() -> None:
    events = MemoryEvents()
    events.add(
        [
            RunEvent(
                event_id="e1",
                run_id="r1",
                seq=1,
                ts=1.0,
                node_path=["pl"],
                type="agent.session_started",
                payload={"session_id": "s", "backend": "fake"},
            )
        ]
    )
    run = Run(
        id="r1",
        graph_id="g",
        graph_version="v",
        status="completed",
        input={},
        origin="chat",
        created_at=1.0,
    )
    rules = RootRunSessions(events)
    assert rules.collect(run) == {"pl": REF}
    assert RootRunSessions(None).collect(run) == {}
    assert rules.prune({"pl": REF, "t/a": REF}, ["pl", "t"]) == {"pl": REF}


def test_memory_runs_filters_by_root() -> None:
    runs = MemoryRuns()
    for rid, root in (("root", None), ("kid", "root")):
        runs.save(
            Run(
                id=rid,
                graph_id="g",
                graph_version="v",
                status="completed",
                input={},
                origin="chat",
                root_run_id=root,
                created_at=1.0 if root is None else 2.0,
            )
        )
    assert [r.id for r in runs.list(root_run_id="root")] == ["kid"]
