"""mod-resources: CRUD·종류 검사·본문·여러 파일·종류 목록·사용 수 포트·끄기·포트 계약(3R.12)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, DefinitionReference, Resource
from agent_console_mod_resources import (
    DEFINITION_USAGES,
    RESOURCE_TYPES,
    RESOURCES_LOOKUP,
    DefinitionUsages,
    StoreResources,
    module,
)
from agent_console_mod_resources.testing import local_definitions_module
from agent_console_modkit import Assembly, BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_resources import FileContentLookup, ResourceLookup
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

TOKEN = "t" * 32
API = "/api/v1"
SKILL = {"id": "review", "type": "skill", "name": "리뷰", "config": {"name": "review"}}
TOKEN_TYPE = (
    "id: api-token\n"
    "title: API 토큰\n"
    "config_schema:\n"
    "  type: object\n"
    "  properties:\n"
    "    token: {type: string, x-secret: true}\n"
    "contributes:\n"
    "  - slot: notes\n"
    "    template: '{name}'\n"
)


def _assembly(tmp_path: Path, *extra: Any, config: ModulesConfig | None = None) -> Assembly:
    types_dir = tmp_path / "ws" / "resource-types"
    types_dir.mkdir(parents=True, exist_ok=True)
    (types_dir / "api-token.yaml").write_text(TOKEN_TYPE, encoding="utf-8")
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    return assemble([module, local_definitions_module(), *extra], config, base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def test_crud_type_check_and_usage_count_null(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        assert "api-token" in {t["id"] for t in client.get(f"{API}/resource-types").json()}
        assert client.get(f"{API}/merge-strategies").json()
        doc = {"id": "t", "type": "api-token", "name": "t", "config": {"token": "plain-x-1"}}
        rejected = client.post(f"{API}/resources", json=doc)
        assert rejected.status_code == 422
        assert "plain-x-1" not in rejected.text
        [issue] = rejected.json()["error"]["details"]["issues"]
        assert (issue["code"], issue["path"]) == ("resource.plain_secret", "/config/token")
        ok = {**doc, "config": {"token": "secret://T"}}
        created = client.post(f"{API}/resources", json=ok)
        assert created.status_code == 201
        etag = created.headers["etag"]
        assert client.put(f"{API}/resources/t", json=ok).status_code == 428
        assert (
            client.put(f"{API}/resources/x", json=ok, headers={"If-Match": etag}).status_code == 400
        )
        [summary] = client.get(f"{API}/resources").json()
        assert (summary["id"], summary["usage_count"]) == ("t", None)  # 사용 수 제공자 없음
        assert client.get(f"{API}/resources", params={"type": "skill"}).json() == []
        assert client.delete(f"{API}/resources/t", headers={"If-Match": '"x"'}).status_code == 412
        assert client.delete(f"{API}/resources/t").status_code == 204


def test_content_and_files(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        note = {"id": "n", "type": "api-token", "name": "n", "config": {}}
        etag = client.post(f"{API}/resources", json=note).headers["etag"]
        assert client.get(f"{API}/resources/n/content").status_code == 404
        put = client.put(
            f"{API}/resources/n/content",
            content="# 안녕".encode(),
            headers={"If-Match": etag, "Content-Type": "text/markdown"},
        )
        assert put.status_code == 200
        got = client.get(f"{API}/resources/n/content")
        assert got.text == "# 안녕"
        assert got.headers["content-type"].startswith("text/markdown")
        refused = client.put(
            f"{API}/resources/n/files/a.md", content=b"x", headers={"If-Match": got.headers["etag"]}
        )
        assert refused.status_code == 422
        assert refused.json()["error"]["details"]["issues"][0]["code"] == "resource.not_multi_file"

        etag = client.post(f"{API}/resources", json=SKILL).headers["etag"]
        written = client.put(
            f"{API}/resources/review/files/SKILL.md", content=b"hi", headers={"If-Match": etag}
        )
        assert written.status_code == 200
        assert [f["path"] for f in client.get(f"{API}/resources/review/files").json()] == [
            "SKILL.md"
        ]
        read = client.get(f"{API}/resources/review/files/SKILL.md")
        assert (read.content, read.headers["etag"]) == (b"hi", written.headers["etag"])
        gone = client.delete(
            f"{API}/resources/review/files/SKILL.md", headers={"If-Match": read.headers["etag"]}
        )
        assert gone.status_code == 200
        assert "x-console-issues" not in gone.headers


def test_reserved_file_names_warn_but_save(tmp_path: Path) -> None:
    """예약 이름(기본 `.git`·`_bundle`, 대소문자 무시)은 저장하고 warning 이슈 헤더를 준다."""
    with _client(_assembly(tmp_path)) as client:
        etag = client.post(f"{API}/resources", json=SKILL).headers["etag"]
        plain = client.put(
            f"{API}/resources/review/files/SKILL.md", content=b"x", headers={"If-Match": etag}
        )
        assert "x-console-issues" not in plain.headers
        etag = plain.headers["etag"]
        for path, name in (("_bundle/a.md", "_bundle"), ("docs/.GIT/config", ".git")):
            res = client.put(
                f"{API}/resources/review/files/{path}",
                content=b"secret-body-1",
                headers={"If-Match": etag},
            )
            assert res.status_code == 200, path
            etag = res.headers["etag"]
            [issue] = json.loads(res.headers["x-console-issues"])
            assert issue["severity"] == "warning"
            assert issue["code"] == "resource.reserved_file_name"
            assert issue["details"] == {"path": path, "name": name}
            # 5R.19(4R.19 QA): 경고 배너가 위치를 보이도록 이슈 path(JSON Pointer)·메시지에 경로
            assert issue["path"] == "/files/" + path.replace("/", "~1")
            assert path in issue["message"]
            assert "secret-body-1" not in res.headers["x-console-issues"]
        paths = {f["path"] for f in client.get(f"{API}/resources/review/files").json()}
        assert {"_bundle/a.md", "docs/.GIT/config"} <= paths


def test_reserved_file_names_are_settings(tmp_path: Path) -> None:
    config = ModulesConfig(options={"mod-resources": {"reserved_file_names": ["drafts"]}})
    with _client(_assembly(tmp_path, config=config)) as client:
        etag = client.post(f"{API}/resources", json=SKILL).headers["etag"]
        ok = client.put(
            f"{API}/resources/review/files/_bundle/a.md", content=b"x", headers={"If-Match": etag}
        )
        assert "x-console-issues" not in ok.headers
        warned = client.put(
            f"{API}/resources/review/files/drafts/a.md",
            content=b"x",
            headers={"If-Match": ok.headers["etag"]},
        )
        [issue] = json.loads(warned.headers["x-console-issues"])
        assert issue["details"]["name"] == "drafts"


class _Usages:
    def references(self, kind: str, id: str) -> Sequence[DefinitionReference]:
        return [DefinitionReference(kind="graph", id="g", name="g", node_ids=["a"])]


def test_usage_count_from_optional_port(tmp_path: Path) -> None:
    usages = _Usages()
    assert isinstance(usages, DefinitionUsages)
    provider = fake_module(
        "usages",
        provides=[DEFINITION_USAGES],
        on_build=lambda ctx: ctx.provide(DEFINITION_USAGES, usages),
    )
    with _client(_assembly(tmp_path, provider)) as client:
        client.post(f"{API}/resources", json=SKILL)
        assert client.get(f"{API}/resources").json()[0]["usage_count"] == 1


def test_lookup_port_contract(tmp_path: Path) -> None:
    """제공 구현 ↔ 소비 프로토콜(``ac-resources.ResourceLookup``·``FileContentLookup``)."""
    assembly = _assembly(tmp_path)
    lookup = assembly.port(RESOURCES_LOOKUP)
    assert isinstance(lookup, StoreResources)
    assert isinstance(lookup, ResourceLookup)
    assert isinstance(lookup, FileContentLookup)
    types = assembly.port(RESOURCE_TYPES)
    assert types is not None
    assert "skill" in types
    store = FileDefinitionStore(tmp_path / "ws", DEFAULT_KINDS)
    saved = store.create("resource", SKILL)
    store.write_file("resource", "review", "SKILL.md", b"x", expected_version=saved.version_hash)
    resource = lookup.get_resource("review")
    assert isinstance(resource, Resource)
    assert lookup.read_files(resource) == {"SKILL.md": b"x"}
    assert lookup.read_content(resource) is None
    assert lookup.get_resource("ghost") is None


def test_requires_definitions_store_and_disabled_is_404(tmp_path: Path) -> None:
    lonely = assemble([module], base=BaseServices())
    [report] = lonely.report
    assert (report.state.value, report.missing) == ("unsatisfied", ("definitions.store",))
    off = _assembly(tmp_path, config=ModulesConfig(disabled=["mod-resources"]))
    with _client(off) as client:
        assert client.get(f"{API}/resources").status_code == 404


# --- QA 3R.30 경계 ---
def _put(client: TestClient, path: str, etag: str, body: bytes = b"TOPSECRET-body") -> Any:
    return client.put(
        f"{API}/resources/review/files/{path}", content=body, headers={"If-Match": etag}
    )


def test_empty_reserved_list_never_warns(tmp_path: Path) -> None:
    config = ModulesConfig(options={"mod-resources": {"reserved_file_names": []}})
    with _client(_assembly(tmp_path, config=config)) as client:
        etag = client.post(f"{API}/resources", json=SKILL).headers["etag"]
        res = _put(client, "_bundle/.git/a.md", etag)
        assert res.status_code == 200
        assert "x-console-issues" not in res.headers


def test_multiple_parts_unicode_and_no_content(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        etag = client.post(f"{API}/resources", json=SKILL).headers["etag"]
        res = _put(client, "_bundle/한글/.git/a.md", etag)
        assert res.status_code == 200
        header = res.headers["x-console-issues"]
        header.encode("ascii")
        assert "TOPSECRET" not in header
        issues = json.loads(header)
        assert [i["details"]["name"] for i in issues] == ["_bundle", ".git"]
        assert all(i["severity"] == "warning" for i in issues)
        # 부분 문자열은 예약이 아니다
        etag = res.headers["etag"]
        ok = _put(client, "my.github/x_bundle/a.md", etag)
        assert "x-console-issues" not in ok.headers


def test_traversal_rejected_not_saved(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        etag = client.post(f"{API}/resources", json=SKILL).headers["etag"]
        for path in ("..%2F..%2Fescape.md", "a/%2E%2E/%2E%2E/escape.md", "%2Fetc%2Fx"):
            res = _put(client, path, etag)
            assert res.status_code >= 400, path
        assert not list(tmp_path.rglob("escape.md"))


def test_cors_exposes_issues_header(tmp_path: Path) -> None:
    policy = SecurityPolicy.for_bind(
        "127.0.0.1",
        0,
        token="t" * 32,
        allowed_hosts=["testserver"],
        allowed_origins=["http://localhost:5173"],
    )
    app = create_host_app(
        _assembly(tmp_path), policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE
    )
    res = TestClient(app).get(
        f"{API}/health", headers={"Origin": "http://localhost:5173", "X-Console-Token": "t" * 32}
    )
    exposed = res.headers.get("access-control-expose-headers", "")
    assert "X-Console-Issues" in exposed
    assert "ETag" in exposed


def test_summary_carries_project_scope(tmp_path: Path) -> None:
    """목록 요약 ``project``(공용 = null, design §UX-P.4, 5.2R.31)."""
    with _client(_assembly(tmp_path)) as client:
        assert client.post(f"{API}/resources", json={**SKILL, "project": "app"}).status_code == 201
        shared = {**SKILL, "id": "shared", "config": {"name": "shared"}}
        assert client.post(f"{API}/resources", json=shared).status_code == 201
        rows = {r["id"]: r["project"] for r in client.get(f"{API}/resources").json()}
        assert rows == {"review": "app", "shared": None}


def test_summary_carries_attributes_and_saved_at(tmp_path: Path) -> None:
    """목록 요약 ``attributes``(원문 그대로)·``saved_at``(5.2R.64). 폴더 저장은 기존 PUT."""
    with _client(_assembly(tmp_path)) as client:
        assert client.post(f"{API}/resources", json=SKILL).status_code == 201
        row = client.get(f"{API}/resources").json()[0]
        assert row["attributes"] == {}
        assert isinstance(row["saved_at"], float)

        got = client.get(f"{API}/resources/review")
        body = {**got.json(), "attributes": {"ui": {"folder": "개발팀"}, "keep": 1}}
        put = client.put(
            f"{API}/resources/review", json=body, headers={"If-Match": got.headers["ETag"]}
        )
        assert put.status_code == 200, put.text
        row = client.get(f"{API}/resources").json()[0]
        assert row["attributes"] == {"ui": {"folder": "개발팀"}, "keep": 1}
