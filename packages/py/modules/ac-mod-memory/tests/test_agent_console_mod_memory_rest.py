"""mod-memory REST(design §5.7R.5.2): 모듈 혼자 켠 서버에서 CRUD·검색·버전·정리·내보내기/가져오기.

- 빈 워크스페이스: 범위 종류 = 패키지 기본(개수만 본다, 이름은 데이터), 항목 0.
- 쓰기 검사 실패는 422(``memory.secret_rejected``·``memory.too_large``·``memory.invalid_key``),
  응답 어디에도 비밀 값·본문 조각이 없다.
- ``If-Match``: PUT은 필수(428), 다르면 412 + ``current_version``. 만들기 중복은 409.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_console_contracts import ErrorCodes
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_memory import load_default_scope_kinds
from agent_console_modkit import Assembly
from agent_console_store import SqliteDatabase

type MakeAssembly = Callable[..., Assembly]
type ClientOf = Callable[[Assembly], Any]
type WarningCodes = Callable[[Assembly], list[str]]

API = "/api/v1"
NOTES = {"kind": "notes", "id": "p1"}
SECRET = "sk-ant-api03-" + "A1b2C3d4E5f6G7h8" * 3

ENTRIES = f"{API}/memory/entries"


def _create(client: Any, key: str, content: str = "본문", **extra: Any) -> dict[str, Any]:
    response = client.post(ENTRIES, json={"scope": NOTES, "key": key, "content": content, **extra})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    assert response.headers["etag"] == f'"{body["version"]}"'
    return body


def test_empty_workspace_lists_default_kinds_and_no_entries(
    database: SqliteDatabase,
    make_assembly: MakeAssembly,
    client_of: ClientOf,
) -> None:
    with client_of(make_assembly(database=database)) as client:
        kinds = client.get(f"{API}/memory/scope-kinds").json()
        assert len(kinds["kinds"]) == len(load_default_scope_kinds())
        assert {k["origin"] for k in kinds["kinds"]} == {"default"}
        assert kinds["include_defaults"] is True
        assert client.get(f"{API}/memory/scopes").json() == []
        page = client.get(ENTRIES).json()
        assert page["items"] == []
        assert client.get(f"{API}/memory/tags").json() == {"tags": [], "truncated": False}


def test_crud_versions_and_conflicts(
    database: SqliteDatabase,
    make_assembly: MakeAssembly,
    client_of: ClientOf,
    warning_codes: WarningCodes,
) -> None:
    assembly = make_assembly(database=database)
    with client_of(assembly) as client:
        created = _create(client, "결정/api-버전", "v1 사용", tags=["api"])
        assert created["version"] == 1
        assert created["created_by"]["kind"] == "user"
        entry_id = created["id"]

        duplicate = client.post(
            ENTRIES, json={"scope": NOTES, "key": "결정/api-버전", "content": "x"}
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["details"]["entry_id"] == entry_id

        missing = client.put(f"{ENTRIES}/{entry_id}", json={"content": "v2"})
        assert missing.status_code == 428
        assert missing.json()["error"]["code"] == ErrorCodes.VERSION_REQUIRED

        updated = client.put(
            f"{ENTRIES}/{entry_id}", json={"content": "v2 사용"}, headers={"If-Match": '"1"'}
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["version"] == 2
        assert updated.headers["etag"] == '"2"'

        stale = client.put(
            f"{ENTRIES}/{entry_id}", json={"content": "v3"}, headers={"If-Match": "1"}
        )
        assert stale.status_code == 412
        assert stale.json()["error"]["details"]["current_version"] == 2

        bad = client.put(f"{ENTRIES}/{entry_id}", json={"content": "v3"}, headers={"If-Match": "x"})
        assert bad.status_code == 422

        versions = client.get(f"{ENTRIES}/{entry_id}/versions").json()
        assert [(v["version"], v["op"]) for v in versions] == [(1, "create"), (2, "update")]
        first = client.get(f"{ENTRIES}/{entry_id}/versions/1").json()
        assert first["content"] == "v1 사용"
        assert client.get(f"{ENTRIES}/{entry_id}/versions/9").status_code == 404

        restored = client.post(f"{ENTRIES}/{entry_id}/restore", params={"version": 1}).json()
        assert restored["content"] == "v1 사용"
        assert restored["version"] == 3

        archived = client.post(f"{ENTRIES}/{entry_id}/archive").json()
        assert archived["archived"] is True
        assert client.get(ENTRIES).json()["items"] == []  # 보관은 기본 목록에서 빠진다
        with_archived = client.get(ENTRIES, params={"include_archived": True}).json()
        assert [i["id"] for i in with_archived["items"]] == [entry_id]
        assert client.post(f"{ENTRIES}/{entry_id}/unarchive").json()["archived"] is False

        moved = client.post(
            f"{ENTRIES}/{entry_id}/move",
            json={"to_key": "결정/api"},
            headers={"If-Match": str(archived["version"] + 1)},
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["key"] == "결정/api"

        deleted = client.delete(f"{ENTRIES}/{entry_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted_at"] is not None
        assert client.get(f"{ENTRIES}/{entry_id}").status_code == 404
        assert (
            client.get(f"{ENTRIES}/{entry_id}", params={"include_deleted": True}).status_code == 200
        )
        back = client.post(f"{ENTRIES}/{entry_id}/restore")
        assert back.status_code == 200
        assert back.json()["deleted_at"] is None

        purged = client.delete(f"{ENTRIES}/{entry_id}", params={"purge": True})
        assert purged.status_code == 204
        assert (
            client.get(f"{ENTRIES}/{entry_id}", params={"include_deleted": True}).status_code == 404
        )
        assert client.get(f"{ENTRIES}/{entry_id}/versions").status_code == 404
        assert client.get(f"{ENTRIES}/missing").status_code == 404
    assert KnownIssueCodes.MEMORY_STORAGE_MEMORY not in warning_codes(assembly)


def test_write_checks_reject_without_echoing_values(
    database: SqliteDatabase,
    make_assembly: MakeAssembly,
    client_of: ClientOf,
) -> None:
    with client_of(make_assembly(database=database, options={"max_entry_bytes": 16})) as client:
        secret = client.post(ENTRIES, json={"scope": NOTES, "key": "s", "content": f"키 {SECRET}"})
        assert secret.status_code == 422
        error = secret.json()["error"]
        assert error["code"] == ErrorCodes.MEMORY_SECRET_REJECTED
        assert error["details"]["field"] == "content"
        assert SECRET not in secret.text
        assert SECRET[:16] not in secret.text

        big = client.post(ENTRIES, json={"scope": NOTES, "key": "big", "content": "가" * 20})
        assert big.status_code == 422
        assert big.json()["error"]["code"] == ErrorCodes.MEMORY_TOO_LARGE
        assert big.json()["error"]["details"]["limit"] == "max_entry_bytes"

        bad_key = client.post(ENTRIES, json={"scope": NOTES, "key": "a/../b", "content": "x"})
        assert bad_key.status_code == 422
        assert bad_key.json()["error"]["code"] == ErrorCodes.MEMORY_INVALID_KEY

        assert client.get(ENTRIES).json()["items"] == []


def test_redact_policy_from_user_settings(
    database: SqliteDatabase,
    make_assembly: MakeAssembly,
    client_of: ClientOf,
) -> None:
    settings = {"memory": {"secrets": "redact"}}
    with client_of(make_assembly(database=database, settings=settings)) as client:
        created = _create(client, "s", f"키 {SECRET} 끝")
        assert SECRET not in created["content"]
        assert SECRET not in client.get(f"{ENTRIES}/{created['id']}").text


def test_search_tags_scopes_and_query_errors(
    database: SqliteDatabase,
    make_assembly: MakeAssembly,
    client_of: ClientOf,
) -> None:
    with client_of(make_assembly(database=database)) as client:
        _create(client, "a", "사과 바나나 이야기", tags=["과일", "임시"])
        _create(client, "b", "바나나 우유", tags=["과일"])
        other = {"kind": "journal", "id": ""}
        response = client.post(ENTRIES, json={"scope": other, "key": "c", "content": "기록"})
        assert response.status_code == 201

        found = client.get(ENTRIES, params={"q": "바나나", "scope": "notes:p1"}).json()
        assert sorted(i["key"] for i in found["items"]) == ["a", "b"]
        tagged = client.get(ENTRIES, params={"tag": "임시"}).json()
        assert [i["key"] for i in tagged["items"]] == ["a"]
        by_key = client.get(ENTRIES, params={"sort": "key", "order": "asc"}).json()
        assert [i["key"] for i in by_key["items"]] == ["a", "b", "c"]
        page = client.get(ENTRIES, params={"limit": 1, "sort": "key", "order": "asc"}).json()
        assert len(page["items"]) == 1
        assert page["next_cursor"]

        tags = client.get(f"{API}/memory/tags").json()
        assert tags["tags"] == [{"tag": "과일", "entries": 2}, {"tag": "임시", "entries": 1}]

        scopes = client.get(f"{API}/memory/scopes").json()
        known = {(s["scope"]["kind"], s["kind_known"]) for s in scopes}
        assert ("notes", False) in known  # 사용자가 범위 종류를 만들지 않았다
        assert (
            client.get(f"{API}/memory/scopes", params={"kind": "journal"}).json()[0]["entries"] == 1
        )

        assert client.get(ENTRIES, params={"sort": "nope"}).status_code == 422
        assert client.get(ENTRIES, params={"order": "up"}).status_code == 422
        assert client.get(ENTRIES, params={"scope": "Bad Kind:x"}).status_code == 422
        assert client.get(ENTRIES, params={"cursor": "zz"}).status_code == 400


def test_user_scope_kinds_and_settings_warnings(
    database: SqliteDatabase,
    make_assembly: MakeAssembly,
    client_of: ClientOf,
    warning_codes: WarningCodes,
) -> None:
    settings = {
        "memory": {
            "include_default_scope_kinds": False,
            "scope_kinds": {
                "notes": {"label": "노트", "id": "{/project_id}"},
                "broken": {"label": "깨짐", "id": "{/nope}"},
            },
            "max_versions_per_entry": "많이",
        }
    }
    assembly = make_assembly(database=database, settings=settings)
    with client_of(assembly) as client:
        kinds = client.get(f"{API}/memory/scope-kinds").json()
        assert [(k["kind"], k["origin"]) for k in kinds["kinds"]] == [("notes", "user")]
        assert kinds["kinds"][0]["context_fields"] == ["project_id"]
        _create(client, "a")
        scopes = client.get(f"{API}/memory/scopes").json()
        assert scopes[0]["kind_known"] is True
    codes = warning_codes(assembly)
    assert codes.count(KnownIssueCodes.MEMORY_SETTINGS_INVALID) == 2


def test_settings_check_reports_paths(
    database: SqliteDatabase,
    make_assembly: MakeAssembly,
    client_of: ClientOf,
) -> None:
    with client_of(make_assembly(database=database)) as client:
        body = {
            "scope_kinds": {"x": {"label": "엑스", "id": "{/nope}"}},
            "retention": {
                "rules": [
                    {
                        "id": "ok",
                        "when": {"all": [{"path": "/tags", "op": "contains", "value": "t"}]},
                    },
                    {"id": "empty", "when": {}},
                    {"id": "weird", "when": {"all": [{"path": "/x", "op": "no_such", "value": 1}]}},
                ]
            },
        }
        issues = client.post(f"{API}/memory/settings/check", json=body).json()
        paths = {(i["severity"], i["path"]) for i in issues}
        assert ("error", "/scope_kinds/x/id") in paths
        assert any(p.startswith("/retention/rules/1") and s == "error" for s, p in paths)
        assert any(p.startswith("/retention/rules/2") for s, p in paths)
        assert not any(p.startswith("/retention/rules/0") for s, p in paths)
        assert client.post(f"{API}/memory/settings/check", json={}).json() == []


def test_retention_plan_and_apply(
    database: SqliteDatabase,
    make_assembly: MakeAssembly,
    client_of: ClientOf,
) -> None:
    rule = {
        "id": "temp-archive",
        "when": {"all": [{"path": "/tags", "op": "contains", "value": "임시"}]},
        "action": "archive",
    }
    settings: dict[str, Any] = {"memory": {}}
    with client_of(make_assembly(database=database, settings=lambda: settings)) as client:
        a = _create(client, "a", tags=["임시"])
        _create(client, "b", tags=["보존"])
        pinned = _create(client, "c", tags=["임시"], pinned=True)

        empty = client.post(f"{API}/memory/retention/plan").json()
        assert empty["count"] == 0  # 기본 규칙 없음
        assert client.post(f"{API}/memory/retention/apply").json()["archived"] == 0

        trial = client.post(f"{API}/memory/retention/plan", json={"rules": [rule]}).json()
        assert [i["entry_id"] for i in trial["items"]] == [a["id"]]  # 고정 항목은 빠진다
        bad = client.post(
            f"{API}/memory/retention/plan", json={"rules": [{"id": "x", "when": {}}]}
        ).json()
        assert bad["count"] == 0
        assert bad["issues"][0]["path"].startswith("/rules/0")

        settings["memory"] = {"retention": {"rules": [rule]}}
        saved = client.post(f"{API}/memory/retention/plan", json={}).json()
        assert saved["count"] == 1
        result = client.post(f"{API}/memory/retention/apply").json()
        assert result["archived"] == 1
        entry = client.get(f"{ENTRIES}/{a['id']}").json()
        assert entry["archived"] is True
        assert (entry["updated_by"]["kind"], entry["updated_by"]["label"]) == (
            "system",
            "temp-archive",
        )
        assert client.get(f"{ENTRIES}/{pinned['id']}").json()["archived"] is False


def test_export_import_roundtrip_and_archive_errors(
    tmp_path: Path,
    make_assembly: MakeAssembly,
    client_of: ClientOf,
) -> None:
    first = SqliteDatabase.open(tmp_path / "a.sqlite3")
    with client_of(make_assembly(database=first)) as client:
        _create(client, "결정/하나", "첫째", tags=["t"])
        _create(client, "결정/둘", "둘째")
        exported = client.get(f"{API}/memory/export")
        assert exported.status_code == 200
        assert exported.headers["content-type"] == "application/zip"
        data = exported.content
    first.close()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert len(archive.namelist()) == 2

    second = SqliteDatabase.open(tmp_path / "b.sqlite3")
    options = {"max_import_archive_bytes": len(data) + 10}
    with client_of(make_assembly(database=second, options=options)) as client:
        preview = client.post(f"{API}/memory/import", params={"dry_run": True}, content=data).json()
        assert preview["dry_run"] is True
        assert preview["created"] == 2
        assert client.get(ENTRIES).json()["items"] == []
        done = client.post(f"{API}/memory/import", content=data).json()
        assert done["created"] == 2
        keys = sorted(i["key"] for i in client.get(ENTRIES).json()["items"])
        assert keys == ["결정/둘", "결정/하나"]
        again = client.post(f"{API}/memory/import", params={"policy": "skip"}, content=data).json()
        assert again["skipped"] == 2

        not_zip = client.post(f"{API}/memory/import", content=b"plain text")
        assert not_zip.status_code == 422
        assert not_zip.json()["error"]["code"] == ErrorCodes.VALIDATION_FAILED
        too_big = client.post(f"{API}/memory/import", content=data + b"x" * 64)
        assert too_big.status_code == 422
        assert too_big.json()["error"]["code"] == ErrorCodes.MEMORY_TOO_LARGE
        policy = client.post(f"{API}/memory/import", params={"policy": "merge"}, content=data)
        assert policy.status_code == 422

        unsafe = io.BytesIO()
        with zipfile.ZipFile(unsafe, "w") as archive:
            archive.writestr("../notes/p1/evil.md", "x")
        rejected = client.post(f"{API}/memory/import", content=unsafe.getvalue()).json()
        assert rejected["created"] == 0
        assert rejected["errors"][0]["code"] == "memory.import_unsafe_path"
    second.close()


def test_no_database_uses_memory_and_warns(
    make_assembly: MakeAssembly,
    client_of: ClientOf,
    warning_codes: WarningCodes,
) -> None:
    assembly = make_assembly()
    with client_of(assembly) as client:
        _create(client, "a")
        assert len(client.get(ENTRIES).json()["items"]) == 1
    assert KnownIssueCodes.MEMORY_STORAGE_MEMORY in warning_codes(assembly)


def test_responses_have_no_secret_even_in_versions(
    database: SqliteDatabase,
    make_assembly: MakeAssembly,
    client_of: ClientOf,
) -> None:
    """가림(redact) 방식에서 버전·목록·내보내기 어디에도 비밀 원문이 없다."""
    settings = {"memory": {"secrets": "redact"}}
    with client_of(make_assembly(database=database, settings=settings)) as client:
        created = _create(client, "s", f"{SECRET}")
        texts = [
            client.get(ENTRIES).text,
            client.get(f"{ENTRIES}/{created['id']}/versions").text,
            client.get(f"{ENTRIES}/{created['id']}/versions/1").text,
            client.get(f"{API}/memory/export").content.decode("latin-1"),
        ]
    assert all(SECRET not in text for text in texts)
    assert json.dumps(texts)  # 직렬화 가능
