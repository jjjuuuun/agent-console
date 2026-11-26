"""모듈 조립(design §7R.3·§7R.4·§7R.5·§7R.12·§7R.18 Q14): 종류 기여, 끄기, 설치자 이름 바꾸기(R0),
사용자 설정 경고, 능력, 쓰기 검사(X50 포트·플러그인), 검색 대체, 단독 실행, OpenAPI 계약 밖 0."""

from __future__ import annotations

import ast
import importlib.metadata
import io
import json
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts import render_schema
from agent_console_mod_wiki import (
    SECTION_KEY,
    WRITE_CHECKS_GROUP,
    as_write_check_factory,
    load_write_check_plugins,
    module,
    new_write_check_registry,
    package_defaults,
    parse_wiki_settings,
    wiki_references,
)
from agent_console_mod_wiki.ports import SERVER_WARNINGS
from agent_console_mod_wiki.standalone import main
from agent_console_mod_wiki.testing import (
    FrontMatterKeyCheck,
    integration_module,
    library_module,
    write_check_module,
)
from agent_console_modkit import DEFINITION_KIND_CONTRIBUTIONS, ModulesConfig
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_store import InMemoryDefinitionStore
from agent_console_wiki import definition_kinds

API = "/api/v1"
SRC = Path(__file__).resolve().parents[1] / "src" / "agent_console_mod_wiki"


def test_kind_contributions_and_references(tmp_path: Path, kit: Any) -> None:
    assembly = kit.make_assembly(tmp_path)
    kinds = {c.kind.name: c for c in assembly.ports(DEFINITION_KIND_CONTRIBUTIONS)}
    assert set(kinds) == {"wiki", "wiki-rules"}
    assert kinds["wiki"].kind.library is False
    assert kinds["wiki"].kind.portable is True
    assert kinds["wiki-rules"].kind.library is True
    assert kinds["wiki-rules"].kind.multi_file is True
    assert kinds["wiki-rules"].references is None
    refs = kinds["wiki"].references
    assert refs is not None
    assert list(refs({"rules": ["a", "a", "b", 3]})) == [("wiki-rules", "a"), ("wiki-rules", "b")]
    assert list(wiki_references("r")({"rules": None})) == []
    # P1.19: 여는 화면 역할(CopyKindInfo.open_role)은 이 모듈의 웹 역할이다
    assert kinds["wiki"].open_role == "wiki"
    assert kinds["wiki-rules"].open_role == "wiki:rules"
    report = next(r for r in assembly.report if r.id == "mod-wiki")
    assert {c.open_role for c in kinds.values()} <= set(report.web_roles)


def test_option_names_change_kinds_and_folders(tmp_path: Path, kit: Any, database: Any) -> None:
    options = {
        "wiki_kind": "note-book",
        "rules_kind": "note-rules",
        "wiki_dir": "books",
        "rules_dir": "book-rules",
        "pages_dir": "leaves",
    }
    assembly = kit.make_assembly(tmp_path, options=options, database=database)
    names = {c.kind.name for c in assembly.ports(DEFINITION_KIND_CONTRIBUTIONS)}
    assert names == {"note-book", "note-rules"}
    with kit.client_for(assembly) as client:
        assert client.get(f"{API}/wiki/info").json()["pages_root"] == "leaves"
        kit.make_rules(client, "r1")
        made = client.post(f"{API}/wiki/wikis", json={"name": "Book", "rules": ["r1"]}).json()
        assert made["directory"] == "leaves/book"
        kit.write_page(client, "book", "p", "# p\n")
    root = tmp_path / "ws" / package_defaults()["standalone_dir"]
    assert (root / "books" / "book.yaml").exists()
    assert (root / "book-rules" / "r1.yaml").exists()
    assert (root / "leaves" / "book" / "p.md").exists()


def test_disabled_module_has_no_routes_or_kinds(tmp_path: Path, kit: Any, database: Any) -> None:
    with kit.client_for(kit.make_assembly(tmp_path, database=database)) as client:
        client.post(f"{API}/wiki/wikis", json={"name": "w"})
        kit.write_page(client, "w", "p", "# p\n")
    root = tmp_path / "ws" / "wiki"
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    assembly = kit.make_assembly(tmp_path, config=ModulesConfig(disabled=["mod-wiki"]))
    assert assembly.ports(DEFINITION_KIND_CONTRIBUTIONS) == []
    with kit.client_for(assembly) as client:
        for path in ("/wiki/info", "/wiki/wikis", "/wiki/rules", "/wiki/wikis/w/pages/p"):
            assert client.get(f"{API}{path}").status_code == 404, path
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*")) == before


def test_empty_workspace_creates_nothing(tmp_path: Path, kit: Any) -> None:
    with kit.client_for(kit.make_assembly(tmp_path)) as client:
        assert client.get(f"{API}/wiki/wikis").json() == []
        assert client.get(f"{API}/wiki/rules").json() == []
        info = client.get(f"{API}/wiki/info").json()
        # DB 없음 → 메모리 기록(프로세스 안에서는 동작)
        assert info["capabilities"]["history"] is True
        assert info["capabilities"]["search"] is True
    assert not (tmp_path / "ws" / "wiki").exists()


def test_user_settings_keep_good_parts_and_warn(tmp_path: Path, kit: Any) -> None:
    raw = {
        "secret_scan": "loud",
        "include_default_syntax": False,
        "write_checks": [{"id": "x"}, {"enabled": True}],
        "future_key": {"a": 1},
    }
    settings, issues = parse_wiki_settings(raw)
    assert settings.include_default_syntax is False
    assert settings.secret_scan == {"user": "warn", "agent": "reject", "system": "reject"}
    assert [c.id for c in settings.write_checks] == ["x"]
    assert settings.model_extra == {"future_key": {"a": 1}}
    assert {i.path for i in issues} == {"/wiki/secret_scan", "/wiki/write_checks/1"}
    assembly = kit.make_assembly(tmp_path, settings={SECTION_KEY: raw})
    codes = [i.code for source in assembly.ports(SERVER_WARNINGS) for i in source()]
    # 깨진 값 2 + 켰는데 설치되지 않은 쓰기 검사 1
    assert codes.count("wiki.settings_invalid") == 3


def test_default_syntax_off_reads_no_wikilinks(tmp_path: Path, kit: Any, database: Any) -> None:
    settings = {
        SECTION_KEY: {
            "include_default_syntax": False,
            "syntax": {
                "links": [{"id": "md", "kind": "markdown", "resolve": ["relative_path"]}],
                "page_extensions": [".md"],
            },
        }
    }
    with kit.client_for(kit.make_assembly(tmp_path, settings=settings, database=database)) as c:
        c.post(f"{API}/wiki/wikis", json={"name": "w"})
        page = kit.write_page(c, "w", "a", "# a\n\n[[b]] [b](b.md)\n")
        assert [link["rule_id"] for link in page["links"]] == ["md"]
        syntax = c.get(f"{API}/wiki/wikis/w/syntax").json()
        assert "default" not in syntax["sources"].values()


def test_capabilities_runs_from_integrations(tmp_path: Path, kit: Any) -> None:
    with kit.client_for(kit.make_assembly(tmp_path, integration_module(["runs"]))) as client:
        assert client.get(f"{API}/wiki/info").json()["capabilities"]["runs"] is True
    other = kit.make_assembly(tmp_path / "o", integration_module(["something-else"]))
    with kit.client_for(other) as client:
        assert client.get(f"{API}/wiki/info").json()["capabilities"]["runs"] is False


def test_write_check_port_and_setting_off(tmp_path: Path, kit: Any, database: Any) -> None:
    check = FrontMatterKeyCheck({"key": "source"})
    assembly = kit.make_assembly(tmp_path, write_check_module(check), database=database)
    with kit.client_for(assembly) as client:
        client.post(f"{API}/wiki/wikis", json={"name": "w"})
        res = client.put(
            f"{API}/wiki/wikis/w/pages/p", json={"content": "# p\n"}, headers={"If-None-Match": "*"}
        )
        assert res.status_code == 422
        assert res.json()["error"]["details"]["rule_id"] == "needs-key"
        ok = client.put(
            f"{API}/wiki/wikis/w/pages/p",
            json={"content": "---\nsource: x\n---\n# p\n"},
            headers={"If-None-Match": "*"},
        )
        assert ok.status_code == 201
    off = {SECTION_KEY: {"write_checks": [{"id": "needs-key", "enabled": False}]}}
    assembly = kit.make_assembly(
        tmp_path / "off", write_check_module(check), settings=off, database=None
    )
    with kit.client_for(assembly) as client:
        client.post(f"{API}/wiki/wikis", json={"name": "w"})
        res = client.put(
            f"{API}/wiki/wikis/w/pages/p", json={"content": "# p\n"}, headers={"If-None-Match": "*"}
        )
        assert res.status_code == 201


def test_write_check_plugin_needs_setting(tmp_path: Path, kit: Any) -> None:
    ep = importlib.metadata.EntryPoint(
        name="needs-key",
        value="agent_console_mod_wiki.testing:FrontMatterKeyCheck",
        group=WRITE_CHECKS_GROUP,
    )
    registry = new_write_check_registry()
    reports = load_write_check_plugins(registry, entry_points=[ep])
    assert [r.status for r in reports] == ["loaded"]
    made = registry.get("needs-key")({"key": "k"})
    assert made.id == "needs-key"
    with pytest.raises(TypeError):
        as_write_check_factory(42)

    from agent_console_mod_wiki.plugins import WRITE_CHECKS_EXTENSION
    from agent_console_modkit import ExtensionRegistries

    registries = ExtensionRegistries()
    host = registries.extension(WRITE_CHECKS_EXTENSION, validator=as_write_check_factory)
    host.register("needs-key", FrontMatterKeyCheck)

    def assembly_with(settings: Any, root: Path) -> Any:
        from agent_console_mod_wiki.testing import static_settings_module
        from agent_console_modkit import BaseServices, Paths, assemble

        base = BaseServices(
            paths=Paths(base_dir=root, workspace=root / "ws", state=root / "state"),
            registries=registries,
        )
        return assemble([module, static_settings_module(settings)], base=base)

    # 설치만으로는 쓰기 판단이 바뀌지 않는다
    with kit.client_for(assembly_with({}, tmp_path / "a")) as client:
        client.post(f"{API}/wiki/wikis", json={"name": "w"})
        res = client.put(
            f"{API}/wiki/wikis/w/pages/p", json={"content": "# p\n"}, headers={"If-None-Match": "*"}
        )
        assert res.status_code == 201
    enabled = {SECTION_KEY: {"write_checks": [{"id": "needs-key", "options": {"key": "src"}}]}}
    with kit.client_for(assembly_with(enabled, tmp_path / "b")) as client:
        client.post(f"{API}/wiki/wikis", json={"name": "w"})
        res = client.put(
            f"{API}/wiki/wikis/w/pages/p", json={"content": "# p\n"}, headers={"If-None-Match": "*"}
        )
        assert res.status_code == 422
        assert res.json()["error"]["details"]["issues"][0]["message"] == "src 필요"


def test_search_backend_fallback_is_degraded(tmp_path: Path, kit: Any, database: Any) -> None:
    settings = {SECTION_KEY: {"search_backend": "not-installed"}}
    with kit.client_for(kit.make_assembly(tmp_path, settings=settings, database=database)) as c:
        info = c.get(f"{API}/wiki/info").json()
        assert "wiki.search_degraded" in {i["code"] for i in info["issues"]}
        c.post(f"{API}/wiki/wikis", json={"name": "w"})
        kit.write_page(c, "w", "p", "# 위키는 좋다\n")
        found = c.get(f"{API}/wiki/wikis/w/search", params={"q": "위키"}).json()
        assert found["backend"] == "scan"
        assert [h["path"] for h in found["items"]] == ["p"]


def test_library_rules_used_by_is_empty(tmp_path: Path, kit: Any) -> None:
    kinds = definition_kinds(
        wiki_kind="wiki", wiki_dir="wikis", rules_kind="wiki-rules", rules_dir="wiki-rules"
    )
    library = InMemoryDefinitionStore(kinds[1:])
    with kit.client_for(kit.make_assembly(tmp_path, library_module(library))) as client:
        info = client.get(f"{API}/wiki/info").json()
        assert info["capabilities"]["rules_library"] is True
        kit.make_rules(client, "lib")
        assert library.list_ids("wiki-rules") == ["lib"]
        client.post(f"{API}/wiki/wikis", json={"name": "w", "rules": ["lib"]})
        assert client.get(f"{API}/wiki/rules").json()[0]["used_by"] == []
        assert client.get(f"{API}/wiki/wikis/w").json()["rules"]["rules"][0]["missing"] is False


def test_standalone_serves_wiki_routes(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from agent_console_modkit.host import HostSettings

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
            seen["wikis"] = client.get(f"{API}/wiki/wikis").json()
            seen["created"] = client.post(f"{API}/wiki/wikis", json={"name": "Solo"}).status_code
            page = client.put(
                f"{API}/wiki/wikis/solo/pages/p",
                json={"content": "# p\n"},
                headers={"If-None-Match": "*"},
            )
            seen["page"] = page.status_code
            history = client.get(f"{API}/wiki/wikis/solo/pages/p/history").json()
            seen["history"] = [i["op"] for i in history["items"]]
            seen["modules"] = [m["id"] for m in client.get(f"{API}/modules").json()]

    out = io.StringIO()
    code = main(["--config", str(config)], serve=serve, out=out, environ={})
    assert code == 0, out.getvalue()
    assert seen["wikis"] == []
    assert seen["created"] == 201
    assert seen["page"] == 201
    assert seen["history"] == ["create"]
    assert "mod-wiki" in seen["modules"]
    assert (tmp_path / "ws" / "wiki" / "wikis" / "solo.yaml").is_file()
    assert (tmp_path / "ws" / "wiki" / "wiki-pages" / "solo" / "p.md").is_file()
    assert (tmp_path / "state" / "console.sqlite3").is_file()


def test_openapi_components_are_contract_models(tmp_path: Path, kit: Any) -> None:
    assembly = kit.make_assembly(tmp_path)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
    schema = create_host_app(assembly, policy=policy).openapi()
    defs = json.loads(render_schema())["$defs"]
    components = schema.get("components", {}).get("schemas", {})
    wiki_paths = [p for p in schema["paths"] if p.startswith(f"{API}/wiki")]
    assert len(wiki_paths) >= 25
    outside = sorted(set(components) - set(defs) - {"HTTPValidationError", "ValidationError"})
    assert outside == []


def _string_constants(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    examples = {
        id(kw.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "example"
    }
    skip = docstrings | examples
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip
    }


def test_no_hardcoded_names_in_source() -> None:
    """R0: 종류 이름·폴더 이름·검색 방식 id·기록 공간 접두는 패키지 데이터에만 있다."""
    data = package_defaults()
    names = {
        str(data[k])
        for k in (
            "wiki_kind",
            "rules_kind",
            "wiki_dir",
            "rules_dir",
            "pages_dir",
            "standalone_dir",
            "index_dir",
            "records_space_prefix",
        )
    }
    names |= {str(data["search"]["backend"]), str(data["search"]["fallback"])}
    # 모듈 정체성(사용자 설정 섹션 이름·웹 역할)은 코드 개념이다 — 종류 이름 기본값과 글자만 같다.
    allowed = {"config.py": {SECTION_KEY}, "module.py": {SECTION_KEY}}
    found: dict[str, set[str]] = {}
    for path in SRC.rglob("*.py"):
        hit = (_string_constants(path) & names) - allowed.get(path.name, set())
        if hit:
            found[path.name] = hit
    assert found == {}


def test_installer_index_options_reach_the_chosen_factory(tmp_path: Path, kit: Any) -> None:
    """설치자 ``search.index_options.<방식>``은 그 방식의 색인 공장에만 간다(키 뜻은 구현이 정한다).

    ``tokenizer``는 덮어쓸 수 있고, 앱이 정하는 ``case_insensitive``·``max_results``는
    덮이지 않는다.
    """
    from agent_console_mod_wiki.plugins import SEARCH_EXTENSION
    from agent_console_mod_wiki.testing import static_settings_module
    from agent_console_modkit import BaseServices, ExtensionRegistries, Paths, assemble
    from agent_console_wiki import ScanSearchIndex

    seen: list[dict[str, Any]] = []

    def capture(root: Path | None, options: Any) -> ScanSearchIndex:
        seen.append(dict(options))
        return ScanSearchIndex()

    registries = ExtensionRegistries()
    registries.extension(SEARCH_EXTENSION).register("captured", capture)
    installer = {
        "max_search_results": 7,
        "search": {
            "backend": "captured",
            "index_options": {
                "captured": {
                    "token_pattern": r"[\w-]+",
                    "tokenizer": "word",
                    "case_insensitive": False,
                    "max_results": 999,
                },
                "other": {"token_pattern": "x"},
            },
        },
    }
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=registries,
    )
    assembly = assemble(
        [module, static_settings_module({})],
        ModulesConfig(options={"mod-wiki": installer}),
        base=base,
    )
    with kit.client_for(assembly) as client:
        client.post(f"{API}/wiki/wikis", json={"name": "w"})
        kit.write_page(client, "w", "p", "# 위키 낱말\n")
        found = client.get(f"{API}/wiki/wikis/w/search", params={"q": "낱말"}).json()
    assert [h["path"] for h in found["items"]] == ["p"]  # 고른 공장이 만든 색인으로 찾는다
    assert seen, "색인 공장이 불리지 않았다"
    for options in seen:
        assert options["token_pattern"] == r"[\w-]+"
        assert options["tokenizer"] == "word"
        assert options["max_results"] == 7  # 앱 값이 이긴다
        assert options["case_insensitive"] is True  # 위키 문법 기본값(앱 값)
    assert all(o.get("token_pattern") != "x" for o in seen)  # 다른 방식의 옵션은 가지 않는다


@pytest.mark.parametrize("backend", ["scan", "sqlite-fts"])
def test_search_snippets_hide_values_caught_by_user_secret_rules(
    tmp_path: Path, kit: Any, backend: str
) -> None:
    """FU.23: 색인 공장에 지금 비밀 의심 규칙(``secrets.rules``)의 가리기가 간다.

    사용자 규칙으로만 잡히는 값은 기본 규칙으로는 그대로 보이고, 사용자 규칙을 더하면 검색
    스니펫·제목에서 가려진다(규칙이 바뀌면 색인을 다시 짓는다).
    """
    from types import SimpleNamespace

    from agent_console_mod_wiki.ports import DEFINITIONS_SAVED, SECRET_RULES
    from agent_console_modkit.testing import fake_module
    from agent_console_secret_rules import default_rules

    value = "CORP-482913"
    current = {"rules": default_rules()}
    provider = fake_module(
        "fake-secret-rules",
        kind="testing",
        provides=[SECRET_RULES],
        on_build=lambda ctx: ctx.provide(SECRET_RULES, lambda: current["rules"]),
    )
    assembly = kit.make_assembly(tmp_path, provider, options={"search": {"backend": backend}})

    def snippets(client: Any) -> str:
        found = client.get(f"{API}/wiki/wikis/w/search", params={"q": "사내번호"}).json()
        assert [h["path"] for h in found["items"]] == ["p"], found
        return json.dumps(found["items"], ensure_ascii=False)

    with kit.client_for(assembly) as client:
        client.post(f"{API}/wiki/wikis", json={"name": "w"})
        kit.write_page(client, "w", "p", f"# 사내번호 {value}\n\n사내번호는 {value} 이다.\n")
        assert value in snippets(client)  # 기본 규칙은 이 모양을 모른다(대조군)

        current["rules"] = default_rules().with_extra(value_patterns=[r"CORP-[0-9]{6}"])
        # 실제 서버에서는 비밀 규칙이 공통 설정에 있어 저장하면 정의 모듈이 이 토픽을 낸다 —
        # 신선도 창(기본 2초) 안이어도 지문을 다시 확인한다(P1.15)
        assembly.services.events.publish(
            DEFINITIONS_SAVED, SimpleNamespace(kind="settings", id="settings", version_hash="v2")
        )
        hidden = snippets(client)
        assert value not in hidden
        assert current["rules"].mask in hidden


def test_secret_rules_signature_changes_with_rules() -> None:
    from agent_console_mod_wiki.service import secret_rules_signature
    from agent_console_secret_rules import default_rules

    base = default_rules()
    assert secret_rules_signature(base) == secret_rules_signature(default_rules())
    extra = base.with_extra(value_patterns=[r"CORP-[0-9]{6}"])
    assert secret_rules_signature(extra) != secret_rules_signature(base)
    assert "CORP" not in secret_rules_signature(extra)  # 규칙 글은 담지 않는다(해시)


def test_index_options_default_is_empty_and_tokenizer_only() -> None:
    from agent_console_mod_wiki.settings import WikiSearchOptions

    opts = WikiSearchOptions()
    assert opts.index_options == {}
    assert opts.factory_options("scan") == {"tokenizer": opts.tokenizer}
    assert opts.factory_options(None) == {"tokenizer": opts.tokenizer}
