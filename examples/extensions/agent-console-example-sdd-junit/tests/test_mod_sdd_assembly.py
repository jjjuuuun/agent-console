"""예제를 설치한 조립(테스트 호스트 + mod-sdd): entry point로 로드 → 사용자 설정에서 켬 → 추적 표에
JUnit 결과가 들어간다. 설정에 켜지 않으면 쓰이지 않고, 폴더 밖 파일 패턴은 거부된다(추적 표에 결과
없음, 폴더 밖 파일을 읽지 않음).

entry point는 설치 대신 `importlib.metadata.EntryPoint`를 만들어 mod-sdd 로더에 주입한다
(설치한 서버의 호스트 플러그인 로더가 하는 일과 같다).
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_example_sdd_junit import SOURCE_ID
from agent_console_mod_sdd import module
from agent_console_mod_sdd.plugins import (
    VERIFICATION_SOURCES_EXTENSION,
    VERIFICATION_SOURCES_GROUP,
    as_verification_source,
    load_source_plugins,
)
from agent_console_mod_sdd.testing import SimpleSpace, spaces_module, static_settings_module
from agent_console_modkit import Assembly, BaseServices, ExtensionRegistries, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_sdd import LocalSpecFiles, definition_kinds
from agent_console_store import FileDefinitionStore

API = "/api/v1"
TOKEN = "t" * 32
TEMPLATE: dict[str, Any] = {
    "kind": "spec-template",
    "id": "flow",
    "name": "흐름",
    "documents": [
        {"id": "req", "title": "요구", "file": "req.md", "roles": ["requirements"]},
        {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
    ],
}
REQ = "# 요구\n\n**R1** 첫 요구\n\n**R2** 둘째 요구\n\n**R3** 셋째 요구\n"
TASKS = "# 작업\n\n- [ ] 1.1 뼈대 [req: R1]\n- [ ] 1.2 화면 [req: R2]\n"
JUNIT = (
    '<testsuites><testsuite name="unit" timestamp="2026-11-05T09:00:00">'
    '<testcase classname="tests.test_login" name="test_R1_login"/>'
    '<testcase classname="tests.test_login" name="test_R2_logout"><failure/></testcase>'
    "</testsuite></testsuites>"
)
OUTSIDE = (
    '<testsuites><testsuite name="x"><testcase name="test_R3_outside"/></testsuite></testsuites>'
)


def _project(tmp_path: Path) -> SimpleSpace:
    folder = tmp_path / "proj"
    (folder / "reports" / "unit").mkdir(parents=True)
    (folder / "reports" / "unit" / "junit.xml").write_text(JUNIT, encoding="utf-8")
    (tmp_path / "outside.xml").write_text(OUTSIDE, encoding="utf-8")
    store = FileDefinitionStore(
        folder / ".cfg",
        definition_kinds(
            spec_kind="spec",
            spec_directory="specs",
            template_kind="spec-template",
            template_directory="spec-templates",
        ),
    )
    created = store.create("spec-template", TEMPLATE)
    store.write_files(
        "spec-template",
        "flow",
        {"req.md": REQ.encode(), "tasks.md": TASKS.encode()},
        expected_version=created.version_hash,
    )
    return SimpleSpace(store=store, files=LocalSpecFiles(folder), config_dir=".cfg")


def _installed_registries() -> ExtensionRegistries:
    """설치한 서버처럼 entry point 그룹을 묶음의 확장 레지스트리에 로드한다."""
    bundle = ExtensionRegistries()
    registry = bundle.extension(VERIFICATION_SOURCES_EXTENSION, validator=as_verification_source)
    ep = importlib.metadata.EntryPoint(
        name=SOURCE_ID,
        value="agent_console_example_sdd_junit:JUnitVerificationSource",
        group=VERIFICATION_SOURCES_GROUP,
    )
    reports = load_source_plugins(registry, entry_points=[ep])
    assert [r.status for r in reports] == ["loaded"], reports
    return bundle


def _assembly(tmp_path: Path, sources: Sequence[Mapping[str, Any]]) -> Assembly:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=_installed_registries(),
    )
    settings = {"sdd": {"verification_sources": sources}}
    modules = [
        module,
        static_settings_module(settings),
        spaces_module({"a": _project(tmp_path)}),
    ]
    return assemble(modules, None, base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _trace(client: TestClient) -> dict[str, Any]:
    made = client.post(f"{API}/sdd/specs?project=a", json={"name": "S", "template": "flow"})
    assert made.status_code == 201, made.text
    got = client.get(f"{API}/sdd/specs/s/trace?project=a")
    assert got.status_code == 200, got.text
    return {r["id"]: r for r in got.json()["rows"]}


def test_junit_results_enter_the_trace_matrix(tmp_path: Path) -> None:
    sources = [{"id": SOURCE_ID, "enabled": True, "options": {"paths": ["reports/**/*.xml"]}}]
    with _client(_assembly(tmp_path, sources)) as client:
        info = client.get(f"{API}/sdd/info?project=a").json()
        assert info["capabilities"]["verification"] is True
        rows = _trace(client)
    assert rows["R1"]["verification"]["status"] == "pass"
    assert rows["R1"]["verification"]["source"] == SOURCE_ID
    assert rows["R2"]["verification"]["status"] == "fail"
    assert rows["R3"]["verification"] is None
    assert "verification_failed" in rows["R2"]["gaps"]
    assert rows["R1"]["results"][0]["ref"]["path"] == "reports/unit/junit.xml"


def test_installed_but_not_enabled_is_not_used(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path, [])) as client:
        info = client.get(f"{API}/sdd/info?project=a").json()
        assert info["capabilities"]["verification"] is False
        rows = _trace(client)
    assert all(row["verification"] is None for row in rows.values())


def test_pattern_outside_the_project_is_rejected(tmp_path: Path) -> None:
    sources = [
        {
            "id": SOURCE_ID,
            "enabled": True,
            "options": {"paths": ["../outside.xml", "reports/**/*.xml"]},
        }
    ]
    with _client(_assembly(tmp_path, sources)) as client:
        rows = _trace(client)
    # 옵션 전체가 거부되어 이 출처는 결과를 내지 않는다(폴더 안 패턴도 함께 — 안전한 쪽).
    assert all(row["verification"] is None for row in rows.values())
