"""6R.19 잔여: ``RunRepository.page``의 ``since``(created_at 하한)·``query``(부분 일치 검색).

- ``query``는 run id·graph_id·입력 최상위 문자열 값만 본다(키·숫자·중첩 값은 아님).
- 대소문자는 ASCII만 무시하고, ``%``·``_``·``\\``는 글자 그대로 찾는다.
- 커서로 이어 붙여도 같은 조건이 유지되고 행이 겹치거나 빠지지 않는다.
- SQLite·인메모리 결과가 같다.
"""

from typing import Any

import pytest

from agent_console_contracts import Run
from agent_console_store.run_page import fold_query, like_contains


def mk(id: str, at: float, **kw: Any) -> Run:
    fields: dict[str, Any] = {
        "id": id, "graph_id": "g", "graph_version": "h", "status": "completed",
        "input": {}, "origin": "api", "created_at": at,
    }  # fmt: skip
    fields.update(kw)
    return Run(**fields)


def walk(runs: Any, limit: int, **kw: Any) -> list[str]:
    out: list[str] = []
    cursor: str | None = None
    while True:
        items, cursor = runs.page(limit=limit, cursor=cursor, **kw)
        out += [r.id for r in items]
        if cursor is None:
            return out


def _seed(storage: Any) -> None:
    runs = storage.runs
    runs.save(mk("alpha-1", 1.0, input={"text": "Fix the LOGIN bug"}))
    runs.save(mk("beta-2", 2.0, graph_id="Team-Pay", input={"text": "결제 화면 수정"}))
    runs.save(mk("gamma-3", 3.0, input={"text": "100% done_now", "n": 42}))
    runs.save(mk("delta-4", 4.0, input={"login": 7, "nested": {"text": "login"}}))
    runs.save(mk("eps-5", 5.0, input={"a": "", "b": "back\\slash"}))
    runs.save(mk("kid-6", 6.0, parent_run_id="alpha-1", root_run_id="alpha-1",
                 input={"text": "login child"}))  # fmt: skip


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("login", ["kid-6", "alpha-1"]),  # 입력 문자열, 대소문자 무시. 키·중첩 값은 아님(delta-4)
        ("  LOGIN  ", ["kid-6", "alpha-1"]),  # 앞뒤 공백
        ("BETA", ["beta-2"]),  # run id
        ("team-pay", ["beta-2"]),  # graph_id
        ("결제", ["beta-2"]),  # 한글
        ("100%", ["gamma-3"]),  # % 글자 그대로
        ("0%", ["gamma-3"]),
        ("%", ["gamma-3"]),
        ("e_n", ["gamma-3"]),  # _ 글자 그대로(beta-2의 "e-2"·"eps-5"와 섞이지 않음)
        ("_", ["gamma-3"]),
        ("\\", ["eps-5"]),  # 이스케이프 문자 자체
        ("42", []),  # 숫자 값은 보지 않는다
        ("nothing", []),
        ("", ["kid-6", "eps-5", "delta-4", "gamma-3", "beta-2", "alpha-1"]),  # 빈 검색어 = 전체
        ("   ", ["kid-6", "eps-5", "delta-4", "gamma-3", "beta-2", "alpha-1"]),
    ],
)
def test_query_matches_id_graph_and_input_strings(
    storage: Any, query: str, expected: list[str]
) -> None:
    _seed(storage)
    assert walk(storage.runs, 1, query=query) == expected
    assert walk(storage.runs, 50, query=query) == expected


def test_query_combines_with_other_filters_and_cursor(storage: Any) -> None:
    _seed(storage)
    runs = storage.runs
    assert walk(runs, 1, query="login", root_only=True) == ["alpha-1"]
    assert walk(runs, 1, query="login", root_run_id="alpha-1") == ["kid-6"]
    assert walk(runs, 1, query="a", since=3.0) == ["eps-5", "delta-4", "gamma-3"]


def test_since_is_inclusive_lower_bound(storage: Any) -> None:
    _seed(storage)
    runs = storage.runs
    assert walk(runs, 2, since=4.0) == ["kid-6", "eps-5", "delta-4"]
    assert walk(runs, 2, since=4.5) == ["kid-6", "eps-5"]
    assert walk(runs, 2, since=99.0) == []
    assert walk(runs, 2, since=0.0) == walk(runs, 2)


def test_cursor_walk_with_query_has_no_gaps(storage: Any) -> None:
    runs = storage.runs
    for i in range(30):
        runs.save(mk(f"r{i:02d}", float(i), input={"text": "hit" if i % 3 == 0 else "miss"}))
    expected = [f"r{i:02d}" for i in range(29, -1, -1) if i % 3 == 0 and i >= 6]
    for size in (1, 2, 3, 7):
        assert walk(runs, size, query="HIT", since=6.0) == expected


def test_helpers() -> None:
    assert fold_query(None) is None
    assert fold_query(" AbC ") == "abc"
    assert like_contains("a%b_c\\") == "%a\\%b\\_c\\\\%"
