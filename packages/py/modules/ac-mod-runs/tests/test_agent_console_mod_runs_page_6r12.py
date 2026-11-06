"""6R.12: ``GET /runs/page``(커서·라벨·프로젝트·Q14 출처 잇기), ``POST /runs`` 라벨, ``node=``.

- 페이지를 끝까지 모으면 중복·누락이 없다(같은 시각 경계 포함).
- 기록 공간이 있는 조립: 폴더 기록(``source=project``)을 끝까지 → 앱 DB 옛 기록(``source=app``),
  한 페이지는 한 출처. 옛 기록이 없으면 폴더 끝에서 ``next_cursor``가 null.
- 이벤트 ``node`` 서버 거르기 = 옛 클라이언트 거르기(``node_path``에 그 노드가 있음).
"""

from __future__ import annotations

import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_console_contracts import Run, RunEvent
from agent_console_mod_runs import SpaceRecorder, space_records
from agent_console_mod_runs.errors import ERROR_MAP, RunQueryError
from agent_console_mod_runs.routes import build_router, parse_label_filters
from agent_console_store import InMemoryStorage, InvalidCursor, SqliteStorage

from .test_agent_console_mod_runs_records_33y2 import (  # type: ignore[import-not-found]
    API,
    Spaces,
    _client,
)


def mk(id: str, at: float, **kw: Any) -> Run:
    fields: dict[str, Any] = {
        "id": id, "graph_id": "g", "graph_version": "h", "status": "completed",
        "input": {}, "origin": "api", "created_at": at,
    }  # fmt: skip
    fields.update(kw)
    return Run(**fields)


@pytest.fixture
def spaces(tmp_path: Path) -> Iterator[Spaces]:
    found = Spaces(tmp_path / "folders")
    yield found
    found.close_all()


def _app(recorder: SpaceRecorder) -> TestClient:
    """라우터만(호스트 조립 없이): 서비스 자리에 기록 읽기만 가진 가짜."""

    def current_run(run_id: str, project: str | None = None) -> Run | None:
        if project is not None:
            return recorder.for_project(project).get(run_id)
        return recorder.runs.get(run_id)

    fake = types.SimpleNamespace(
        records=recorder,
        reader=lambda project=None: recorder.for_project(project),
        current_run=current_run,
        runtime=types.SimpleNamespace(get=lambda _id: None),
    )
    app = FastAPI()
    router = build_router(
        lambda: fake,  # type: ignore[arg-type, return-value]
        lambda: None,  # type: ignore[arg-type, return-value]
        runs=lambda: recorder.runs,
        events=lambda: recorder.events,
    )
    app.include_router(router, prefix=API)
    return TestClient(app)


def _collect(client: TestClient, query: str) -> tuple[list[str], list[str], int]:
    """커서를 끝까지 따라가 (id 목록, 페이지 출처 목록, 페이지 수)."""
    ids: list[str] = []
    sources: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        sep = "&" if query else ""
        url = f"{API}/runs/page?{query}" + (f"{sep}cursor={cursor}" if cursor else "")
        body = client.get(url).json()
        pages += 1
        ids += [r["id"] for r in body["items"]]
        sources.append(body["source"])
        cursor = body["next_cursor"]
        if cursor is None:
            return ids, sources, pages
        assert pages < 1000


# ---- 질의 값 -----------------------------------------------------------------


def test_parse_label_filters_and_errors() -> None:
    assert parse_label_filters(None) == {}
    assert parse_label_filters(["a=1", "b=", "a=1"]) == {"a": "1", "b": ""}
    for bad in (["noeq"], ["=v"], ["a=1", "a=2"]):
        with pytest.raises(RunQueryError):
            parse_label_filters(bad)
    assert ERROR_MAP[InvalidCursor] == "bad_request"
    assert ERROR_MAP[RunQueryError] == "bad_request"


# ---- 호스트 하나(기능 단독) -----------------------------------------------------


def test_host_pages_have_no_duplicates_or_gaps_and_filters() -> None:
    host = InMemoryStorage()
    recorder = SpaceRecorder(host)
    expected: list[Run] = []
    for i in range(37):
        run = mk(
            f"r{i:02d}",
            float(i // 3),  # 같은 시각 3개씩 - 경계에서 id로 나눈다
            project_id="pa" if i % 2 else None,
            labels={"sdd.spec": "s1" if i % 3 else "s2"},
        )
        host.runs.save(run)
        expected.append(run)
    host.runs.save(mk("child", 5.0, root_run_id="r01", parent_run_id="r01"))
    client = _app(recorder)
    ids, sources, pages = _collect(client, "limit=5")
    order = sorted([*expected, mk("child", 5.0)], key=lambda r: (r.created_at, r.id), reverse=True)
    assert ids == [r.id for r in order]
    assert pages == 8
    assert set(sources) == {"project"}  # 공간 없는 조립은 요청한 출처 그대로, 잇지 않는다
    roots, _, _ = _collect(client, "limit=4&root_only=true")
    assert "child" not in roots
    assert len(roots) == 37
    in_pa, _, _ = _collect(client, "limit=4&project=pa")
    assert in_pa == [r.id for r in order if r.project_id == "pa"]
    labelled, _, _ = _collect(client, "limit=3&label=sdd.spec=s2")
    assert labelled == [r.id for r in order if r.labels.get("sdd.spec") == "s2"]
    both, _, _ = _collect(client, "label=sdd.spec=s2&label=sdd.spec=s2&project=pa")
    assert both == [r.id for r in order if r.labels.get("sdd.spec") == "s2" and r.project_id]
    none, _, _ = _collect(client, "label=sdd.spec=s1&label=other=x")
    assert none == []


# ---- 기록 공간 + 앱 DB 옛 기록(Q14) -------------------------------------------


def _spaced(spaces: Spaces) -> tuple[SpaceRecorder, InMemoryStorage, SqliteStorage]:
    host = InMemoryStorage()
    recorder = SpaceRecorder(host, space_records(lambda: spaces, prefix="project:"))
    folder = SqliteStorage(spaces.open("project:pa").writable_engine())
    return recorder, host, folder


def test_project_then_app_without_mixing(spaces: Spaces) -> None:
    recorder, host, folder = _spaced(spaces)
    for i in range(11):  # 폴더 기록: 시각 100~
        folder.runs.save(mk(f"f{i:02d}", 100.0 + i, project_id="pa"))
    for i in range(6):  # 앱 DB 옛 기록: 폴더보다 *새* 시각이어도 폴더 뒤에 온다
        host.runs.save(mk(f"a{i:02d}", 500.0 + i, project_id="pa"))
    host.runs.save(mk("other", 900.0, project_id="pb"))
    host.runs.save(mk("plain", 901.0))
    client = _app(recorder)
    ids, sources, _ = _collect(client, "project=pa&limit=4")
    folder_ids = [f"f{i:02d}" for i in reversed(range(11))]
    app_ids = [f"a{i:02d}" for i in reversed(range(6))]
    assert ids == folder_ids + app_ids
    assert sources == ["project"] * 3 + ["app"] * 2  # 4+4+3 / 4+2 - 한 페이지에 한 출처
    assert len(ids) == len(set(ids))
    # 폴더 마지막 페이지의 next_cursor = 앱 기록의 처음
    third = client.get(f"{API}/runs/page?project=pa&limit=11").json()
    assert [r["id"] for r in third["items"]] == folder_ids
    assert third["source"] == "project"
    assert third["next_cursor"] == "app."
    first_app = client.get(f"{API}/runs/page?project=pa&limit=11&cursor=app.").json()
    assert first_app["source"] == "app"
    assert [r["id"] for r in first_app["items"]] == app_ids
    assert first_app["next_cursor"] is None
    # source=app으로 옛 기록만 바로
    direct, direct_sources, _ = _collect(client, "project=pa&source=app&limit=5")
    assert direct == app_ids
    assert set(direct_sources) == {"app"}


def test_project_end_without_app_records_ends(spaces: Spaces) -> None:
    recorder, host, folder = _spaced(spaces)
    folder.runs.save(mk("f1", 1.0, project_id="pa"))
    host.runs.save(mk("x", 2.0, project_id="pb"))
    client = _app(recorder)
    body = client.get(f"{API}/runs/page?project=pa").json()
    assert ([r["id"] for r in body["items"]], body["next_cursor"]) == (["f1"], None)
    # 거르기도 앱 쪽 존재 확인에 적용된다(라벨이 맞는 옛 기록이 없으면 잇지 않는다)
    host.runs.save(mk("a1", 3.0, project_id="pa", labels={"k": "v"}))
    assert client.get(f"{API}/runs/page?project=pa&label=k=w").json()["next_cursor"] is None
    labelled = client.get(f"{API}/runs/page?project=pa&label=k=v").json()
    assert (labelled["items"], labelled["next_cursor"]) == ([], "app.")


def test_folder_without_records_file_goes_straight_to_app(spaces: Spaces, tmp_path: Path) -> None:
    host = InMemoryStorage()
    recorder = SpaceRecorder(host, space_records(lambda: spaces, prefix="project:"))
    host.runs.save(mk("a1", 1.0, project_id="fresh"))
    client = _app(recorder)
    body = client.get(f"{API}/runs/page?project=fresh").json()
    assert (body["items"], body["source"], body["next_cursor"]) == ([], "project", "app.")
    assert not (tmp_path / "folders" / "fresh" / "records.sqlite3").exists()


# ---- 이벤트 node= -------------------------------------------------------------


def _event(seq: int, path: list[str], type: str = "log.info") -> RunEvent:
    return RunEvent.model_validate(
        {
            "event_id": f"e{seq}", "run_id": "r1", "seq": seq, "ts": float(seq),
            "type": type, "node_path": path, "payload": {},
        }
    )  # fmt: skip


@pytest.mark.parametrize("kind", ["memory", "sqlite"])
def test_event_node_filter_equals_client_filter(kind: str, tmp_path: Path) -> None:
    if kind == "memory":
        host: Any = InMemoryStorage()
    else:
        from agent_console_mod_runs.storage import BRANCH
        from agent_console_store import SqliteDatabase

        db = SqliteDatabase.open(tmp_path / "e.sqlite3")
        db.upgrade([BRANCH])
        host = SqliteStorage(db.engine)
    host.runs.save(mk("r1", 1.0))
    paths = [[], ["A"], ["B"], ["A", "sub"], ["B", "A"], ["sub"], ["A"], ["AA"]]
    host.events.append_many([_event(i + 1, p) for i, p in enumerate(paths)])
    client = _app(SpaceRecorder(host))
    every = client.get(f"{API}/runs/r1/events").json()
    for node in ("A", "B", "sub", "AA", "none"):
        server = client.get(f"{API}/runs/r1/events?node={node}").json()
        assert server == [e for e in every if node in e["node_path"]], node
    combined = client.get(f"{API}/runs/r1/events?node=A&since_seq=2&type_prefix=log.").json()
    assert [e["seq"] for e in combined] == [4, 5, 7]


# ---- 조립 서버: POST /runs 라벨 → 기록 DB, 페이지·400 -------------------------


def test_post_labels_land_on_root_and_query_through_full_host(
    tmp_path: Path, spaces: Spaces
) -> None:
    with _client(tmp_path, spaces) as client:
        labels = {"sdd.spec": "pay", "sdd.task": "2.1"}
        body = {"graph_id": "g", "input": {}, "project_id": "pa", "labels": labels}
        created = client.post(f"{API}/runs", json=body)
        assert created.status_code == 202, created.text
        assert created.json()["labels"] == labels
        other = client.post(f"{API}/runs", json={**body, "labels": {"sdd.spec": "pay"}})
        assert other.status_code == 202
        too_many = {f"k{i}": "v" for i in range(17)}
        refused = client.post(f"{API}/runs", json={**body, "labels": too_many})
        assert refused.status_code == 422
        page = client.get(
            f"{API}/runs/page?project=pa&root_only=true&label=sdd.spec=pay&label=sdd.task=2.1"
        )
        assert page.status_code == 200, page.text
        assert [r["id"] for r in page.json()["items"]] == [created.json()["id"]]
        assert page.json()["source"] == "project"
        bad_cursor = client.get(f"{API}/runs/page?cursor=zzz")
        assert bad_cursor.status_code == 400
        assert bad_cursor.json()["error"]["code"] == "bad_request"
        bad_label = client.get(f"{API}/runs/page?label=nolabel")
        assert bad_label.status_code == 400
        spec = client.app.openapi()["paths"]
        assert spec[f"{API}/runs"]["get"].get("deprecated") is True
        assert "deprecated" not in spec[f"{API}/runs/page"]["get"]
    stored = SqliteStorage(spaces.open("project:pa").read_engine()).runs
    root = stored.get(created.json()["id"])
    assert root is not None
    assert root.labels == labels
    children = stored.descendants(root.id)
    assert children
    assert all(c.labels == {} for c in children)  # 자식 Run은 라벨을 물려받지 않는다
