"""위키 규칙 버전 경로(계약 0.14.2, ``/sdd/templates/{id}/versions``와 같은 모양)와 서버 후속
필드(``WikiInfo.rules_kind``·규칙 항목 글롭·경로 틀·이름·점검 켜진 이름·그래프 스킴 대상)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_console_mod_wiki.testing import SimpleWikiSpace, spaces_module
from agent_console_store import FileDefinitionStore
from agent_console_wiki import definition_kinds

API = "/api/v1"


def test_rule_versions_list_get_files_restore(tmp_path: Path, database: Any, kit: Any) -> None:
    settings: dict[str, Any] = {"wiki": {}}
    assembly = kit.make_assembly(tmp_path, settings=lambda: settings, database=database)
    with kit.client_for(assembly) as client:
        rule_id = kit.make_rules(client)
        base = f"{API}/wiki/rules/{rule_id}"
        first = client.get(base)
        put = client.put(
            base,
            json={**first.json()["rules"], "description": "둘째"},
            headers={"If-Match": first.headers["etag"]},
        )
        assert put.status_code == 200, put.text
        versions = client.get(f"{base}/versions")
        assert versions.status_code == 200, versions.text
        items = versions.json()
        # 만들기 + 파일 두 개 + 저장 = 4, 최신순
        assert len(items) == 4
        assert items[0]["version_hash"] == put.headers["etag"].strip('"')
        old = items[1]["version_hash"]  # 파일 두 개를 다 쓴 뒤, 설명 바꾸기 전
        one = client.get(f"{base}/versions/{old}")
        assert one.status_code == 200
        assert one.json()["content"].get("description", "") != "둘째"
        files = client.get(f"{base}/versions/{old}/files").json()
        assert {f["path"] for f in files} == {"instructions.md", "templates/note.md"}
        body = client.get(f"{base}/versions/{old}/files/instructions.md")
        assert body.status_code == 200
        assert body.text == "결정만 기록하세요.\n"
        assert client.get(f"{base}/versions/nope").status_code == 404
        assert client.get(f"{base}/versions/{old}/files/none.md").status_code == 404

        # If-Match 없음 428, 다름 412
        assert client.post(f"{base}/versions/{old}/restore").status_code == 428
        wrong = client.post(f"{base}/versions/{old}/restore", headers={"If-Match": '"x"'})
        assert wrong.status_code == 412
        restored = client.post(
            f"{base}/versions/{old}/restore", headers={"If-Match": put.headers["etag"]}
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["message"] == f"restored from {old}"
        now = client.get(base)
        assert now.headers["etag"] == restored.headers["etag"]
        assert now.json()["rules"].get("description", "") == ""
        # 같은 내용이라 버전 해시는 그 버전과 같다(버전 해시 = 내용 해시)
        assert restored.headers["etag"].strip('"') == old

        # 비밀 의심 본문: 사람 쓰기 warn(기본) → 되돌림 + X-Console-Issues, reject → 422
        cur = client.get(base).headers["etag"]
        res = client.put(
            f"{base}/files/instructions.md",
            content=f"키 {kit.SECRET}\n".encode(),
            headers={"If-Match": cur},
        )
        assert res.status_code == 200, res.text
        secret_hash = res.headers["etag"].strip('"')
        clean = client.post(
            f"{base}/versions/{old}/restore", headers={"If-Match": res.headers["etag"]}
        )
        assert clean.status_code == 200, clean.text
        settings["wiki"] = {"secret_scan": {"user": "reject"}}
        rejected = client.post(
            f"{base}/versions/{secret_hash}/restore", headers={"If-Match": clean.headers["etag"]}
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "wiki.secret_rejected"
        assert kit.SECRET not in rejected.text
        settings["wiki"] = {}
        warned = client.post(
            f"{base}/versions/{secret_hash}/restore",
            headers={"If-Match": clean.headers["etag"]},
            json={"message": "다시"},
        )
        assert warned.status_code == 200, warned.text
        assert warned.json()["message"] == "다시"
        issues = json.loads(warned.headers["x-console-issues"])
        assert [i["code"] for i in issues] == ["wiki.secret_suspect"]
        assert kit.SECRET not in warned.headers["x-console-issues"]

        # 지운 규칙은 If-Match 없이 되살린다
        assert client.delete(base).status_code == 204
        assert client.get(f"{base}/versions").status_code == 200
        revived = client.post(f"{base}/versions/{old}/restore")
        assert revived.status_code == 200, revived.text
        assert client.get(base).status_code == 200


def test_rule_versions_in_readonly_space(tmp_path: Path, kit: Any) -> None:
    kinds = definition_kinds(
        wiki_kind="wiki", wiki_dir="wikis", rules_kind="wiki-rules", rules_dir="wiki-rules"
    )
    cfg = tmp_path / "A" / ".agent-console"
    store = FileDefinitionStore(cfg, kinds)  # 버전 이력(메모리)을 두 조립이 함께 본다

    def space(**kw: Any) -> SimpleWikiSpace:
        return SimpleWikiSpace(store=store, pages_root=cfg / "wiki-pages", **kw)

    q = {"project": "pa"}
    with kit.client_for(kit.make_assembly(tmp_path, spaces_module({"pa": space()}))) as client:
        kit.make_rules(client, "pr", project="pa")
    with kit.client_for(
        kit.make_assembly(tmp_path / "r", spaces_module({"pa": space(config_writable=False)}))
    ) as client:
        items = client.get(f"{API}/wiki/rules/pr/versions", params=q).json()
        assert len(items) == 3
        res = client.post(
            f"{API}/wiki/rules/pr/versions/{items[-1]['version_hash']}/restore",
            params=q,
            headers={"If-Match": '"x"'},
        )
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "project.config_readonly"


def test_info_rules_kind_entries_lint_checks_and_graph(
    standalone: tuple[Any, Any], kit: Any
) -> None:
    client, _ = standalone
    info = client.get(f"{API}/wiki/info").json()
    assert info["rules_kind"] == "wiki-rules"
    rule_id = kit.make_rules(client)
    client.post(f"{API}/wiki/wikis", json={"name": "w", "rules": [rule_id]})
    view = client.get(f"{API}/wiki/wikis/w").json()
    entries = {e["id"]: e for e in view["rules"]["entries"]}
    assert entries["no-temp"]["applies_to"] == ["**"]
    assert entries["agents-no-delete"]["applies_to"] == []
    assert entries["note"]["path"] == "notes/{slug}"
    assert entries["note"]["title"] == "메모"
    assert entries["stale"].get("applies_to") is None
    kit.write_page(client, "w", "p", "# p\n[[없음]]\n")
    lint = client.get(f"{API}/wiki/wikis/w/lint").json()
    assert lint["partial"] is False
    assert lint["skipped"] == []
    assert "lint_rules" in lint["enabled_checks"]
    assert "broken_link" in lint["enabled_checks"]
    graph = client.get(f"{API}/wiki/wikis/w/graph").json()
    assert all(n.get("scheme_target") is None for n in graph["nodes"])
