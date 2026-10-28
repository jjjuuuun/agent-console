"""mod-runs: 실행 경로·WS·재시작 복구·이어 가기 위임·준비자·노드 서비스·경고·꺼짐 404.

노드·백엔드는 설치된 entry point(``ac-nodes-core``·``ac-backend-fake-agent``, dev 의존)에서 읽는다.
에이전트 조회 같은 노드 서비스는 테스트용 공급 모듈이 ``runs.services``로 준다(통합 서버에서는
``link-runs-teams``).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_console_contracts import (
    Agent,
    DelegationSettings,
    FlowSettings,
    Graph,
    InteractionSettings,
    Issue,
    NodeRun,
    Run,
    RunEvent,
)
from agent_console_mod_runs import (
    DEFAULT_OBSERVE_EVENT_PREFIXES,
    INTERACTIONS_UPDATED,
    RESUME_HANDLERS,
    RUN_PREPARERS,
    RUN_SERVICES,
    RUNS_EVENT,
    RUNS_STARTER,
    SECRET_REDACT,
    SERVER_ATTRIBUTES,
    SERVER_WARNINGS,
    STORAGE_MEMORY,
    TEAM_RULES_UNAVAILABLE,
    RunEnvironment,
    RunPreparation,
    RunService,
    RunsModuleSettings,
    load_observe_event_prefixes,
    module,
    observe_event_prefixes_of,
)
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import (
    Assembly,
    BaseServices,
    Module,
    ModuleContext,
    ModuleParts,
    ModulesConfig,
    Paths,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_nodes_core import AGENT_LOOKUP, RUN_FILES_ROOT, WORKING_DIRECTORY
from agent_console_runtime import Registries, ResumeStart, ServiceKey, Services, load_registries
from agent_console_store import (
    DEFAULT_KINDS,
    FileDefinitionStore,
    SqliteDatabase,
    SqliteStorage,
)

API = "/api/v1"
TOKEN = "t" * 32
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})


def _registries() -> Registries:
    registries = Registries()
    load_registries(registries)
    return registries


def _graph(graph_id: str = "flow", agent_ref: str = "fast") -> dict[str, Any]:
    return {
        "id": graph_id,
        "name": "흐름",
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "a", "type": "agent", "label": "응답자", "config": {"agent_ref": agent_ref}},
        ],
        "edges": [
            {
                "id": "m1",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "a", "port": "in"},
                "kind": "message",
                "config": {},
            },
            {
                "id": "r1",
                "source": {"node": "a", "port": "out"},
                "target": {"node": "you", "port": "hears"},
                "kind": "reply",
                "config": {},
            },
        ],
    }


def _agent(agent_id: str = "fast") -> dict[str, Any]:
    return {
        "id": agent_id,
        "name": agent_id,
        "backend": "fake-agent",
        "backend_options": {"default": {"response": "답: $prompt"}},
    }


class _Services:
    """테스트용 ``runs.services``: 워크스페이스 파일에서 에이전트를 읽는다."""

    def __init__(self, store: FileDefinitionStore) -> None:
        self.store = store
        self.seen: list[RunEnvironment] = []

    def services(self, env: RunEnvironment) -> Mapping[ServiceKey[Any], Any]:
        self.seen.append(env)

        def find(agent_id: str) -> Agent | None:
            try:
                return Agent.model_validate(self.store.get("agent", agent_id).document)
            except Exception:
                return None

        return {
            AGENT_LOOKUP: find,
            WORKING_DIRECTORY: str(env.working_directory),
            RUN_FILES_ROOT: str(env.run_files_root),
        }


class _Preparer:
    """테스트용 준비자: ``block``이면 차단 이슈, 아니면 경고 하나와 상호작용 설정."""

    def __init__(
        self,
        *,
        block: bool = False,
        fail: bool = False,
        flow: FlowSettings | None = None,
        delegation: DelegationSettings | None = None,
    ) -> None:
        self.block = block
        self.fail = fail
        self.flow = flow
        self.delegation = delegation
        self.prepared: list[str] = []

    def check(
        self, graph: Graph, engine_issues: Sequence[Issue], services: Services, *, strict: bool
    ) -> list[Issue]:
        if self.fail:
            raise RuntimeError("검사 실패")
        if self.block:
            return [Issue(severity="error", code="test.rule", message="규칙")]
        return [Issue(severity="warning", code="test.rule", message="규칙")]

    def prepare(self, graph: Graph, services: Services) -> RunPreparation:
        self.prepared.append(graph.id)
        return RunPreparation(
            interaction_settings=InteractionSettings(),
            flow_settings=self.flow,
            delegation_settings=self.delegation,
        )


def _providers(workspace: Path, *, preparer: _Preparer | None = None) -> Module:
    store = FileDefinitionStore(workspace, DEFAULT_KINDS)

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(RUN_SERVICES, _Services(store))
        if preparer is not None:
            ctx.provide(RUN_PREPARERS, preparer)
        return ModuleParts()

    return fake_module(
        "test-providers", kind="link", provides=[RUN_SERVICES, RUN_PREPARERS], on_build=build
    )


def _seed(workspace: Path) -> None:
    store = FileDefinitionStore(workspace, DEFAULT_KINDS)
    store.create("agent", _agent())
    store.create("graph", _graph())


def _base(tmp_path: Path, database: SqliteDatabase | None) -> BaseServices:
    return BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        database=database,
        registries=_registries(),
        environ={"MY_SECRET": "sekret-value-zz9"},
    )


@contextmanager
def _client(
    tmp_path: Path,
    *extra: Module,
    database: SqliteDatabase | None = None,
    config: ModulesConfig | None = None,
) -> Iterator[tuple[TestClient, Assembly]]:
    assembly = assemble(
        [module, local_definitions_module(), *extra], config, base=_base(tmp_path, database)
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, assembly


def _starter(assembly: Assembly) -> RunService:
    found = assembly.port(RUNS_STARTER)
    assert isinstance(found, RunService)
    return found


def _wait(client: TestClient, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        snap: dict[str, Any] = client.get(f"{API}/runs/{run_id}").json()
        if snap["run"]["status"] in TERMINAL:
            return snap
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def test_run_starts_with_injected_services_and_lists(tmp_path: Path) -> None:
    _seed(tmp_path / "ws")
    with _client(tmp_path, _providers(tmp_path / "ws")) as (client, _assembly):
        response = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"text": "안녕"}})
        assert response.status_code == 202, response.text
        run_id = response.json()["id"]
        snap = _wait(client, run_id)
        assert snap["run"]["status"] == "completed"
        assert [r["id"] for r in client.get(f"{API}/runs").json()] == [run_id]
        events = client.get(f"{API}/runs/{run_id}/events").json()
        assert events[0]["type"] == "run.created"
        assert client.get(f"{API}/agents/fast/activity").json()
        node_types = {d["id"] for d in client.get(f"{API}/node-types").json()}
        assert {"user", "agent"} <= node_types
        assert client.get(f"{API}/backends/fake-agent/models").status_code == 200
        assert client.get(f"{API}/backends/nope/models").status_code == 404
        assert client.get(f"{API}/runs/missing").status_code == 404
        assert client.get(f"{API}/runs/missing/events").status_code == 404
        assert client.post(f"{API}/runs", json={"graph_id": "nope"}).status_code == 404


def test_project_id_is_stored_and_runs_listed_by_project_and_root_only(tmp_path: Path) -> None:
    """5.2R.32: ``project_id`` 저장, ``?project=``·``?root_only=`` 거르기(불투명 문자열)."""
    _seed(tmp_path / "ws")
    with _client(tmp_path, _providers(tmp_path / "ws")) as (client, _assembly):
        body = {"graph_id": "flow", "input": {"text": "안녕"}}
        inside = client.post(f"{API}/runs", json={**body, "project_id": "p1"})
        assert inside.status_code == 202, inside.text
        assert inside.json()["project_id"] == "p1"
        plain = client.post(f"{API}/runs", json=body).json()
        assert plain["project_id"] is None
        for run_id in (inside.json()["id"], plain["id"]):
            _wait(client, run_id)
        stored = client.get(f"{API}/runs/{inside.json()['id']}").json()["run"]
        assert stored["project_id"] == "p1"

        def ids(**q: str) -> list[str]:
            return [r["id"] for r in client.get(f"{API}/runs", params=q).json()]

        assert ids(project="p1") == [inside.json()["id"]]
        assert ids(project="p1", root_only="true") == [inside.json()["id"]]
        assert ids(project="zzz") == []
        assert set(ids(root_only="true")) == {inside.json()["id"], plain["id"]}


@pytest.mark.parametrize("sqlite", [False, True])
def test_assign_project_and_counts_routes(tmp_path: Path, sqlite: bool) -> None:
    """5.7R.33j: ``GET /runs/project-counts``·``POST /runs/assign-project``."""
    _seed(tmp_path / "ws")
    db = SqliteDatabase.open(tmp_path / "c.sqlite3") if sqlite else None
    with _client(tmp_path, _providers(tmp_path / "ws"), database=db) as (client, _assembly):
        body = {"graph_id": "flow", "input": {"text": "안녕"}}
        a = client.post(f"{API}/runs", json=body).json()["id"]
        b = client.post(f"{API}/runs", json={**body, "project_id": "p1"}).json()["id"]
        _wait(client, a)
        _wait(client, b)
        counts = client.get(f"{API}/runs/project-counts")
        assert counts.status_code == 200, counts.text
        assert counts.json() == {"total": 2, "no_project": 1, "by_project": {"p1": 1}}
        assert client.post(f"{API}/runs/assign-project", json={"to": "p2"}).status_code in (
            400,
            422,
        )
        res = client.post(f"{API}/runs/assign-project", json={"to": "p2", "from_null": True})
        assert res.json() == {"assigned": 1, "skipped": []}
        assert client.get(f"{API}/runs/{a}").json()["run"]["project_id"] == "p2"
        assert client.get(f"{API}/runs/{b}").json()["run"]["project_id"] == "p1"
        res = client.post(f"{API}/runs/assign-project", json={"to": "p2", "ids": [b, "nope"]})
        assert res.json()["assigned"] == 1
        assert [s["reason"] for s in res.json()["skipped"]] == ["not_found"]
        assert client.get(f"{API}/runs", params={"project": "p2"}).json()
        assert client.get(f"{API}/runs/project-counts").json()["by_project"] == {"p2": 2}
    if db is not None:
        db.close()


def test_engine_only_without_preparers_warns_team_rules_unavailable(tmp_path: Path) -> None:
    """준비자(팀 규칙)가 없으면 엔진 검증만으로 실행하고 ``team.rules_unavailable``을 낸다."""
    _seed(tmp_path / "ws")
    with _client(tmp_path, _providers(tmp_path / "ws")) as (client, assembly):
        codes = [i.code for source in assembly.ports(SERVER_WARNINGS) for i in source()]
        assert TEAM_RULES_UNAVAILABLE in codes
        assert STORAGE_MEMORY in codes  # DB 핸들 없음 → 메모리
        run_id = client.post(f"{API}/runs", json={"graph_id": "flow"}).json()["id"]
        assert _wait(client, run_id)["run"]["status"] == "completed"


def test_preparers_block_and_prepare(tmp_path: Path) -> None:
    _seed(tmp_path / "ws")
    blocking = _Preparer(block=True)
    with _client(tmp_path, _providers(tmp_path / "ws", preparer=blocking)) as (client, assembly):
        response = client.post(f"{API}/runs", json={"graph_id": "flow"})
        assert response.status_code == 422
        assert [i["code"] for i in response.json()["error"]["details"]["issues"]] == ["test.rule"]
        assert blocking.prepared == []
        codes = [i.code for source in assembly.ports(SERVER_WARNINGS) for i in source()]
        assert TEAM_RULES_UNAVAILABLE not in codes
    passing = _Preparer()
    with _client(tmp_path, _providers(tmp_path / "ws", preparer=passing)) as (client, assembly):
        run_id = client.post(f"{API}/runs", json={"graph_id": "flow"}).json()["id"]
        assert _wait(client, run_id)["run"]["status"] == "completed"
        assert passing.prepared == ["flow"]
        starter = _starter(assembly)
        assert isinstance(starter, RunService)
        graph = starter.load_graph("flow")
        assert [i.code for i in starter.check(graph)] == ["test.rule"]


def test_preparer_flow_settings_reach_engine(tmp_path: Path) -> None:
    """준비자의 반복·실행 한도(`flow_settings`, 5R.5)·위임 설정(`delegation_settings`, 5R.6)이
    `GraphRuntime.start`로 간다."""
    _seed(tmp_path / "ws")
    flow = FlowSettings(max_iterations=2, max_node_runs=7)
    delegation = DelegationSettings(max_depth=2)
    preparer = _Preparer(flow=flow, delegation=delegation)
    with _client(tmp_path, _providers(tmp_path / "ws", preparer=preparer)) as (client, assembly):
        starter = _starter(assembly)
        assert isinstance(starter, RunService)
        runtime = starter.runtime
        seen: list[Any] = []
        original = runtime.start

        async def spy(*args: Any, **kwargs: Any) -> Any:
            seen.append((kwargs.get("flow_settings"), kwargs.get("delegation_settings")))
            return await original(*args, **kwargs)

        runtime.start = spy  # type: ignore[method-assign]
        run_id = client.post(f"{API}/runs", json={"graph_id": "flow"}).json()["id"]
        assert _wait(client, run_id)["run"]["status"] == "completed"
        assert seen == [(flow, delegation)]


def test_preparer_error_blocks_start_but_not_check(tmp_path: Path) -> None:
    _seed(tmp_path / "ws")
    with _client(tmp_path, _providers(tmp_path / "ws", preparer=_Preparer(fail=True))) as (
        client,
        assembly,
    ):
        starter = _starter(assembly)
        assert starter.check(starter.load_graph("flow")) == []  # 검증 응답은 기록하고 넘어간다
        with pytest.raises(RuntimeError, match="검사 실패"):  # 검사 없이 시작하지 않는다
            client.post(f"{API}/runs", json={"graph_id": "flow"})
        assert client.get(f"{API}/runs").json() == []


def test_topics_and_websocket(tmp_path: Path) -> None:
    _seed(tmp_path / "ws")
    with _client(tmp_path, _providers(tmp_path / "ws")) as (client, assembly):
        seen: list[RunEvent] = []
        assembly.services.events.subscribe(RUNS_EVENT, seen.append)
        updates: list[Any] = []
        assembly.services.events.subscribe(INTERACTIONS_UPDATED, updates.append)
        run_id = client.post(f"{API}/runs", json={"graph_id": "flow"}).json()["id"]
        with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
            ws.send_json({"type": "subscribe", "payload": {"topic": f"run:{run_id}"}})
            types: list[str] = []
            for _ in range(200):
                message = ws.receive_json()
                if message.get("type") == "run.event":
                    types.append(message["payload"]["type"])
                    if message["payload"]["type"] == "run.completed":
                        break
            assert types[0] == "run.created"
            assert types[-1] == "run.completed"
            ws.send_json({"type": "subscribe", "payload": {"topic": "run:nope"}})
            error = ws.receive_json()
            assert error["payload"]["code"] == "not_found"
        assert {e.type for e in seen} >= {"run.created", "run.completed"}
        assert all(e.run_id == run_id for e in seen)


def test_recovery_runs_first_and_attribute(tmp_path: Path) -> None:
    """시작할 때 이전 프로세스의 미종료 Run을 끊김으로 정리한다(가장 먼저, design §R14.5)."""
    database = SqliteDatabase.open(tmp_path / "state" / "console.sqlite3")
    database.upgrade()
    storage = SqliteStorage(database.engine)
    storage.runs.save(
        Run(
            id="old",
            graph_id="flow",
            graph_version="v",
            status="running",
            input={},
            origin="api",
            created_at=1.0,
        )
    )
    storage.runs.save_node_run(
        NodeRun(run_id="old", node_id="a", status="running", attempt=1, started_at=1.0)
    )
    _seed(tmp_path / "ws")
    with _client(tmp_path, _providers(tmp_path / "ws"), database=database) as (client, assembly):
        snap = client.get(f"{API}/runs/old").json()
        assert snap["run"]["status"] == "interrupted"
        attrs: dict[str, Any] = {}
        for source in assembly.ports(SERVER_ATTRIBUTES):
            attrs.update(source())
        assert attrs == {"recovered_runs": 1}
        codes = [i.code for source in assembly.ports(SERVER_WARNINGS) for i in source()]
        assert STORAGE_MEMORY not in codes
        options = client.get(f"{API}/runs/old/resume-options").json()
        assert options["run_id"] == "old"
    database.close()


class _Handler:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def accepts(self, run: Run) -> bool:
        return run.origin == "chat"

    async def resume(self, request: ResumeStart) -> Run:
        self.calls.append(request.run.id)
        return request.run.model_copy(update={"id": "resumed-by-handler"})


def test_resume_delegates_to_handlers(tmp_path: Path) -> None:
    """이어 가기는 받는 처리기(``runs.resume_handlers``)에 맡기고, 없으면 일반 실행으로 시작한다."""
    handler = _Handler()

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(RESUME_HANDLERS, handler)
        return ModuleParts()

    handlers = fake_module("test-handlers", kind="link", provides=[RESUME_HANDLERS], on_build=build)
    _seed(tmp_path / "ws")
    with _client(tmp_path, _providers(tmp_path / "ws"), handlers) as (_http, assembly):
        starter = _starter(assembly)
        graph = starter.load_graph("flow")
        base = Run(
            id="r0",
            graph_id="flow",
            graph_version="v",
            status="interrupted",
            input={},
            origin="chat",
            created_at=1.0,
        )
        chat = asyncio.run(starter._start_resumed(ResumeStart(run=base, graph=graph, seed={})))
        assert chat.id == "resumed-by-handler"
        assert handler.calls == ["r0"]


def test_secret_redact_port(tmp_path: Path) -> None:
    with _client(tmp_path) as (_http, assembly):
        redact = assembly.port(SECRET_REDACT)
        assert redact is not None
        starter = _starter(assembly)
        assert redact("값 sekret-value-zz9") == "값 sekret-value-zz9"  # 아직 해석한 적 없음
        starter.runtime._settings.secrets.resolve("MY_SECRET")
        assert redact("값 sekret-value-zz9") == "값 [REDACTED]"


def test_disabled_module_routes_are_404(tmp_path: Path) -> None:
    with _client(tmp_path, config=ModulesConfig(disabled=["mod-runs"])) as (client, _assembly):
        assert client.get(f"{API}/runs").status_code == 404
        assert client.get(f"{API}/node-types").status_code == 404
        assert client.get(f"{API}/interactions").status_code == 404


def test_requires_definitions_lookup() -> None:
    assembly = assemble([module], base=BaseServices(registries=_registries()))
    [report] = assembly.report
    assert report.state.value == "unsatisfied"
    assert report.missing == ("definitions.lookup",)


def test_settings_schema_rejects_unknown_keys() -> None:
    config = ModulesConfig(options={"mod-runs": {"nope": 1}})
    assembly = assemble([module, local_definitions_module()], config)
    assert assembly.status("mod-runs").state.value == "failed"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_shutdown_is_idempotent(tmp_path: Path) -> None:
    assembly = assemble([module, local_definitions_module()], base=_base(tmp_path, None))
    await assembly.start()
    starter = _starter(assembly)
    assert starter is not None
    await starter.shutdown()
    await starter.shutdown()
    await assembly.stop()


def test_recovery_precedes_dependent_module_startup(tmp_path: Path) -> None:
    """QA 3R.13: ``runs.reader``를 쓰는 다른 모듈의 시작 훅이 돌 때는 이미 복구가 끝나 있다."""
    from agent_console_mod_runs import RUNS_READER

    database = SqliteDatabase.open(tmp_path / "state" / "console.sqlite3")
    database.upgrade()
    SqliteStorage(database.engine).runs.save(
        Run(
            id="old",
            graph_id="flow",
            graph_version="v",
            status="running",
            input={},
            origin="api",
            created_at=1.0,
        )
    )
    seen: list[str] = []

    def build(ctx: ModuleContext) -> ModuleParts:
        reader = ctx.port(RUNS_READER)

        async def start() -> None:
            assert reader is not None
            seen.append(reader.get("old").status)

        return ModuleParts(startup=[start])

    probe = fake_module("probe-after-runs", kind="link", requires=[RUNS_READER], on_build=build)
    # probe를 목록 맨 앞에 두어도 의존 순서가 우선해야 한다
    assembly = assemble(
        [probe, module, local_definitions_module()], None, base=_base(tmp_path, database)
    )
    app = create_host_app(
        assembly, policy=SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["t"])
    )
    with TestClient(app):
        pass
    assert seen == ["interrupted"]
    database.close()


# ---------------------------------------------------------------- 관측 탭 이벤트 접두어(5.5R.13)


def test_observe_event_prefixes_default_comes_from_package_data(tmp_path: Path) -> None:
    """옵션이 없으면 패키지 기본 데이터(``data/observe_event_prefixes.json``)를 낸다."""
    with _client(tmp_path) as (client, _assembly):
        response = client.get(f"{API}/observe-event-prefixes")
        assert response.status_code == 200
        assert response.json() == list(DEFAULT_OBSERVE_EVENT_PREFIXES) == ["hook.", "mcp."]


def test_observe_event_prefixes_option_replaces_response(tmp_path: Path) -> None:
    """옵션을 바꾸면 응답이 바뀐다(공백·빈 값·중복은 정리)."""
    config = ModulesConfig(
        options={"mod-runs": {"observe_event_prefixes": ["otel.", " hook. ", "", "otel."]}}
    )
    with _client(tmp_path, config=config) as (client, _assembly):
        assert client.get(f"{API}/observe-event-prefixes").json() == ["otel.", "hook."]


def test_observe_event_prefixes_off_keeps_runs_working(tmp_path: Path) -> None:
    """빈 목록 = 끔: 응답은 빈 목록이고 실행·이벤트·디스크립터는 그대로 동작한다."""
    _seed(tmp_path / "ws")
    config = ModulesConfig(options={"mod-runs": {"observe_event_prefixes": []}})
    with _client(tmp_path, _providers(tmp_path / "ws"), config=config) as (client, _assembly):
        assert client.get(f"{API}/observe-event-prefixes").json() == []
        response = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"text": "안녕"}})
        assert response.status_code == 202, response.text
        run_id = response.json()["id"]
        assert _wait(client, run_id)["run"]["status"] == "completed"
        events = client.get(f"{API}/runs/{run_id}/events").json()
        assert events[0]["type"] == "run.created"
        assert client.get(f"{API}/node-types").status_code == 200


def test_observe_event_prefixes_settings_schema() -> None:
    """설정: None = 기본, 목록은 정리, 문자열 아닌 값은 거부, 스키마에 라벨·설명·x-ui."""
    assert RunsModuleSettings().observe_event_prefixes is None
    assert RunsModuleSettings(observe_event_prefixes=[" a.", "a.", " "]).observe_event_prefixes == [
        "a."
    ]
    with pytest.raises(ValidationError):
        RunsModuleSettings.model_validate({"observe_event_prefixes": [1]})
    field = RunsModuleSettings.model_json_schema()["properties"]["observe_event_prefixes"]
    assert field["title"]
    assert field["description"]
    assert "x-ui" in field


def test_observe_event_prefix_data_helpers(tmp_path: Path) -> None:
    """표 파일 읽기(교체용)와 옵션 해석은 서버 없이 쓸 수 있다."""
    assert load_observe_event_prefixes('{"prefixes": ["x.", " ", "x.", "y."]}') == ("x.", "y.")
    assert load_observe_event_prefixes("{}") == ()
    with pytest.raises(ValueError, match="목록"):
        load_observe_event_prefixes('{"prefixes": "hook."}')
    with pytest.raises(ValueError, match="객체"):
        load_observe_event_prefixes("[]")
    with pytest.raises(ValueError, match="문자열"):
        load_observe_event_prefixes('{"prefixes": [1]}')
    assert observe_event_prefixes_of(None) == DEFAULT_OBSERVE_EVENT_PREFIXES
    assert observe_event_prefixes_of([]) == ()
    assert observe_event_prefixes_of(["z."]) == ("z.",)
