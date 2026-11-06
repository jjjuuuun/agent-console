"""공간(design §7R.4): ``wiki.spaces`` 프로젝트 공간·격리·읽기 전용·연동 없음, ``records.spaces``
기록 DB(계보 ``wiki`` 범위 project, 호스트 DB에 대신 쓰지 않음), 서비스 포트 모양, WS 알림 키."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_contracts import SpaceRef
from agent_console_contracts.wiki import WikiChanged
from agent_console_mod_wiki import BRANCH, WIKI_SERVICE, WikiServicePort, WikiSpace
from agent_console_mod_wiki.testing import SimpleWikiSpace, records_module, spaces_module
from agent_console_mod_wiki.ws import change_key, change_publisher, changed_message
from agent_console_store import FileDefinitionStore, open_records_db
from agent_console_wiki import definition_kinds

API = "/api/v1"


def _space(root: Path, **kw: Any) -> SimpleWikiSpace:
    kinds = definition_kinds(
        wiki_kind="wiki", wiki_dir="wikis", rules_kind="wiki-rules", rules_dir="wiki-rules"
    )
    cfg = root / ".agent-console"
    return SimpleWikiSpace(
        store=FileDefinitionStore(cfg, kinds),
        pages_root=cfg / "wiki-pages",
        config_dir=".agent-console",
        index_dir=cfg / ".state" / "wiki-index",
        **kw,
    )


class RecordsPort:
    """``records.spaces`` 가짜: 공간 이름 → 그 폴더 기록 DB(계보 wiki를 올린다)."""

    def __init__(self, roots: dict[str, Path]) -> None:
        self.dbs = {
            name: open_records_db(
                root / ".agent-console" / "records.sqlite3",
                [BRANCH],
                backup_dir=root / ".agent-console" / ".state" / "backups",
            )
            for name, root in roots.items()
        }
        self.opened: list[str] = []

    def open(self, space: str) -> Any:
        self.opened.append(space)
        return self.dbs[space]

    def state(self, space: str) -> Any:
        return self.dbs[space].state

    def close(self, space: str) -> None:
        self.dbs[space].close()


def test_project_spaces_are_isolated_with_records(tmp_path: Path, kit: Any, database: Any) -> None:
    a, b = tmp_path / "A", tmp_path / "B"
    records = RecordsPort({"project:pa": a, "project:pb": b})
    spaces = spaces_module({"pa": _space(a), "pb": _space(b)})
    assembly = kit.make_assembly(tmp_path, spaces, records_module(records), database=database)
    with kit.client_for(assembly) as client:
        info = client.get(f"{API}/wiki/info", params={"project": "pa"}).json()
        assert info["pages_root"] == ".agent-console/wiki-pages"
        assert info["capabilities"]["history"] is True
        kit.make_rules(client, "pr", project="pa")
        made = client.post(
            f"{API}/wiki/wikis", json={"name": "notes", "rules": ["pr"]}, params={"project": "pa"}
        )
        assert made.status_code == 201, made.text
        assert made.json()["directory"] == ".agent-console/wiki-pages/notes"
        kit.write_page(client, "notes", "p", "# p\n", project="pa")
        # B 공간에는 없다, 단독 루트에도 없다
        assert client.get(f"{API}/wiki/wikis", params={"project": "pb"}).json() == []
        assert client.get(f"{API}/wiki/wikis").json() == []
        assert client.get(f"{API}/wiki/rules", params={"project": "pa"}).json()[0]["used_by"] == [
            {"id": "notes", "name": "notes"}
        ]
        history = client.get(
            f"{API}/wiki/wikis/notes/pages/p/history", params={"project": "pa"}
        ).json()
        assert [i["op"] for i in history["items"]] == ["create"]
        changes = client.get(f"{API}/wiki/changes", params={"project": "pa"}).json()
        assert [c["wiki"] for c in changes["items"]] == ["notes"]
        # 단독 공간 기록(호스트 DB)에는 남지 않는다
        assert client.get(f"{API}/wiki/changes").json()["items"] == []
    assert (a / ".agent-console" / "wiki-pages" / "notes" / "p.md").is_file()
    assert (a / ".agent-console" / "records.sqlite3").is_file()
    assert (a / ".agent-console" / ".state" / "wiki-index" / "notes.sqlite3").is_file()
    assert not (b / ".agent-console" / "wiki-pages").exists()
    assert "project:pa" in records.opened
    for db in records.dbs.values():
        db.close()


def test_project_without_records_has_no_history(tmp_path: Path, kit: Any, database: Any) -> None:
    a = tmp_path / "A"
    assembly = kit.make_assembly(tmp_path, spaces_module({"pa": _space(a)}), database=database)
    with kit.client_for(assembly) as client:
        info = client.get(f"{API}/wiki/info", params={"project": "pa"}).json()
        assert info["capabilities"]["history"] is False
        client.post(f"{API}/wiki/wikis", json={"name": "w"}, params={"project": "pa"})
        kit.write_page(client, "w", "p", "# p\n", project="pa")
        res = client.get(f"{API}/wiki/wikis/w/pages/p/history", params={"project": "pa"})
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "wiki.history_unavailable"
        # 앱 DB(단독 공간 기록)에 대신 쓰지 않았다
        assert client.get(f"{API}/wiki/changes").json()["items"] == []


def test_readonly_space_and_unavailable(tmp_path: Path, kit: Any) -> None:
    a = tmp_path / "A"
    writable = _space(a)
    with kit.client_for(kit.make_assembly(tmp_path, spaces_module({"pa": writable}))) as client:
        client.post(f"{API}/wiki/wikis", json={"name": "w"}, params={"project": "pa"})
        kit.write_page(client, "w", "p", "# p\n", project="pa")
    readonly = _space(a, config_writable=False)
    with kit.client_for(
        kit.make_assembly(tmp_path / "r", spaces_module({"pa": readonly}))
    ) as client:
        q = {"project": "pa"}
        assert client.get(f"{API}/wiki/wikis/w/pages/p", params=q).status_code == 200
        assert client.get(f"{API}/wiki/wikis/w/search", params={**q, "q": "p"}).status_code == 200
        res = client.put(
            f"{API}/wiki/wikis/w/pages/q",
            json={"content": "x"},
            headers={"If-None-Match": "*"},
            params=q,
        )
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "project.config_readonly"
        assert client.delete(f"{API}/wiki/wikis/w/pages/p", params=q).status_code == 409
        preview = client.post(
            f"{API}/wiki/wikis/w/pages/p/preview", json={"content": "y"}, params=q
        )
        assert preview.status_code == 200
        assert client.get(f"{API}/wiki/wikis", params={"project": "nope"}).status_code == 404
    with kit.client_for(kit.make_assembly(tmp_path / "n")) as client:
        res = client.get(f"{API}/wiki/wikis", params={"project": "pa"})
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "wiki.spaces_unavailable"


def test_service_port_shape_and_tool_targets(tmp_path: Path, kit: Any) -> None:
    a = tmp_path / "A"
    assembly = kit.make_assembly(tmp_path, spaces_module({"pa": _space(a)}))
    service = assembly.port(WIKI_SERVICE)
    assert isinstance(service, WikiServicePort)
    assert isinstance(_space(a), WikiSpace)
    with kit.client_for(assembly) as client:
        client.post(f"{API}/wiki/wikis", json={"name": "Docs"}, params={"project": "pa"})
    assert service.wiki_ids("pa") == ["docs"]
    targets = service.tool_targets("pa")
    assert targets["docs"].pages_dir == ".agent-console/wiki-pages/docs"
    assert targets["docs"].name == "Docs"
    assert service.repository("pa", "docs").wiki_id == "docs"
    seen: list[WikiChanged] = []
    kit.service_of(assembly).ports.publish = seen.append
    service.notify("pa", "docs", ["x", "x"])
    assert seen[0].paths == ["x"]
    assert seen[0].space.project_id == "pa"


def test_change_publisher_drops_repeats() -> None:
    seen: list[WikiChanged] = []
    pub = change_publisher(seen.append)
    one = WikiChanged(space=SpaceRef(), wiki_id="w", paths=["a"])
    pub(one)
    pub(one)
    pub(WikiChanged(space=SpaceRef(), wiki_id="w", paths=["a"], deleted=True))
    assert len(seen) == 2
    assert change_key(one) == (None, "w", ("a",), False, False)
    assert changed_message(one).type == "wiki.changed"
