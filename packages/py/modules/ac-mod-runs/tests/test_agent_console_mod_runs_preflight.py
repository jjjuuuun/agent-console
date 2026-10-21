"""mod-runs 사전 점검 확장 지점(5.2R.4): 준비자의 선택 메서드 ``preflight``.

모듈은 오류 코드·백엔드 이름을 모른다. 준비자가 돌려준 ``ErrorInfo``를 그대로(코드·문구·상세·해결
버튼) 오류 응답으로 내고, Run을 만들지 않는다. ``preflight``가 없는 준비자(이전 형식)는 그대로 돈다.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    Agent,
    ErrorInfo,
    Fix,
    FixAction,
    FixTarget,
    Graph,
    Issue,
)
from agent_console_mod_runs import (
    ERROR_MAP,
    RUN_PREPARERS,
    RUN_SERVICES,
    RUNS_STARTER,
    RunEnvironment,
    RunPreflight,
    RunPreflightError,
    RunPreparation,
    RunService,
    module,
)
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import BaseServices, Module, ModuleContext, ModuleParts, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_nodes_core import AGENT_LOOKUP, RUN_FILES_ROOT, WORKING_DIRECTORY
from agent_console_runtime import Registries, ServiceKey, Services, load_registries
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

API = "/api/v1"
TOKEN = "t" * 32
CODE = "zz.preflight"  # 임의 코드: 모듈은 코드 이름을 모른다


def _graph() -> dict[str, Any]:
    def edge(eid: str, src: tuple[str, str], dst: tuple[str, str], kind: str) -> dict[str, Any]:
        return {
            "id": eid,
            "source": {"node": src[0], "port": src[1]},
            "target": {"node": dst[0], "port": dst[1]},
            "kind": kind,
        }

    return {
        "id": "flow",
        "name": "흐름",
        "nodes": [
            {"id": "you", "type": "user"},
            {"id": "a", "type": "agent", "config": {"agent_ref": "fast"}},
        ],
        "edges": [
            edge("m1", ("you", "says"), ("a", "in"), "message"),
            edge("r1", ("a", "out"), ("you", "hears"), "reply"),
        ],
    }


class _Services:
    def __init__(self, store: FileDefinitionStore) -> None:
        self.store = store

    def services(self, env: RunEnvironment) -> Mapping[ServiceKey[Any], Any]:
        def find(agent_id: str) -> Agent | None:
            return Agent.model_validate(self.store.get("agent", agent_id).document)

        return {
            AGENT_LOOKUP: find,
            WORKING_DIRECTORY: str(env.working_directory),
            RUN_FILES_ROOT: str(env.run_files_root),
        }


class _Plain:
    """``preflight`` 없는 준비자(이전 형식)."""

    def check(
        self, graph: Graph, engine_issues: Sequence[Issue], services: Services, *, strict: bool
    ) -> list[Issue]:
        return []

    def prepare(self, graph: Graph, services: Services) -> RunPreparation:
        return RunPreparation()


class _Gate(_Plain):
    """``preflight``로 막거나(``error``) 통과시키는 준비자."""

    def __init__(self, error: ErrorInfo | None = None, *, fail: bool = False) -> None:
        self.error = error
        self.fail = fail
        self.calls = 0

    def preflight(self, graph: Graph, services: Services) -> ErrorInfo | None:
        self.calls += 1
        if self.fail:
            raise RuntimeError("점검 계산 실패")
        return self.error


def _error() -> ErrorInfo:
    return ErrorInfo(
        code=CODE,
        message="'응답자'를 고칠 곳이 있습니다",
        details={"nodes": [{"id": "a", "label": "응답자"}]},
        fix=Fix(actions=[FixAction(label="고치기", target=FixTarget(role="r-x"), focus="/k")]),
    )


@contextmanager
def _client(tmp_path: Path, *preparers: Any) -> Iterator[tuple[TestClient, RunService]]:
    ws = tmp_path / "ws"
    store = FileDefinitionStore(ws, DEFAULT_KINDS)
    store.create(
        "agent",
        {
            "id": "fast",
            "name": "fast",
            "backend": "fake",
            "backend_options": {"default": {"response": "ok"}},
        },
    )
    store.create("graph", _graph())

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(RUN_SERVICES, _Services(store))
        for preparer in preparers:
            ctx.provide(RUN_PREPARERS, preparer)
        return ModuleParts()

    providers: Module = fake_module(
        "test-providers", kind="link", provides=[RUN_SERVICES, RUN_PREPARERS], on_build=build
    )
    registries = Registries()
    load_registries(registries)
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=ws, state=tmp_path / "state"),
        registries=registries,
    )
    assembly = assemble([module, local_definitions_module(), providers], base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status={CODE: 422})
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        starter = assembly.port(RUNS_STARTER)
        assert isinstance(starter, RunService)
        yield client, starter


def _wait(client: TestClient, run_id: str) -> str:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status: str = client.get(f"{API}/runs/{run_id}").json()["run"]["status"]
        if status in {"completed", "failed", "cancelled", "interrupted"}:
            return status
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def test_preflight_error_is_reply_and_no_run_is_recorded(tmp_path: Path) -> None:
    gate = _Gate(_error())
    assert isinstance(gate, RunPreflight)
    assert not isinstance(_Plain(), RunPreflight)
    with _client(tmp_path, _Plain(), gate) as (client, starter):
        res = client.post(f"{API}/runs", json={"graph_id": "flow"})
        assert res.status_code == 422, res.text
        assert res.json() == {
            "error": {
                "code": CODE,
                "message": "'응답자'를 고칠 곳이 있습니다",
                "details": {"nodes": [{"id": "a", "label": "응답자"}]},
                "fix": {"actions": [{"label": "고치기", "target": {"role": "r-x"}, "focus": "/k"}]},
            }
        }
        assert client.get(f"{API}/runs").json() == []
        assert starter.preflight(starter.load_graph("flow")) == _error()
        # 검증 응답(check)은 사전 점검을 하지 않는다
        assert starter.check(starter.load_graph("flow")) == []


def test_preflight_pass_and_calc_failure_do_not_block(tmp_path: Path) -> None:
    passing, broken = _Gate(None), _Gate(fail=True)
    with _client(tmp_path, passing, broken) as (client, _starter):
        res = client.post(f"{API}/runs", json={"graph_id": "flow"})
        assert res.status_code == 202, res.text
        assert _wait(client, res.json()["id"]) == "completed"
        assert (passing.calls, broken.calls) == (1, 1)


def test_error_map_uses_contract_status_for_known_code() -> None:
    """``RunPreflightError``는 오류 맵에 있고, 상태는 호스트의 코드 → 상태 표가 정한다."""
    assert RunPreflightError in ERROR_MAP
    assert HTTP_STATUS_BY_ERROR_CODE["backend.unresolved"] == 422
