"""숨긴 실행 백엔드(5.2R.105): 개발·테스트용 백엔드는 기본으로 숨김 표시, 설치자 설정으로 보인다.

- 백엔드가 디스크립터 ``ui_hints.hidden``으로 선언한다(모듈은 백엔드 이름을 모른다).
- ``show_hidden_backends``(환경변수 ``<접두어>SHOW_HIDDEN_BACKENDS``)를 켜면 숨김을 푼 사본을 낸다.
- 옛 id ``fake``는 별칭 없이 없앴다: 저장 데이터에 남아 있으면 "등록되지 않은 실행 백엔드" 오류.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_backend_fake_agent import FakeBackend
from agent_console_contracts import Agent, BackendDescriptor, UiHints
from agent_console_mod_runs import (
    RUN_SERVICES,
    RunEnvironment,
    RunsModuleSettings,
    module,
    reveal_hidden_backends,
)
from agent_console_mod_runs.settings import SETTINGS_COMPAT
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import (
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
from agent_console_runtime import Registries, ServiceKey, load_registries
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

API = "/api/v1"
TOKEN = "t" * 32
FAKE_AGENT = "fake-agent"


def _providers(workspace: Path) -> Module:
    store = FileDefinitionStore(workspace, DEFAULT_KINDS)

    class _Services:
        def services(self, env: RunEnvironment) -> Mapping[ServiceKey[Any], Any]:
            def find(agent_id: str) -> Agent | None:
                return Agent.model_validate(store.get("agent", agent_id).document)

            return {
                AGENT_LOOKUP: find,
                WORKING_DIRECTORY: str(env.working_directory),
                RUN_FILES_ROOT: str(env.run_files_root),
            }

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(RUN_SERVICES, _Services())
        return ModuleParts()

    return fake_module("test-providers", kind="link", provides=[RUN_SERVICES], on_build=build)


@contextmanager
def _client(tmp_path: Path, *extra: Module, show: bool | None = None) -> Iterator[TestClient]:
    registries = Registries()
    load_registries(registries)
    options = {} if show is None else {"mod-runs": {"show_hidden_backends": show}}
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=registries,
    )
    assembly = assemble(
        [module, local_definitions_module(), *extra], ModulesConfig(options=options), base=base
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


def _fake_agent(client: TestClient) -> dict[str, Any]:
    found: dict[str, dict[str, Any]] = {d["id"]: d for d in client.get(f"{API}/backends").json()}
    assert "fake" not in found  # 옛 id는 별칭 없이 없앴다
    return found[FAKE_AGENT]


def test_fake_agent_is_hidden_by_default(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        fake = _fake_agent(client)
        assert fake["title"] == "가짜 에이전트(테스트용)"
        assert fake["ui_hints"]["hidden"] is True
        # 숨김은 화면 선택지·설정 카드용 표시일 뿐, 조회 경로는 그대로 쓴다
        assert client.get(f"{API}/backends/{FAKE_AGENT}/models").status_code == 200


def test_show_hidden_backends_reveals(tmp_path: Path) -> None:
    with _client(tmp_path, show=True) as client:
        fake = _fake_agent(client)
        assert fake["ui_hints"]["hidden"] is False
        assert fake["ui_hints"]["badge"]  # 다른 힌트는 그대로


def test_env_setting_maps_to_option() -> None:
    env = {e.name: e.path for e in SETTINGS_COMPAT.env}
    assert env["SHOW_HIDDEN_BACKENDS"] == ("show_hidden_backends",)
    assert RunsModuleSettings.model_validate({"show_hidden_backends": "1"}).show_hidden_backends
    assert RunsModuleSettings().show_hidden_backends is False


def _backend(backend_id: str, *, hidden: bool | None) -> FakeBackend:
    backend = FakeBackend(backend_id=backend_id)
    hints = None if hidden is None else UiHints(hidden=hidden)
    backend.descriptor = backend.descriptor.model_copy(update={"ui_hints": hints})
    return backend


class _ReadOnly(FakeBackend):
    """디스크립터를 바꿀 수 없는 백엔드(읽기 전용 속성)."""

    @property
    def descriptor(self) -> BackendDescriptor:
        return BackendDescriptor(id="ro", title="ro", ui_hints=UiHints(hidden=True))

    @descriptor.setter
    def descriptor(self, value: BackendDescriptor) -> None:
        if hasattr(self, "_ready"):
            raise AttributeError("읽기 전용")
        self._ready = True


def test_reveal_hidden_backends_only_touches_hidden(caplog: pytest.LogCaptureFixture) -> None:
    regs = Registries()
    regs.backends.register("dev", _backend("dev", hidden=True))
    regs.backends.register("plain", _backend("plain", hidden=None))
    regs.backends.register("shown", _backend("shown", hidden=False))
    regs.backends.register("ro", _ReadOnly())
    assert reveal_hidden_backends(regs) == ["dev"]
    dev_hints = regs.backends.get("dev").descriptor.ui_hints
    assert dev_hints is not None
    assert dev_hints.hidden is False
    assert regs.backends.get("plain").descriptor.ui_hints is None
    assert "ro" in caplog.text


def test_old_fake_id_is_unknown_backend(tmp_path: Path) -> None:
    store = FileDefinitionStore(tmp_path / "ws", DEFAULT_KINDS)
    store.create("agent", {"id": "old", "name": "old", "backend": "fake"})
    store.create(
        "graph",
        {
            "id": "g",
            "name": "g",
            "nodes": [
                {"id": "you", "type": "user"},
                {"id": "a", "type": "agent", "config": {"agent_ref": "old"}},
            ],
            "edges": [
                {
                    "id": "m1",
                    "source": {"node": "you", "port": "says"},
                    "target": {"node": "a", "port": "in"},
                    "kind": "message",
                },
                {
                    "id": "r1",
                    "source": {"node": "a", "port": "out"},
                    "target": {"node": "you", "port": "hears"},
                    "kind": "reply",
                },
            ],
        },
    )
    with _client(tmp_path, _providers(tmp_path / "ws")) as client:
        res = client.post(f"{API}/runs", json={"graph_id": "g", "input": {"text": "hi"}})
        assert res.status_code == 202, res.text
        run_id = res.json()["id"]
        deadline = time.monotonic() + 10
        snap: dict[str, Any] = {}
        while time.monotonic() < deadline:
            snap = client.get(f"{API}/runs/{run_id}").json()
            if snap["run"]["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                break
            time.sleep(0.02)
        assert snap["run"]["status"] == "failed"
        errors = [n["error"] for n in snap["node_runs"] if n.get("error")]
        assert [e["code"] for e in errors] == ["agent.unknown_backend"]
        assert "'fake'" in errors[0]["message"]
