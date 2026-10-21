"""mod-presets: 목록·적용·시작 시 적용·검사 포트·끄기(design §3R.1.3)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, Issue
from agent_console_mod_presets import (
    DEFINITION_CHECKS,
    DEFINITION_DEPENDENCIES,
    DEFINITIONS_STORE,
    DefinitionCheck,
    DocumentDependencies,
    PresetNotFoundError,
    module,
)
from agent_console_mod_presets.testing import local_definitions_module
from agent_console_modkit import BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import DEFAULT_KINDS, InMemoryDefinitionStore

TOKEN = "t" * 32


def _preset(root: Path, preset_id: str = "demo", agent_name: str = "도우미") -> Path:
    folder = root / preset_id
    (folder / "agents").mkdir(parents=True)
    (folder / "preset.yaml").write_text(
        f"kind: preset\nid: {preset_id}\nschema_version: 1\nname: 예시\n"
        "items:\n  - agents/helper.yaml\n",
        encoding="utf-8",
    )
    (folder / "agents" / "helper.yaml").write_text(
        f"id: helper\nname: {agent_name}\nbackend: fake\n", encoding="utf-8"
    )
    return root


class _RejectNames:
    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]:
        if document.get("name") == "거부":
            return [Issue(severity="error", code="test.rejected", message="거부", path="/name")]
        return []


def _store_module(store: InMemoryDefinitionStore, *, checks: bool = False) -> Any:
    provides = [DEFINITIONS_STORE, DEFINITION_CHECKS] if checks else [DEFINITIONS_STORE]

    def build(ctx: Any) -> None:
        ctx.provide(DEFINITIONS_STORE, store)
        if checks:
            ctx.provide(DEFINITION_CHECKS, _RejectNames())

    return fake_module("definitions", provides=provides, on_build=build)


def _config(root: Path, **extra: Any) -> ModulesConfig:
    return ModulesConfig(options={"mod-presets": {"directories": [str(root)], **extra}})


def _client(*modules: Any, config: ModulesConfig | None = None) -> TestClient:
    assembly = assemble([module, *modules], config)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def test_list_and_apply_over_http(tmp_path: Path) -> None:
    store = InMemoryDefinitionStore(DEFAULT_KINDS)
    with _client(_store_module(store), config=_config(_preset(tmp_path))) as client:
        [summary] = client.get("/api/v1/presets").json()
        assert (summary["id"], summary["item_count"]) == ("demo", 1)
        applied = client.post("/api/v1/presets/demo/apply").json()
        assert [i["action"] for i in applied["items"]] == ["created"]
        again = client.post("/api/v1/presets/demo/apply", json={"on_conflict": "skip"}).json()
        assert [i["action"] for i in again["items"]] == ["skipped"]
        missing = client.post("/api/v1/presets/ghost/apply")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"
    assert store.list_ids("agent") == ["helper"]


def test_checks_port_rejects_items(tmp_path: Path) -> None:
    store = InMemoryDefinitionStore(DEFAULT_KINDS)
    root = _preset(tmp_path, agent_name="거부")
    with _client(_store_module(store, checks=True), config=_config(root)) as client:
        [item] = client.post("/api/v1/presets/demo/apply").json()["items"]
    assert item["action"] == "failed"
    assert item["error"].endswith("test.rejected(/name)")
    assert store.list_ids("agent") == []
    assert isinstance(_RejectNames(), DefinitionCheck)


def test_apply_on_start_and_unknown_id_fails_start(tmp_path: Path) -> None:
    store = InMemoryDefinitionStore(DEFAULT_KINDS)
    root = _preset(tmp_path)
    assembly = assemble([module, _store_module(store)], _config(root, apply_on_start=["demo"]))
    asyncio.run(assembly.start(fail_fast=True))
    asyncio.run(assembly.stop())
    assert store.list_ids("agent") == ["helper"]
    bad = assemble([module, _store_module(store)], _config(root, apply_on_start=["ghost"]))
    with pytest.raises(PresetNotFoundError):
        asyncio.run(bad.start(fail_fast=True))


def test_requires_store_and_disabled_is_404(tmp_path: Path) -> None:
    alone = assemble([module])
    assert alone.report[0].state.value == "unsatisfied"
    assert alone.report[0].missing == ("definitions.store",)
    store = InMemoryDefinitionStore(DEFAULT_KINDS)
    config = ModulesConfig(disabled=["mod-presets"])
    with _client(_store_module(store), config=config) as client:
        assert client.get("/api/v1/presets").status_code == 404


def test_relative_directories_resolve_against_base_dir(tmp_path: Path) -> None:
    _preset(tmp_path / "presets")
    base = BaseServices(paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path))
    config = ModulesConfig(options={"mod-presets": {"directories": ["presets"]}})
    assembly = assemble([module, local_definitions_module()], config, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        client.headers["X-Console-Token"] = TOKEN
        assert [p["id"] for p in client.get("/api/v1/presets").json()] == ["demo"]
        assert client.post("/api/v1/presets/demo/apply").status_code == 200
    assert (tmp_path / "ws" / "agents" / "helper.yaml").is_file()


@dataclass(frozen=True)
class _Ref:
    kind: str
    id: str


class _Uses:
    """``definitions.dependencies`` 흉내: 팀 구성 parent → child → 에이전트 helper."""

    def dependencies_of(self, kind: str, document: Mapping[str, Any]) -> Sequence[_Ref]:
        return {
            "parent": [_Ref("graph", "child"), _Ref("agent", "helper")],
            "child": [_Ref("agent", "helper")],
        }.get(str(document.get("id")), [])


def _nested_preset(root: Path) -> Path:
    folder = root / "nest"
    (folder / "graphs").mkdir(parents=True)
    (folder / "agents").mkdir()
    (folder / "preset.yaml").write_text(
        "kind: preset\nid: nest\nname: 중첩\n"
        "items:\n  - graphs/parent.yaml\n  - graphs/child.yaml\n  - agents/helper.yaml\n",
        encoding="utf-8",
    )
    for gid in ("parent", "child"):
        (folder / "graphs" / f"{gid}.yaml").write_text(f"id: {gid}\nname: {gid}\n", "utf-8")
    (folder / "agents" / "helper.yaml").write_text("id: helper\nname: 도우미\n", "utf-8")
    return root


def test_dependencies_port_orders_items(tmp_path: Path) -> None:
    """``definitions.dependencies``가 있으면 쓰는 정의부터, 없으면 매니페스트 순서(5R.15)."""
    root = _nested_preset(tmp_path)
    assert isinstance(_Uses(), DocumentDependencies)

    def provider(ctx: Any) -> None:
        ctx.provide(DEFINITION_DEPENDENCIES, _Uses())

    uses = fake_module("teams", provides=[DEFINITION_DEPENDENCIES], on_build=provider)
    store = InMemoryDefinitionStore(DEFAULT_KINDS)
    with _client(_store_module(store), uses, config=_config(root)) as client:
        items = client.post("/api/v1/presets/nest/apply").json()["items"]
    assert [i["id"] for i in items] == ["helper", "child", "parent"]
    plain = InMemoryDefinitionStore(DEFAULT_KINDS)
    with _client(_store_module(plain), config=_config(root)) as client:
        items = client.post("/api/v1/presets/nest/apply").json()["items"]
    assert [i["id"] for i in items] == ["parent", "child", "helper"]


def test_apply_request_project_stamps_created_items(tmp_path: Path) -> None:
    """요청 ``project``(계약 0.8.0) → 만든 정의에 범위를 찍는다. 생략 = 공용(design §UX-P.2)."""
    from agent_console_mod_presets import scope_stamp

    assert scope_stamp(None) is None
    assert scope_stamp("") is None
    assert scope_stamp("app") == {"project": "app"}
    store = InMemoryDefinitionStore(DEFAULT_KINDS)
    with _client(_store_module(store), config=_config(_preset(tmp_path))) as client:
        body = {"on_conflict": "skip", "project": "app"}
        applied = client.post("/api/v1/presets/demo/apply", json=body).json()
        assert [i["action"] for i in applied["items"]] == ["created"]
        assert store.get("agent", "helper").document["project"] == "app"
        body = {"on_conflict": "rename"}
        renamed = client.post("/api/v1/presets/demo/apply", json=body).json()
        [item] = renamed["items"]
        assert "project" not in store.get("agent", item["target_id"]).document
        bad = client.post("/api/v1/presets/demo/apply", json={"project": "Bad Id!"})
        assert bad.status_code in (400, 422)


# --- 5.2R.6: 요약 badges·featured·start_graph -------------------------------------------------


@dataclass(frozen=True)
class _Hints:
    badge: str | None


@dataclass(frozen=True)
class _Descriptor:
    ui_hints: _Hints | None


@dataclass(frozen=True)
class _Backend:
    descriptor: _Descriptor


@dataclass(frozen=True)
class _Entry:
    key: str
    item: _Backend


class _BackendRegistry:
    def __init__(self, badges: Mapping[str, str | None]) -> None:
        self._entries = [
            _Entry(k, _Backend(_Descriptor(_Hints(v) if v is not None else None)))
            for k, v in badges.items()
        ]

    def list(self, *, all_versions: bool = False) -> list[_Entry]:
        return list(self._entries)


@dataclass
class _Registries:
    backends: _BackendRegistry


def _start_preset(root: Path, manifest_extra: str, *, backend: str = "trial") -> Path:
    """에이전트(backend 없음) + 팀 구성(settings.backend)이 있는 프리셋."""
    folder = root / "starter"
    (folder / "agents").mkdir(parents=True)
    (folder / "graphs").mkdir(parents=True)
    (folder / "preset.yaml").write_text(
        "kind: preset\nid: starter\nname: 시작\ndefault_entry: main\n"
        "items:\n  - agents/helper.yaml\n  - graphs/main.yaml\n" + manifest_extra,
        encoding="utf-8",
    )
    (folder / "agents" / "helper.yaml").write_text("id: helper\nname: 도우미\n", encoding="utf-8")
    (folder / "graphs" / "main.yaml").write_text(
        f"kind: graph\nid: main\nname: 메인\nsettings:\n  backend: {backend}\n"
        "nodes:\n  - {id: a, type: agent, config: {agent_ref: helper}}\n",
        encoding="utf-8",
    )
    return root


def _base(registries: Any) -> BaseServices:
    return BaseServices(registries=registries)


def _summaries(root: Path, registries: Any = None) -> list[dict[str, Any]]:
    store = InMemoryDefinitionStore(DEFAULT_KINDS)
    assembly = assemble([module, _store_module(store)], _config(root), base=_base(registries))
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        response = client.get("/api/v1/presets")
        assert response.status_code == 200
        body: list[dict[str, Any]] = response.json()
        return body


def test_summary_badges_from_manifest_and_backend_descriptor(tmp_path: Path) -> None:
    """배지 = 매니페스트 badges + 쓰는 백엔드의 디스크립터 ui_hints.badge(이름은 데이터)."""
    root = _start_preset(tmp_path, "featured: 2\nbadges: [추천]\n", backend="trial")
    registries = _Registries(_BackendRegistry({"trial": "맛보기", "real": None}))
    [summary] = _summaries(root, registries)
    assert summary["badges"] == ["추천", "맛보기"]
    assert summary["featured"] == 2
    assert summary["start_graph"] == "main"  # 키 생략 = default_entry


def test_summary_without_registries_or_badge_has_only_manifest_badges(tmp_path: Path) -> None:
    root = _start_preset(tmp_path, "badges: [추천, 추천]\n", backend="real")
    [alone] = _summaries(root)  # 실행 기능 없음(레지스트리 없음)
    assert alone["badges"] == ["추천"]
    assert alone["featured"] is None
    registries = _Registries(_BackendRegistry({"real": None}))
    [plain] = _summaries(root, registries)  # 배지 없는 백엔드
    assert plain["badges"] == ["추천"]


def test_summary_start_graph_explicit_null_and_missing_graph(tmp_path: Path) -> None:
    [off] = _summaries(_start_preset(tmp_path / "a", "start_graph: null\n"))
    assert off["start_graph"] is None
    [ghost] = _summaries(_start_preset(tmp_path / "b", "start_graph: ghost\n"))
    assert ghost["start_graph"] is None  # 항목에 없는 팀 구성은 싣지 않는다
    [explicit] = _summaries(_start_preset(tmp_path / "c", "start_graph: main\n"))
    assert explicit["start_graph"] == "main"


def test_summary_with_broken_items_keeps_listing(tmp_path: Path) -> None:
    root = _start_preset(tmp_path, "badges: [추천]\n")
    (root / "starter" / "graphs" / "main.yaml").write_text("- not a mapping\n", encoding="utf-8")
    registries = _Registries(_BackendRegistry({"trial": "맛보기"}))
    [summary] = _summaries(root, registries)
    assert (summary["badges"], summary["start_graph"]) == (["추천"], None)


def test_no_presets_lists_empty(tmp_path: Path) -> None:
    """프리셋을 전부 지워도(빈 폴더·없는 폴더) 목록은 빈 배열이다(R0.2)."""
    (tmp_path / "empty").mkdir()
    assert _summaries(tmp_path / "empty") == []
    assert _summaries(tmp_path / "missing") == []


def test_registry_backend_badge_tolerates_other_shapes() -> None:
    from agent_console_mod_presets import registry_backend_badge

    assert registry_backend_badge(lambda: None)("fake") is None
    assert registry_backend_badge(lambda: object())("fake") is None
    reg = _Registries(_BackendRegistry({"x": "체험"}))
    assert registry_backend_badge(lambda: reg)("x") == "체험"
    assert registry_backend_badge(lambda: reg)("y") is None


def test_scan_cache_rereads_only_changed_presets(tmp_path: Path) -> None:
    import os

    from agent_console_mod_presets import ScanCache, list_presets

    root = _start_preset(tmp_path, "", backend="one")
    cache = ScanCache()
    badge = {"one": "하나", "two": "둘"}.get
    [first] = list_presets([root], backend_badge=badge, cache=cache)
    assert first.badges == ["하나"]
    graph = root / "starter" / "graphs" / "main.yaml"
    graph.write_text(graph.read_text(encoding="utf-8").replace("one", "two"), encoding="utf-8")
    st = graph.stat()
    os.utime(graph, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    [second] = list_presets([root], backend_badge=badge, cache=cache)
    assert second.badges == ["둘"]
