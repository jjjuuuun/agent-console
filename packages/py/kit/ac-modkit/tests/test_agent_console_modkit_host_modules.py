"""3R.9: 켜고 끄기 덮어쓰기, /modules, feature_unavailable, fail_fast 시작, 코어 import 차단."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest
from fastapi.testclient import TestClient

from agent_console_modkit import (
    FEATURE_UNAVAILABLE,
    FeatureUnavailableError,
    ModuleDescriptor,
    ModuleParts,
    ModulesConfig,
    ModuleState,
    PortKey,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import ECHO_TRANSFORM, echo_module, fake_module

API = "/api/v1"


def _policy() -> SecurityPolicy:
    return SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])


# ---------------------------------------------------------------- ModulesConfig.with_overrides


def test_with_overrides_null_enabled_keeps_all_and_moves_disabled() -> None:
    cfg = ModulesConfig(disabled=["a", "b"])
    out = cfg.with_overrides(enable=["a"], disable=["c"])
    assert out.enabled is None
    assert out.disabled == ["b", "c"]
    assert cfg.disabled == ["a", "b"]  # 원본은 그대로


def test_with_overrides_enabled_list_and_disable_wins() -> None:
    cfg = ModulesConfig(enabled=["a", "b"], options={"a": {"x": 1}})
    out = cfg.with_overrides(enable=["c", "d"], disable=["b", "d"])
    assert out.enabled == ["a", "c"]
    assert out.disabled == ["b", "d"]
    assert out.options == {"a": {"x": 1}}


def test_with_overrides_applied_to_assemble() -> None:
    a = fake_module("mod-a")
    b = fake_module("mod-b")
    cfg = ModulesConfig(disabled=["mod-a"]).with_overrides(enable=["mod-a"], disable=["mod-b"])
    states = {r.id: r.state for r in assemble([a, b], cfg).report}
    assert states == {"mod-a": ModuleState.ACTIVE, "mod-b": ModuleState.DISABLED}


# ---------------------------------------------------------------- 보고·/modules


def test_report_carries_contracts_mapping_and_to_dict() -> None:
    module = fake_module("mod-x", optional=["p.opt"])
    module.descriptor = ModuleDescriptor(
        id="mod-x",
        version="1.2.3",
        kind="feature",
        title="X",
        optional=(PortKey("p.opt"),),
        contracts={"chat": "1.0.0"},
        web_roles=("x",),
    )
    report = assemble([module]).report[0]
    assert report.contracts == {"chat": "1.0.0"}
    data = report.to_dict()
    assert data["state"] == "active"
    assert data["contracts"] == {"chat": "1.0.0"}
    assert data["optional"] == ["p.opt"]
    json.dumps(data)  # JSON으로 보낼 수 있다


def test_host_modules_route_lists_reports() -> None:
    assembly = assemble([echo_module, fake_module("mod-off")], ModulesConfig(disabled=["mod-off"]))
    with TestClient(create_host_app(assembly, policy=_policy())) as client:
        body = client.get(f"{API}/modules").json()
    assert [(m["id"], m["state"]) for m in body] == [("echo", "active"), ("mod-off", "disabled")]
    assert body[0]["web_roles"] == ["echo"]


def test_host_modules_route_payload_injected() -> None:
    assembly = assemble([echo_module])
    app = create_host_app(
        assembly, policy=_policy(), modules_payload=lambda: [{"id": r.id} for r in assembly.report]
    )
    with TestClient(app) as client:
        assert client.get(f"{API}/modules").json() == [{"id": "echo"}]


# ---------------------------------------------------------------- feature_unavailable


def test_feature_unavailable_when_optional_port_missing() -> None:
    with TestClient(create_host_app(assemble([echo_module]), policy=_policy())) as client:
        res = client.get(f"{API}/echo/transformed", params={"text": "hi"})
    assert res.status_code == 409
    assert res.json()["error"] == {
        "code": FEATURE_UNAVAILABLE,
        "message": res.json()["error"]["message"],
        "details": {"module": "echo", "port": ECHO_TRANSFORM.name},
    }


def test_feature_available_when_optional_port_provided() -> None:
    upper = fake_module(
        "mod-upper",
        provides=[ECHO_TRANSFORM],
        on_build=lambda ctx: ctx.provide(ECHO_TRANSFORM, str.upper),
    )
    with TestClient(create_host_app(assemble([echo_module, upper]), policy=_policy())) as client:
        res = client.get(f"{API}/echo/transformed", params={"text": "hi"})
    assert res.status_code == 200
    assert res.json() == {"text": "HI"}


def test_feature_unavailable_error_shape() -> None:
    exc = FeatureUnavailableError("mod-chat", "chat.turn_launcher")
    assert exc.code == FEATURE_UNAVAILABLE
    assert exc.details == {"module": "mod-chat", "port": "chat.turn_launcher"}
    assert "chat.turn_launcher" in str(exc)


# ---------------------------------------------------------------- fail_fast


async def test_start_fail_fast_reraises_and_stop_cleans_up() -> None:
    calls: list[str] = []

    def parts_for(name: str, *, fail: bool = False) -> ModuleParts:
        async def start() -> None:
            calls.append(f"start {name}")
            if fail:
                raise RuntimeError("boom")

        async def stop() -> None:
            calls.append(f"stop {name}")

        return ModuleParts(startup=[start], shutdown=[stop])

    assembly = assemble(
        [
            fake_module("mod-a", on_build=lambda _: parts_for("mod-a")),
            fake_module("mod-b", on_build=lambda _: parts_for("mod-b", fail=True)),
            fake_module("mod-c", on_build=lambda _: parts_for("mod-c")),
        ]
    )
    with pytest.raises(RuntimeError, match="boom"):
        await assembly.start(fail_fast=True)
    assert calls == ["start mod-a", "start mod-b"]  # 뒤 모듈은 시작하지 않는다
    assert assembly.status("mod-b").state is ModuleState.FAILED  # type: ignore[union-attr]
    await assembly.stop()
    assert calls[-2:] == ["stop mod-b", "stop mod-a"]


# ---------------------------------------------------------------- 코어 import 차단


def test_core_imports_without_host_dependencies() -> None:
    """코어(``agent_console_modkit``)는 fastapi·uvicorn·websockets·ruamel·starlette 없이
    import·조립된다."""
    script = textwrap.dedent(
        """
        import importlib.abc
        import sys

        BLOCKED = ("fastapi", "uvicorn", "websockets", "ruamel", "starlette")

        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in BLOCKED:
                    raise ImportError(f"blocked: {name}")
                return None

        sys.meta_path.insert(0, Block())
        import agent_console_modkit as mk

        store = mk.PortKey("definitions.store")

        class Provider:
            descriptor = mk.ModuleDescriptor(
                id="mod-a", version="0", kind="feature", title="A", provides=(store,)
            )

            def build(self, ctx):
                ctx.provide(store, "impl")
                return mk.ModuleParts()

        class Consumer:
            descriptor = mk.ModuleDescriptor(
                id="mod-b", version="0", kind="feature", title="B", requires=(store,)
            )

            def build(self, ctx):
                return mk.ModuleParts()

        assembly = mk.assemble([Consumer(), Provider()])
        assert assembly.order == ["mod-a", "mod-b"], assembly.order
        loaded = sorted(n for n in sys.modules if n.split(".")[0] in BLOCKED)
        assert not loaded, loaded
        print("ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
