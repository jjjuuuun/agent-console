"""한 바퀴(design §7R.0 중 서버 몫, 7R.12 완료 기준): 모듈 혼자 켠 서버(단독 루트)에서 규칙 → 위키 →
페이지 쓰기·링크·옮기기·기록·검색·그래프·점검, §7R.18.1 경로(미리보기·링크 넣기·틀 렌더·변경·
``op=``·pruned·내보내기·가져오기)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts.wiki import WikiChanged
from agent_console_modkit import Assembly

API = "/api/v1"


def _capture(kit: Any, assembly: Assembly) -> list[WikiChanged]:
    seen: list[WikiChanged] = []
    service = kit.service_of(assembly)
    service.ports.publish = seen.append
    return seen


def test_full_lap_standalone(
    standalone: tuple[TestClient, Assembly], tmp_path: Path, kit: Any
) -> None:
    client, assembly = standalone
    events = _capture(kit, assembly)
    # 빈 workspace: 위키 0, 규칙 0
    assert client.get(f"{API}/wiki/wikis").json() == []
    assert client.get(f"{API}/wiki/rules").json() == []
    info = client.get(f"{API}/wiki/info").json()
    assert info["capabilities"]["history"] is True
    assert info["capabilities"]["runs"] is False
    assert info["pages_root"] == "wiki-pages"
    assert info["writable"] is True  # 0.14.1: 단독 공간은 쓸 수 있다

    rule_id = kit.make_rules(client)
    created = client.post(
        f"{API}/wiki/wikis", json={"name": "Team Notes", "rules": [rule_id], "home": "index"}
    )
    assert created.status_code == 201, created.text
    wiki = created.json()["wiki"]["id"]
    assert wiki == "team-notes"
    assert created.json()["rules"]["instructions"].count("결정만 기록하세요.") == 1
    assert {e["id"] for e in created.json()["rules"]["entries"]} == {
        "no-temp",
        "agents-no-delete",
        "stale",
        "note",
    }

    kit.write_page(client, wiki, "index", "# 첫 페이지\n\n[[alpha]] 그리고 [[gone]]\n")
    kit.write_page(client, wiki, "alpha", "# 알파\n\n[베타](beta.md)\n")
    kit.write_page(client, wiki, "beta", "---\ntags: [x]\n---\n# 베타\n\n[[alpha|알파로]]\n")
    assert {e.paths[0] for e in events if e.paths} >= {"index", "alpha", "beta"}

    # 페이지 보기: 링크(UTF-16 범위)·백링크·ETag
    page = client.get(f"{API}/wiki/wikis/{wiki}/pages/index")
    assert page.status_code == 200
    body = page.json()
    assert page.headers["etag"] == f'"{body["content_hash"]}"'
    statuses = {link["target"]: link["status"] for link in body["links"]}
    assert statuses == {"alpha": "ok", "gone": "broken"}
    first = body["links"][0]
    assert body["content"][first["start"] : first["end"]] == "[[alpha]]"
    alpha = client.get(f"{API}/wiki/wikis/{wiki}/pages/alpha").json()
    assert {b["path"] for b in alpha["backlinks"]} == {"index", "beta"}

    # 그래프·점검(끊긴 링크)·검색
    graph = client.get(f"{API}/wiki/wikis/{wiki}/graph").json()
    assert {n["path"] for n in graph["nodes"]} >= {"index", "alpha", "beta"}
    lint = client.get(f"{API}/wiki/wikis/{wiki}/lint").json()
    assert "wiki.broken_link" in {i["code"] for i in lint["issues"]}
    assert lint["counts"]
    hits = client.get(f"{API}/wiki/wikis/{wiki}/search", params={"q": "알파"}).json()
    assert {h["path"] for h in hits["items"]} >= {"alpha"}

    # 위키 목록 카드: 요청 하나로 값
    [card] = client.get(f"{API}/wiki/wikis").json()
    assert card["pages"] == 3
    assert card["broken_links"] == 1
    assert card["lint_counts"]
    assert card["rules"][0]["id"] == rule_id
    assert card["updated_by"]["kind"] == "user"
    assert card["directory"] == f"wiki-pages/{wiki}"

    # 미리보기: 금지 패턴 → would_reject, 파일·기록·이벤트 불변
    before_events = len(events)
    history_before = client.get(f"{API}/wiki/wikis/{wiki}/pages/alpha/history").json()
    preview = client.post(
        f"{API}/wiki/wikis/{wiki}/pages/alpha/preview", json={"content": "TEMPNOTE 여기\n"}
    ).json()
    assert preview["would_reject"] is True
    assert preview["rule_results"][0]["rule_id"] == "no-temp"
    assert len(events) == before_events
    assert client.get(f"{API}/wiki/wikis/{wiki}/pages/alpha/history").json() == history_before

    # 같은 본문 쓰기 = 422 details 같은 규칙
    etag = client.get(f"{API}/wiki/wikis/{wiki}/pages/alpha").headers["etag"]
    rejected = client.put(
        f"{API}/wiki/wikis/{wiki}/pages/alpha",
        json={"content": "TEMPNOTE 여기\n"},
        headers={"If-Match": etag},
    )
    assert rejected.status_code == 422
    error = rejected.json()["error"]
    assert error["code"] == "wiki.rule_rejected"
    assert error["details"]["rule_id"] == "no-temp"
    assert error["details"]["lines"] == [1]

    # 비밀 의심(사람 = warn) → 저장 + X-Console-Issues
    warned = client.put(
        f"{API}/wiki/wikis/{wiki}/pages/alpha",
        json={"content": f"# 알파\n\nkey {kit.SECRET}\n[베타](beta.md)\n"},
        headers={"If-Match": etag},
    )
    assert warned.status_code == 200, warned.text
    issues = json.loads(warned.headers["x-console-issues"])
    assert issues[0]["code"] == "wiki.secret_suspect"

    # 있는 페이지를 If-Match 없이 고치면 428, 틀린 해시는 412
    assert (
        client.put(f"{API}/wiki/wikis/{wiki}/pages/alpha", json={"content": "x"}).status_code == 428
    )
    stale = client.put(
        f"{API}/wiki/wikis/{wiki}/pages/alpha", json={"content": "x"}, headers={"If-Match": etag}
    )
    assert stale.status_code == 412

    # 옮기기: 다른 두 페이지의 링크 문자열만 바뀐다
    root = tmp_path / "ws" / "wiki" / "wiki-pages" / wiki
    index_before = (root / "index.md").read_text(encoding="utf-8")
    dry = client.post(
        f"{API}/wiki/wikis/{wiki}/pages/alpha/move", json={"to": "docs/alpha", "dry_run": True}
    ).json()
    assert dry["moved"] is False
    # 옮기는 페이지 자신의 상대 링크도 새 위치 기준으로 고친다(docs/alpha)
    assert {r["path"] for r in dry["rewritten"]} == {"index", "beta", "docs/alpha"}
    moved = client.post(f"{API}/wiki/wikis/{wiki}/pages/alpha/move", json={"to": "docs/alpha"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["moved"] is True
    index_after = (root / "index.md").read_text(encoding="utf-8")
    assert index_after == index_before.replace("[[alpha]]", "[[docs/alpha]]")
    assert (root / "docs" / "alpha.md").exists()

    # 기록·되돌리기·지운 페이지
    history = client.get(f"{API}/wiki/wikis/{wiki}/pages/docs/alpha/history").json()
    assert history["items"][0]["op"] == "move_in"
    deleted = client.delete(f"{API}/wiki/wikis/{wiki}/pages/beta")
    assert deleted.status_code == 204
    gone = client.get(f"{API}/wiki/wikis/{wiki}/pages/beta")
    assert gone.status_code == 404
    assert gone.json()["error"]["code"] == "wiki.page_not_found"
    assert gone.json()["error"]["details"]["has_history"] is True
    beta_history = client.get(f"{API}/wiki/wikis/{wiki}/pages/beta/history").json()
    first_version = beta_history["items"][-1]["version"]
    content = client.get(f"{API}/wiki/wikis/{wiki}/pages/beta/history/{first_version}")
    assert content.status_code == 200
    assert "베타" in content.text
    restored = client.post(
        f"{API}/wiki/wikis/{wiki}/pages/beta/restore", json={"version": first_version}
    )
    assert restored.status_code == 200, restored.text
    latest = client.get(f"{API}/wiki/wikis/{wiki}/pages/beta/history").json()["items"][0]
    assert latest["op"] == "restore"

    # 변경(위키·공간 전체·op 거르기)
    changes = client.get(f"{API}/wiki/wikis/{wiki}/changes").json()["items"]
    assert changes
    assert all(c["wiki"] == wiki for c in changes)
    space_wide = client.get(f"{API}/wiki/changes", params={"op": "delete,restore"}).json()
    assert {c["op"] for c in space_wide["items"]} == {"delete", "restore"}

    # 외부 변경: 파일 직접 고침 → scan이 external
    (root / "index.md").write_text("# 첫 페이지\n\n밖에서 고침\n", encoding="utf-8")
    scan = client.post(f"{API}/wiki/wikis/{wiki}/scan").json()
    assert scan["external"] == ["index"]
    assert events[-1].external is True

    # 위키를 지워도 페이지 폴더는 남는다
    view = client.get(f"{API}/wiki/wikis/{wiki}")
    assert (
        client.delete(
            f"{API}/wiki/wikis/{wiki}", headers={"If-Match": view.headers["etag"]}
        ).status_code
        == 204
    )
    assert (root / "index.md").exists()
    assert client.get(f"{API}/wiki/wikis/{wiki}/pages/index").status_code == 404


def test_link_text_templates_export_import(
    standalone: tuple[TestClient, Assembly], kit: Any
) -> None:
    client, _assembly = standalone
    rule_id = kit.make_rules(client)
    wiki = client.post(f"{API}/wiki/wikis", json={"name": "w", "rules": [rule_id]}).json()["wiki"][
        "id"
    ]
    kit.write_page(client, wiki, "a/one", "# 하나\n")
    text = client.post(
        f"{API}/wiki/wikis/{wiki}/link-text", json={"from_page": "b/two", "target": "a/one"}
    ).json()
    assert text["text"] == "[[a/one|하나]]"
    relative = client.post(
        f"{API}/wiki/wikis/{wiki}/link-text",
        json={"from_page": "b/two", "target": "a/one", "rule_id": "relative"},
    ).json()
    assert relative["text"] == "[하나](../a/one.md)"

    templates = client.get(f"{API}/wiki/wikis/{wiki}/templates").json()
    assert [t["id"] for t in templates] == ["note"]
    rendered = client.post(
        f"{API}/wiki/wikis/{wiki}/templates/note/render", json={"title": "새 메모"}
    ).json()
    assert rendered["path"] == "notes/새-메모"
    assert rendered["content"].startswith("# 새 메모")
    missing = client.post(f"{API}/wiki/wikis/{wiki}/templates/nope/render", json={})
    assert missing.status_code == 404

    # 틀로 새 페이지(content 비움)
    res = client.put(
        f"{API}/wiki/wikis/{wiki}/pages/notes/first",
        json={"content": "", "template": "note"},
        headers={"If-None-Match": "*"},
    )
    assert res.status_code == 201
    assert res.json()["content"].startswith("# ")

    exported = client.post(f"{API}/wiki/wikis/{wiki}/export")
    assert exported.status_code == 200
    disposition = exported.headers["content-disposition"]
    assert disposition.startswith(f'attachment; filename="{wiki}.zip"')
    assert "filename*=UTF-8''" in disposition
    names = zipfile.ZipFile(io.BytesIO(exported.content)).namelist()
    assert "a/one.md" in names

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a/one.md", "# 덮어쓰기\n")
        zf.writestr("c/new.md", "# 새것\n")
        zf.writestr("../evil.md", "x")
        zf.writestr("image.png", b"\x89PNG")
    data = buf.getvalue()
    dry = client.post(
        f"{API}/wiki/wikis/{wiki}/import",
        content=data,
        params={"dry_run": "true", "policy": "rename"},
    ).json()
    assert dry["dry_run"] is True
    assert client.get(f"{API}/wiki/wikis/{wiki}/pages/c/new").status_code == 404
    result = client.post(
        f"{API}/wiki/wikis/{wiki}/import", content=data, params={"policy": "rename"}
    ).json()
    by_path = {i["path"]: i for i in result["items"]}
    assert by_path["c/new"]["status"] == "created"
    assert by_path["a/one"]["status"] == "renamed"
    assert any(i["status"] == "rejected" for i in result["items"])
    assert client.get(f"{API}/wiki/wikis/{wiki}/pages/c/new").status_code == 200


def test_history_pruned_and_version_not_found(tmp_path: Path, database: Any, kit: Any) -> None:
    assembly = kit.make_assembly(
        tmp_path, database=database, settings={"wiki": {"max_versions_per_page": 2}}
    )
    with kit.client_for(assembly) as client:
        wiki = client.post(f"{API}/wiki/wikis", json={"name": "w"}).json()["wiki"]["id"]
        for n in range(4):
            kit.write_page(client, wiki, "p", f"# v{n}\n")
        history = client.get(f"{API}/wiki/wikis/{wiki}/pages/p/history").json()
        assert history["pruned"] is True
        versions = [i["version"] for i in history["items"]]
        assert 1 in versions
        assert 2 not in versions
        missing = client.get(f"{API}/wiki/wikis/{wiki}/pages/p/history/2")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "wiki.version_not_found"


def test_rules_check_and_library_used_by(standalone: tuple[TestClient, Assembly], kit: Any) -> None:
    client, _ = standalone
    rule_id = kit.make_rules(client)
    client.post(f"{API}/wiki/wikis", json={"name": "w", "rules": [rule_id]})
    listed = client.get(f"{API}/wiki/rules").json()
    assert listed[0]["counts"] == {"write": 2, "lint": 1, "templates": 1}
    assert listed[0]["has_instructions"] is True
    assert listed[0]["used_by"] == [{"id": "w", "name": "w"}]
    bad = {
        **kit.RULES,
        "id": "bad",
        "write_rules": [{"id": "all", "action": "reject", "message": "m"}],
    }
    check = client.post(f"{API}/wiki/rules/check", json={"rules": bad, "files": []}).json()
    codes = {i["code"] for i in check["issues"]}
    assert "wiki.always_rejects" in codes
    assert "wiki.template_missing" in codes
    view = client.get(f"{API}/wiki/rules/{rule_id}")
    assert view.json()["used_by"] == [{"id": "w", "name": "w"}]
    files = client.get(f"{API}/wiki/rules/{rule_id}/files").json()
    assert {f["path"] for f in files} == {"instructions.md", "templates/note.md"}
    put = client.put(
        f"{API}/wiki/rules/{rule_id}",
        json={**view.json()["rules"], "description": "바꿈"},
        headers={"If-Match": view.headers["etag"]},
    )
    assert put.status_code == 200, put.text
    assert put.json()["rules"]["description"] == "바꿈"
    # 규칙이 바뀌면 저장소를 다시 만든다(규칙 요약에 반영)
    assert client.get(f"{API}/wiki/wikis/w").json()["rules"]["write_rules"] == 2
