"""5.7R.46 통합: 서버 자동 정리가 등록 프로젝트 메모리 저장소에도 돈다(실제 ``mod-projects``·
``link-projects-memory``·``mod-memory`` 조립, design ``[pl 결정 11/20, 5.7R.46·5.7R.47]``).

- 대상 = 사용자 설정 ``memory.retention.auto``(생략 = 공용·프로젝트 모두), 프로젝트 =
  ``memory.sqlite3``가 이미 있는 켜진 등록만. 자동 정리는 파일을 만들지 않는다.
- ``link-projects-memory``를 끄면 공용만(오류 없음).

범위 종류·정리 규칙은 이 테스트 안에서 만든 사용자 설정 데이터다.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_server.testing import API, make_settings, register_project, server

INTERVAL = 0.05
ENTRIES = f"{API}/memory/entries"
KINDS = {"notes": {"label": "노트", "id": ""}}
RULE = {
    "id": "temp-cleanup",
    "when": {"all": [{"path": "/tags", "op": "contains", "value": "임시"}]},
    "action": "delete",
}


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[Callable[..., TestClient]]:
    stack: list[Any] = []

    def open_server(*, disabled: list[str] | None = None) -> TestClient:
        extra: dict[str, Any] = {"modules": {"disabled": disabled}} if disabled else {}
        options: dict[str, dict[str, Any]] = {
            "mod-memory": {"retention_interval_seconds": INTERVAL},
            "link-projects-runs": {"require_project": False},
        }
        ctx = server(make_settings(tmp_path / "app", options=options, **extra))
        stack.append(ctx)
        return ctx.__enter__()

    yield open_server
    while stack:
        stack.pop().__exit__(None, None, None)


def _set_memory(client: TestClient, section: dict[str, Any]) -> None:
    body: dict[str, Any] = client.get(f"{API}/settings").json()
    body["memory"] = section
    res = client.put(f"{API}/settings", json=body)
    assert res.status_code == 200, res.text


def _temp(client: TestClient, project: str | None = None) -> str:
    params = {"project": project} if project else {}
    body = {"scope": {"kind": "notes", "id": ""}, "key": "t", "content": "x", "tags": ["임시"]}
    res = client.post(ENTRIES, params=params, json=body)
    assert res.status_code == 201, res.text
    entry_id: str = res.json()["id"]
    return entry_id


def _gone(client: TestClient, entry_id: str, project: str | None = None) -> bool:
    params = {"project": project} if project else {}
    return client.get(f"{ENTRIES}/{entry_id}", params=params).status_code == 404


def _wait_gone(client: TestClient, entry_id: str, project: str | None = None) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if _gone(client, entry_id, project):
            return
        time.sleep(INTERVAL)
    pytest.fail(f"자동 정리가 돌지 않았다: {project or '공용'}")


def _db(folder: Path) -> Path:
    return folder / ".agent-console" / "memory.sqlite3"


def _deleted_in_file(path: Path) -> list[bool]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT deleted_at FROM memory_entries").fetchall()
    return [row[0] is not None for row in rows]


def test_auto_retention_cleans_registered_projects_with_memory(
    make_client: Callable[..., TestClient], tmp_path: Path
) -> None:
    client = make_client()
    folders = {name: tmp_path / name for name in ("p1", "p2", "p3", "p4")}
    for name, folder in folders.items():
        folder.mkdir()
        register_project(client, name, folder)
    _set_memory(client, {"scope_kinds": KINDS})
    library = _temp(client)
    p1 = _temp(client, "p1")
    _temp(client, "p3")
    _temp(client, "p4")
    assert not _db(folders["p2"]).exists()
    assert client.delete(f"{API}/projects/p3").status_code == 204  # 보관 = 켜지지 않은 등록
    _set_memory(
        client,
        {
            "scope_kinds": KINDS,
            "retention": {"rules": [RULE], "auto": {"exclude_projects": ["p4"]}},
        },
    )
    _wait_gone(client, library)
    _wait_gone(client, p1, "p1")
    time.sleep(INTERVAL * 4)  # 몇 주기 더
    assert not _db(folders["p2"]).exists()  # 파일이 없던 프로젝트에 만들지 않는다
    assert _deleted_in_file(_db(folders["p3"])) == [False]  # 보관된 등록은 대상이 아니다
    assert _deleted_in_file(_db(folders["p4"])) == [False]  # 뺀 프로젝트
    version = client.get(f"{ENTRIES}/{p1}/versions", params={"project": "p1"}).json()[-1]
    assert version["author"]["kind"] == "system"
    assert version["author"]["label"] == "temp-cleanup"


def test_link_off_cleans_library_only(
    make_client: Callable[..., TestClient], tmp_path: Path
) -> None:
    client = make_client(disabled=["link-projects-memory"])
    folder = tmp_path / "p1"
    folder.mkdir()
    register_project(client, "p1", folder)
    _set_memory(client, {"scope_kinds": KINDS})
    library = _temp(client)
    _set_memory(client, {"scope_kinds": KINDS, "retention": {"rules": [RULE]}})
    _wait_gone(client, library)
    assert not _db(folder).exists()
    assert client.get(f"{API}/health").status_code == 200


def test_no_memory_connection_survives_server_stop(tmp_path: Path) -> None:
    """자동 정리가 도는 서버를 끈 뒤 프로젝트 메모리 DB를 연 파일 설명자가 남지 않고, 늦게 온
    열기(끝나지 않은 정리 스레드 흉내)는 파일을 열지 않는다(리눅스 ``/proc``)."""
    proc = Path("/proc/self/fd")
    if not proc.is_dir():
        pytest.skip("/proc 없음")
    from agent_console_link_projects_memory import MEMORY_SPACES, MemoryDbUnavailable

    folder = tmp_path / "p1"
    folder.mkdir()
    options: dict[str, dict[str, Any]] = {
        "mod-memory": {"retention_interval_seconds": INTERVAL},
        "link-projects-runs": {"require_project": False},
    }
    with server(make_settings(tmp_path / "app", options=options)) as client:
        register_project(client, "p1", folder)
        _set_memory(client, {"scope_kinds": KINDS})
        entry = _temp(client, "p1")
        _set_memory(client, {"scope_kinds": KINDS, "retention": {"rules": [RULE]}})
        _wait_gone(client, entry, "p1")
        pool = client.app.state.assembly.port(MEMORY_SPACES)  # type: ignore[attr-defined]
    with pytest.raises(MemoryDbUnavailable):
        pool.open("p1")
    assert pool.existing() == []
    db = _db(folder)
    names = {str(db), f"{db}-wal", f"{db}-shm"}
    held = []
    for fd in proc.iterdir():
        try:
            if str(fd.readlink()) in names:
                held.append(fd.name)
        except OSError:
            continue
    assert held == []
