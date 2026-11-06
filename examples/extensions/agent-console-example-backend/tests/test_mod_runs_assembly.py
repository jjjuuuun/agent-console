"""예제를 설치한 조립(테스트 호스트 + 실행 모듈 ``mod-runs``): entry point로 로드 →
``/backends``에 보임(설치자 설정이 능력을 바꿈) → 팀 실행 완료 → 제거하면 목록에서 사라지고
남은 설정·에이전트에 경고.

entry point는 설치 대신 ``importlib.metadata.EntryPoint``를 만들어 레지스트리 로더에 주입한다
(설치한 서버의 호스트 플러그인 로더가 하는 일과 같다). 에이전트 조회 같은 노드 서비스는 작은 공급
모듈이 ``runs.services``로 준다(통합 서버에서는 팀 연동 모듈이 준다).
"""

from __future__ import annotations

import importlib.metadata
import json
import logging
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import Agent
from agent_console_example_backend import BACKEND_ID
from agent_console_mod_runs import RUN_SERVICES, RunEnvironment, module
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import BaseServices, ModuleContext, ModuleParts, ModulesConfig, Paths
from agent_console_modkit import assemble as assemble_modules
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_nodes_core import AGENT_LOOKUP, RUN_FILES_ROOT, WORKING_DIRECTORY
from agent_console_runtime import (
    BACKENDS_GROUP,
    DELEGATION_STRATEGIES_GROUP,
    EDGE_TYPES_GROUP,
    NODE_TYPES_GROUP,
    Registries,
    ServiceKey,
    load_registries,
)
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

API = "/api/v1"
TOKEN = "t" * 32
SECRET = "sekret-value-zz9"
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})
GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP)
EXAMPLE = importlib.metadata.EntryPoint(
    name=BACKEND_ID, value="agent_console_example_backend:ScriptedBackend", group=BACKENDS_GROUP
)
AGENT = {
    "id": "bot",
    "name": "봇",
    "backend": BACKEND_ID,
    "backend_options": {
        "rules": [{"contains": "안녕", "reply": "반가워요($turn)"}],
        "default_reply": "받음: $prompt",
    },
}
GRAPH = {
    "id": "flow",
    "name": "흐름",
    "nodes": [
        {"id": "you", "type": "user", "label": "나"},
        {"id": "a", "type": "agent", "label": "응답자", "config": {"agent_ref": "bot"}},
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


def _registries(*, installed: bool) -> Registries:
    core = importlib.metadata.distribution("agent-console-nodes-core").entry_points
    eps = [ep for ep in core if ep.group in GROUPS]
    registries = Registries()
    reports = load_registries(registries, entry_points=[*eps, *([EXAMPLE] if installed else [])])
    assert all(r.ok for r in reports), reports
    return registries


class _Services:
    """``runs.services``: 워크스페이스 파일에서 에이전트를 읽는다."""

    def __init__(self, store: FileDefinitionStore) -> None:
        self.store = store

    def services(self, env: RunEnvironment) -> Mapping[ServiceKey[Any], Any]:
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


@contextmanager
def _client(tmp_path: Path, *, installed: bool) -> Iterator[TestClient]:
    workspace = tmp_path / "ws"
    store = FileDefinitionStore(workspace, DEFAULT_KINDS)

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(RUN_SERVICES, _Services(store))
        return ModuleParts()

    providers = fake_module("test-providers", kind="link", provides=[RUN_SERVICES], on_build=build)
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=workspace, state=tmp_path / "state"),
        registries=_registries(installed=installed),
        environ={"TOKEN": SECRET},
    )
    # 설치자 설정: 이 백엔드의 세션 기록 폴더(상대 경로 = 앱 workspace 기준). 제거 뒤에도 남는다.
    options = {"backends": {BACKEND_ID: {"session_dir": "scripted-sessions"}}}
    config = ModulesConfig(options={"mod-runs": options})
    assembly = assemble_modules([module, local_definitions_module(), providers], config, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


def _seed(tmp_path: Path) -> None:
    store = FileDefinitionStore(tmp_path / "ws", DEFAULT_KINDS)
    store.create("agent", AGENT)
    store.create("graph", GRAPH)


def _wait(client: TestClient, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        snap: dict[str, Any] = client.get(f"{API}/runs/{run_id}").json()
        if snap["run"]["status"] in TERMINAL:
            return snap
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def test_installed_backend_is_listed_and_runs_a_team(tmp_path: Path) -> None:
    _seed(tmp_path)
    with _client(tmp_path, installed=True) as client:
        listed = {b["id"]: b for b in client.get(f"{API}/backends").json()}
        assert BACKEND_ID in listed
        mine = listed[BACKEND_ID]
        assert mine["ui_hints"]["badge"] == "예제"
        assert mine["capabilities"]["streaming"] is True
        assert mine["capabilities"]["resume"] is True  # 설치자 설정(session_dir)이 훅으로 들어갔다
        assert client.get(f"{API}/backends/{BACKEND_ID}/models").json() == []

        started = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"text": "안녕"}})
        assert started.status_code == 202, started.text
        run_id = started.json()["id"]
        assert _wait(client, run_id)["run"]["status"] == "completed"
        events = client.get(f"{API}/runs/{run_id}/events").json()
        replies = [e["payload"]["text"] for e in events if e["type"] == "run.reply"]
        assert replies == ["반가워요(1)"]

        # 세션 기록은 workspace 아래 설정한 폴더에 쌓이고, 이벤트에는 경로·비밀 값이 없다.
        assert list((tmp_path / "ws" / "scripted-sessions").rglob("*.jsonl"))
        dumped = json.dumps(events, ensure_ascii=False)
        assert SECRET not in dumped
        assert "scripted-sessions" not in dumped


def test_removed_backend_disappears_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _seed(tmp_path)
    with caplog.at_level(logging.WARNING), _client(tmp_path, installed=False) as client:
        assert BACKEND_ID not in {b["id"] for b in client.get(f"{API}/backends").json()}
        assert client.get(f"{API}/backends/{BACKEND_ID}/models").status_code == 404
        # 남은 설치자 설정: 서버는 시작하고 경고만 남긴다.
        assert any(
            BACKEND_ID in r.getMessage() and "등록되어 있지 않습니다" in r.getMessage()
            for r in caplog.records
        )
        # 이 백엔드를 고른 에이전트: 노드가 "등록되지 않은 실행 백엔드"로 실패한다(나머지는 정상).
        started = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"text": "안녕"}})
        assert started.status_code == 202, started.text
        snap = _wait(client, started.json()["id"])
        assert snap["run"]["status"] == "failed"
        assert "agent.unknown_backend" in json.dumps(snap, ensure_ascii=False)
