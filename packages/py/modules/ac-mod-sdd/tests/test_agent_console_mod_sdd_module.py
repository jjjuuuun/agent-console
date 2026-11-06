"""모듈 조립(design §6R.3·§6R.4·§6R.13·§6R.18 Q8·Q10·Q13): 종류 기여, 끄기, 라벨 표시 접두,
사용자 설정 경고, 비밀 검사, 파싱 캐시, 틀로 저장, 원격 바인딩, WS 알림, 검증 출처 플러그인,
단독 실행."""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.sdd import SddChanged, VerificationResult
from agent_console_mod_sdd import (
    SDD_SERVICE,
    SDD_TOPIC,
    SddService,
    as_verification_source,
    module,
    parse_sdd_settings,
    template_references,
)
from agent_console_mod_sdd.plugins import load_source_plugins, new_source_registry, plugin_sources
from agent_console_mod_sdd.standalone import main
from agent_console_mod_sdd.testing import library_module
from agent_console_modkit import DEFINITION_KIND_CONTRIBUTIONS, ModulesConfig, Topic
from agent_console_modkit.host import HostSettings
from agent_console_sdd.testing import FakeVerificationSource
from agent_console_store import InMemoryDefinitionStore

API = "/api/v1"
SECRET = "sk-ant-api03-" + "a" * 40


def test_kind_contributions_and_references(tmp_path: Path, kit: Any) -> None:
    assembly = kit.make_assembly(tmp_path)
    found = assembly.ports(DEFINITION_KIND_CONTRIBUTIONS)
    kinds = {c.kind.name: c.kind for c in found}
    assert set(kinds) == {"spec", "spec-template"}
    assert kinds["spec"].library is False
    assert kinds["spec"].portable is True
    assert kinds["spec-template"].library is True
    assert kinds["spec-template"].multi_file is True
    doc = {"rules": {"run_profiles": [{"graph": "a"}, {"graph": "a"}, {"graph": "b"}, {}]}}
    assert list(template_references(doc)) == [("graph", "a"), ("graph", "b")]
    assert list(template_references({"rules": None})) == []


def test_option_names_change_kinds_and_label_keys(tmp_path: Path, kit: Any) -> None:
    options = {"spec_kind": "doc-spec", "run_label_prefix": "x/", "spec_dir": "plans"}
    assembly = kit.make_assembly(tmp_path, options=options)
    names = {c.kind.name for c in assembly.ports(DEFINITION_KIND_CONTRIBUTIONS)}
    assert names == {"doc-spec", "spec-template"}
    report = next(r for r in assembly.report if r.id == "mod-sdd")
    keys = [d["key"] for d in report.label_display]
    assert keys == ["x/spec", "x/task", "x/profile", "x/purpose"]
    assert report.to_dict()["label_display"][0]["target"]["id_from"] == "x/spec"
    with kit.client_for(assembly) as client:
        assert client.get(f"{API}/sdd/info").json()["spec_root"] == "plans"
    none = kit.make_assembly(tmp_path / "n", options={"label_display": []})
    assert next(r for r in none.report if r.id == "mod-sdd").label_display == ()


def test_disabled_module_has_no_routes_or_kinds(tmp_path: Path, kit: Any) -> None:
    root = tmp_path / "ws" / "sdd"
    kit.write_template(kit.spec_store(root))
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    assembly = kit.make_assembly(tmp_path, config=ModulesConfig(disabled=["mod-sdd"]))
    assert assembly.ports(DEFINITION_KIND_CONTRIBUTIONS) == []
    with kit.client_for(assembly) as client:
        assert client.get(f"{API}/sdd/info").status_code == 404
        assert client.get(f"{API}/sdd/specs").status_code == 404
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*")) == before


def test_user_settings_keep_good_parts_and_warn(tmp_path: Path, kit: Any) -> None:
    raw = {
        "secret_scan": "loud",
        "include_default_syntax": False,
        "verification_sources": [{"id": "ok"}, {"enabled": True}],
        "future_key": {"kept": 1},
    }
    parsed, issues = parse_sdd_settings(raw)
    assert parsed.include_default_syntax is False
    assert parsed.secret_scan == "warn"
    assert [s.id for s in parsed.verification_sources] == ["ok"]
    assert (parsed.model_extra or {}).get("future_key") == {"kept": 1}
    assert sorted(i.path or "" for i in issues) == [
        "/sdd/secret_scan",
        "/sdd/verification_sources/1",
    ]
    assembly = kit.make_assembly(tmp_path, settings={"sdd": raw})
    service = assembly.port(SDD_SERVICE)
    assert isinstance(service, SddService)
    assert {i.code for i in service.warnings()} == {"sdd.settings_invalid"}
    with kit.client_for(assembly) as client:
        made = client.post(f"{API}/sdd/specs", json={"name": "N"}).json()
        assert made["index"]["tasks"] == []
        syntax = client.get(f"{API}/sdd/specs/n/syntax").json()
        assert syntax["empty"] is True  # 기본 문법 끔 → 문서 편집은 그대로
        doc = made["spec"]["documents"][0]["id"]
        assert client.get(f"{API}/sdd/specs/n/documents/{doc}").status_code == 200


@pytest.mark.parametrize(
    ("mode", "status", "issues"), [("off", 200, 0), ("warn", 200, 1), ("reject", 422, 0)]
)
def test_document_secret_scan_modes(
    tmp_path: Path, kit: Any, mode: str, status: int, issues: int
) -> None:
    assembly = kit.make_assembly(tmp_path, settings={"sdd": {"secret_scan": mode}})
    with kit.client_for(assembly) as client:
        made = client.post(f"{API}/sdd/specs", json={"name": "S"}).json()
        doc = made["spec"]["documents"][0]["id"]
        put = client.put(
            f"{API}/sdd/specs/s/documents/{doc}", json={"content": f"line\nkey {SECRET}\n"}
        )
        assert put.status_code == status, put.text
        if status == 200:
            found = put.json()["issues"]
            assert len(found) == issues
            if issues:
                assert found[0]["code"] == "sdd.secret_suspect"
                assert found[0]["line"] == 2
        else:
            assert SECRET not in put.text  # 오류 본문에 값이 없다
            assert put.json()["error"]["code"] == "sdd.secret_rejected"
            assert put.json()["error"]["details"]["issues"][0]["line"] == 2


def test_spec_yaml_with_secret_is_rejected_in_standalone_store(tmp_path: Path, kit: Any) -> None:
    with kit.client_for(kit.make_assembly(tmp_path)) as client:
        made = client.post(f"{API}/sdd/specs", json={"name": "S"})
        spec = made.json()["spec"]
        spec["attributes"] = {"api_key": SECRET}
        put = client.put(
            f"{API}/sdd/specs/s", json=spec, headers={"If-Match": made.headers["etag"]}
        )
        assert put.status_code == 422
        assert put.json()["error"]["code"] == "sdd.secret_rejected"
        assert SECRET not in put.text


def test_parse_cache_hits_until_file_changes(tmp_path: Path, kit: Any) -> None:
    root = tmp_path / "ws" / "sdd"
    kit.write_template(kit.spec_store(root))
    assembly = kit.make_assembly(tmp_path)
    service = assembly.port(SDD_SERVICE)
    assert isinstance(service, SddService)
    with kit.client_for(assembly) as client:
        client.post(f"{API}/sdd/specs", json={"name": "C", "template": "flow"})
        service.cache.clear()
        client.get(f"{API}/sdd/specs/c/plan")
        first = service.cache.stats()
        client.get(f"{API}/sdd/specs/c/plan")
        client.get(f"{API}/sdd/specs/c/tasks")
        second = service.cache.stats()
        assert second["misses"] == first["misses"]
        assert second["hits"] >= first["hits"] + 2
        path = root / "specs" / "c" / "tasks.md"
        path.write_text(path.read_text(encoding="utf-8") + "- [ ] 3.1 새 작업\n", encoding="utf-8")
        keys = [t["key"] for t in client.get(f"{API}/sdd/specs/c/tasks").json()]
        assert "3.1" in keys  # 파일을 직접 고쳐도 바로 다시 읽는다


def test_save_as_template_needs_library(tmp_path: Path, kit: Any) -> None:
    root = tmp_path / "ws" / "sdd"
    kit.write_template(kit.spec_store(root))
    with kit.client_for(kit.make_assembly(tmp_path)) as client:
        client.post(f"{API}/sdd/specs", json={"name": "T", "template": "flow"})
        refused = client.post(f"{API}/sdd/specs/t/save-as-template", json={"name": "Copy"})
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "feature_unavailable"

    kinds = [c.kind for c in kit.make_assembly(tmp_path / "k").ports(DEFINITION_KIND_CONTRIBUTIONS)]
    library = InMemoryDefinitionStore([k for k in kinds if k.library])
    kit.write_template(library, {**kit.TEMPLATE, "id": "lib", "name": "라이브러리 틀"})
    assembly = kit.make_assembly(tmp_path / "lib", library_module(library))
    with kit.client_for(assembly) as client:
        assert client.get(f"{API}/sdd/info").json()["capabilities"]["templates"] is True
        assert [t["id"] for t in client.get(f"{API}/sdd/templates").json()] == ["lib"]
        made = client.post(f"{API}/sdd/specs", json={"name": "From lib", "template": "lib"})
        assert made.status_code == 201, made.text
        saved = client.post(
            f"{API}/sdd/specs/from-lib/save-as-template", json={"name": "Lib", "id": "lib"}
        )
        assert saved.status_code == 409
        assert saved.json()["error"]["code"] == "sdd.template_exists"
        renamed = client.post(
            f"{API}/sdd/specs/from-lib/save-as-template",
            json={"name": "Lib", "id": "lib", "on_conflict": "rename"},
        )
        assert renamed.status_code == 201, renamed.text
        assert renamed.json() == {
            "template_id": "lib-2",
            "target": {"project_id": None},
            "status": "renamed",
        }
        assert sorted(library.list_ids("spec-template")) == ["lib", "lib-2"]
        assert library.list_ids("spec-template")
        assert "spec" not in library.kinds()


def test_import_files_refused_on_remote_bind(tmp_path: Path, kit: Any) -> None:
    assembly = kit.make_assembly(tmp_path, options={"server_host": "0.0.0.0"})
    with kit.client_for(assembly) as client:
        res = client.get(f"{API}/sdd/import/files")
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "folders.remote_disabled"


def test_ws_changed_is_published_once_per_change(tmp_path: Path, kit: Any) -> None:
    assembly = kit.make_assembly(tmp_path)
    hub = assembly.services.ws_hub
    got: list[Any] = []

    async def scenario() -> None:
        sub = hub.subscribe(SDD_TOPIC)
        service = assembly.port(SDD_SERVICE)
        assert isinstance(service, SddService)
        service.notify(None, "a", version_hash="v1")
        service.notify(None, "a", version_hash="v1")  # 같은 변경 알림은 한 번
        assembly.services.events.publish(
            Topic("definitions.saved"), _Saved("spec", "a", "v2", None)
        )
        assembly.services.events.publish(
            Topic("definitions.saved"), _Saved("agent", "z", "v", None)
        )
        for _ in range(2):
            got.append(await asyncio.wait_for(sub.get(), 1))
        sub.close()

    asyncio.run(scenario())
    payloads = [m.payload for m in got]
    assert all(isinstance(p, SddChanged) for p in payloads)
    assert [(p.spec_id, p.version_hash) for p in payloads] == [("a", "v1"), ("a", "v2")]


class _Saved:
    def __init__(self, kind: str, id: str, version_hash: str, space: str | None) -> None:
        self.kind, self.id, self.version_hash, self.space = kind, id, version_hash, space


def test_plugin_sources_are_enabled_only_by_settings(tmp_path: Path) -> None:
    source = FakeVerificationSource(
        results=[VerificationResult(source="junitish", status="fail")], source_id="junitish"
    )
    registry = new_source_registry()
    registry.register("junitish", source)
    assert [s.id for s in plugin_sources(registry)] == ["junitish"]
    assert as_verification_source(lambda: source) is source
    with pytest.raises(TypeError):
        as_verification_source(object())
    assert load_source_plugins(new_source_registry(), entry_points=[]) == []


def test_standalone_serves_sdd_routes(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    token = "s" * 32
    config = tmp_path / "standalone.json"
    config.write_text(
        json.dumps({"port": 0, "workspace": "ws", "state": "state", "security": {"token": token}}),
        encoding="utf-8",
    )
    seen: dict[str, Any] = {}

    def serve(app: Any, settings: HostSettings) -> None:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            client.headers["X-Console-Token"] = token
            seen["specs"] = client.get(f"{API}/sdd/specs").json()
            seen["created"] = client.post(f"{API}/sdd/specs", json={"name": "Solo"}).status_code
            seen["modules"] = [m["id"] for m in client.get(f"{API}/modules").json()]

    out = io.StringIO()
    code = main(["--config", str(config)], serve=serve, out=out, environ={})
    assert code == 0, out.getvalue()
    assert seen["specs"] == []
    assert seen["created"] == 201
    assert "mod-sdd" in seen["modules"]
    assert (tmp_path / "ws" / "sdd" / "specs" / "solo.yaml").is_file()
    assert (tmp_path / "state" / "console.sqlite3").is_file()  # 버전 기록(처음 쓸 때 연다)
    assert module.descriptor.id == "mod-sdd"


def test_service_satisfies_port_shape(tmp_path: Path, kit: Any) -> None:
    from agent_console_mod_sdd import SddServicePort
    from agent_console_mod_sdd.ports import SddScopeLike

    service = kit.make_assembly(tmp_path).port(SDD_SERVICE)
    assert isinstance(service, SddServicePort)
    assert isinstance(service.scope(None), SddScopeLike)
    assert service.label_key("task") == "sdd.task"
    assert service.secret_mode() == "warn"
    assert service.secret_findings(f"x {SECRET}")[0].code == "sdd.secret_suspect"
