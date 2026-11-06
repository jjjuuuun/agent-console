"""6R.19 서버 후속: ``RunRepository.page``의 ``conversation_id``·``agent``·``root_run_id`` 거르기와
행마다 ``has_children``(직접 자식 유무). SQLite(계보 없는 legacy 표)·인메모리 둘 다.

- 거르기는 ``list``와 같은 결과다(같은 조건, 같은 정렬).
- ``has_children``은 페이지 행마다 채워지고 ``list``·``get``은 채우지 않는다(None).
"""

from typing import Any

from agent_console_contracts import Run, RunEvent


def mk(id: str, at: float, **kw: Any) -> Run:
    fields: dict[str, Any] = {
        "id": id, "graph_id": "g", "graph_version": "h", "status": "completed",
        "input": {}, "origin": "api", "created_at": at,
    }  # fmt: skip
    fields.update(kw)
    return Run(**fields)


def ev(run_id: str, seq: int, actor: str | None) -> RunEvent:
    return RunEvent(
        event_id=f"{run_id}-{seq}",
        run_id=run_id,
        seq=seq,
        ts=float(seq),
        type="node.started",
        node_path=["n1"],
        attempt=1,
        actor=actor,
        payload={},
    )


def _seed(storage: Any) -> None:
    runs = storage.runs
    runs.save(mk("root1", 1.0, conversation_id="c1"))
    runs.save(mk("kid1", 2.0, parent_run_id="root1", root_run_id="root1"))
    runs.save(mk("grand1", 3.0, parent_run_id="kid1", root_run_id="root1"))
    runs.save(mk("root2", 4.0, conversation_id="c2"))
    runs.save(mk("root3", 5.0, conversation_id="c1"))
    storage.events.append(ev("root1", 1, "pl"))
    storage.events.append(ev("kid1", 1, "dev"))
    storage.events.append(ev("root3", 1, "pl"))
    storage.events.append(ev("root2", 1, None))


def walk(runs: Any, limit: int, **kw: Any) -> list[Run]:
    out: list[Run] = []
    cursor: str | None = None
    while True:
        items, cursor = runs.page(limit=limit, cursor=cursor, **kw)
        out += items
        if cursor is None:
            return out


def test_page_filters_match_list(storage: Any) -> None:
    _seed(storage)
    runs = storage.runs
    cases: list[dict[str, Any]] = [
        {"conversation_id": "c1"},
        {"agent": "pl"},
        {"agent": "dev"},
        {"agent": "ghost"},
        {"root_run_id": "root1"},
        {"root_run_id": "root1", "agent": "dev"},
        {"conversation_id": "c1", "root_only": True, "agent": "pl"},
        {"root_run_id": "root2"},
    ]
    for kw in cases:
        paged = [r.id for r in walk(runs, 1, **kw)]
        assert paged == [r.id for r in runs.list(**kw)], kw
    assert [r.id for r in walk(runs, 2, root_run_id="root1")] == ["grand1", "kid1"]
    assert [r.id for r in walk(runs, 2, conversation_id="c1")] == ["root3", "root1"]
    assert [r.id for r in walk(runs, 2, agent="pl")] == ["root3", "root1"]


def test_page_fills_has_children_and_list_does_not(storage: Any) -> None:
    _seed(storage)
    runs = storage.runs
    flags = {r.id: r.has_children for r in walk(runs, 2)}
    assert flags == {
        "root3": False,
        "root2": False,
        "grand1": False,
        "kid1": True,  # 손자의 부모
        "root1": True,
    }
    roots = {r.id: r.has_children for r in walk(runs, 10, root_only=True)}
    assert roots == {"root3": False, "root2": False, "root1": True}
    assert all(r.has_children is None for r in runs.list())
    got = runs.get("root1")
    assert got is not None
    assert got.has_children is None


def test_empty_page_has_no_rows(storage: Any) -> None:
    items, cursor = storage.runs.page(root_run_id="nothing")
    assert (items, cursor) == ([], None)
