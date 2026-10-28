"""메모리 구현과 SQLite 구현의 차등 시험: 같은 무작위 연산열 -> 같은 결과·같은 오류·같은 상태.

시드마다 연산 수백 개를 두 저장소에 똑같이 보낸다. 항목 id·시각을 주입해 결과를 그대로 비교한다.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Callable
from dataclasses import fields, is_dataclass, replace
from typing import Any

import pytest

from agent_console_contracts.memory import MEMORY_ENTRY_SORTS, MemoryScopeRef
from agent_console_memory import (
    InMemoryMemoryStore,
    MemoryLimits,
    MemoryPolicy,
    MemoryQuery,
    MemoryStore,
    MemoryStoreError,
)
from agent_console_memory.sqlite import fts5_trigram_available, open_sqlite_memory_store
from agent_console_memory.testing import FakeClock, agent_author_sample, user_author

SCOPES = [
    MemoryScopeRef(kind="ka", id=""),
    MemoryScopeRef(kind="ka", id="x"),
    MemoryScopeRef(kind="kb", id="x"),
]
KEYS = ["a", "b", "dir/a", "dir/b", "dir/sub/c", "한글/키", "Mixed/Case"]
WORDS = ["alpha", "Beta", "회의록", "ÉCOLE", "x", "ab", "foo bar", 'q"uote', "100%", "a_b", "회의"]
TAGS = ["t1", "t2", "임시", "Tag3", "ab"]
NEEDLES = [
    "alpha",
    "BETA",
    "회의록",
    "회의",
    "écol",
    "x",
    "ab",
    "o ba",
    'q"u',
    "%",
    "_",
    "dir/s",
    "t",
]
SECRET = "sk-ant-api03-" + "A1b2C3d4E5f6G7h8" * 3
PARAMS = [pytest.param(seed, id=f"seed{seed}") for seed in range(24)]


def _content(rng: random.Random) -> str:
    if rng.random() < 0.03:
        return f"token {SECRET}"
    parts = [rng.choice(WORDS) for _ in range(rng.randint(0, 6))]
    text = " ".join(parts)
    return text + ("x" * rng.randint(20, 60) if rng.random() < 0.05 else "")


def _stores(seed: int) -> tuple[MemoryStore, MemoryStore, FakeClock, FakeClock]:
    limits = replace(
        MemoryLimits(),
        max_entry_bytes=64,
        max_entries_per_scope=6,
        max_total_bytes=420,
        max_tags=3,
    )
    policy = MemoryPolicy(limits=limits, max_versions_per_entry=3)
    counters = (itertools.count(1), itertools.count(1))
    clocks = (FakeClock(1000.0), FakeClock(1000.0))
    memory = InMemoryMemoryStore(
        policy=policy, clock=clocks[0], new_id=lambda: f"e{next(counters[0])}"
    )
    sqlite = open_sqlite_memory_store(
        ":memory:", policy=policy, clock=clocks[1], new_id=lambda: f"e{next(counters[1])}"
    )
    return memory, sqlite, clocks[0], clocks[1]


def _norm(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _norm(getattr(value, f.name)) for f in fields(value)}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_norm(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_norm(v) for v in value)
    return value


def _call(fn: Callable[[MemoryStore], Any], store: MemoryStore) -> tuple[str, Any]:
    try:
        return "ok", _norm(fn(store))
    except MemoryStoreError as error:
        extra = {
            k: getattr(error, k)
            for k in ("entry_id", "current_version", "limit", "value", "field", "rules")
            if hasattr(error, k)
        }
        return "err", (type(error).__name__, error.code, extra)


def _query(rng: random.Random) -> MemoryQuery:
    scopes = None if rng.random() < 0.4 else rng.sample(SCOPES, rng.randint(0, 3))
    sort = rng.choice(MEMORY_ENTRY_SORTS)
    return MemoryQuery(
        scopes=scopes,
        text=rng.choice(NEEDLES) if rng.random() < 0.5 else "",
        tags=rng.sample(TAGS, rng.randint(0, 2)) if rng.random() < 0.3 else (),
        author_run=rng.choice(["run-1", "run-2", "none"]) if rng.random() < 0.2 else None,
        author_kind=rng.choice(["user", "agent"]) if rng.random() < 0.2 else None,
        include_archived=rng.random() < 0.3,
        include_deleted=rng.random() < 0.3,
        sort=sort,
        order=rng.choice(["asc", "desc"]),
        limit=rng.choice([1, 2, 3, 50]),
    )


def _random_op(rng: random.Random, known: list[str]) -> Callable[[MemoryStore], Any]:
    def pick_id() -> str:
        return rng.choice(known) if known and rng.random() < 0.9 else "missing"

    author = rng.choice(
        [user_author(), agent_author_sample(run_id="run-1"), agent_author_sample(run_id="run-2")]
    )
    scope = rng.choice(SCOPES)
    key = rng.choice(KEYS)
    kind = rng.choices(
        [
            "write",
            "update",
            "delete",
            "purge",
            "restore",
            "archive",
            "move",
            "mark_read",
            "search",
            "page",
            "scopes",
            "read",
        ],
        weights=[30, 8, 6, 3, 6, 5, 6, 3, 14, 4, 3, 8],
    )[0]
    if_version = rng.choice([None, None, None, 1, 2, 3])
    tags = rng.sample(TAGS, rng.randint(0, 4)) if rng.random() < 0.6 else None
    content = _content(rng)
    if kind == "write":
        mode = rng.choice(["replace", "replace", "append"])
        pinned = rng.choice([None, True, False])
        content_type = rng.choice([None, "text/plain"])
        create_only = rng.random() < 0.1
        return lambda s: s.write(
            scope,
            key,
            content,
            author=author,
            tags=tags,
            pinned=pinned,
            content_type=content_type,
            if_version=if_version,
            mode=mode,  # type: ignore[arg-type]
            create_only=create_only,
        )
    entry_id = pick_id()
    if kind == "update":
        new_content = content if rng.random() < 0.7 else None
        return lambda s: s.update(
            entry_id,
            author=author,
            content=new_content,
            tags=tags,
            if_version=if_version,
        )
    if kind == "delete":
        return lambda s: s.delete(entry_id, author=author, if_version=if_version)
    if kind == "purge":
        return lambda s: s.purge(entry_id)
    if kind == "restore":
        version = rng.choice([None, None, 1, 2, 9])
        return lambda s: s.restore(entry_id, author=author, version=version)
    if kind == "archive":
        flag = rng.random() < 0.7
        return lambda s: s.archive(entry_id, author=author, archived=flag, if_version=if_version)
    if kind == "move":
        to_scope = scope if rng.random() < 0.6 else None
        to_key = rng.choice([None, *KEYS, "../bad", f"k/{SECRET}"])
        return lambda s: s.move(
            entry_id, author=author, to_scope=to_scope, to_key=to_key, if_version=if_version
        )
    if kind == "mark_read":
        return lambda s: s.mark_read(entry_id)
    if kind == "search":
        query = _query(rng)
        return lambda s: s.search(query)
    if kind == "page":
        query = replace(_query(rng), limit=2)

        def pages(s: MemoryStore) -> list[Any]:
            out = []
            cursor = None
            for _ in range(20):
                page = s.search(replace(query, cursor=cursor))
                out.append(page)
                cursor = page.next_cursor
                if cursor is None:
                    break
            return out

        return pages
    if kind == "scopes":
        kind_filter = rng.choice([None, "ka", "kb", "zz"])
        return lambda s: s.list_scopes(kind=kind_filter)

    def read(s: MemoryStore) -> Any:
        return (
            s.get(entry_id),
            s.get(entry_id, include_deleted=True),
            s.find(scope, key),
            s.get_version(entry_id, rng_version),
            _history(s, entry_id),
        )

    rng_version = rng.choice([1, 2, 3, 4])
    return read


def _history(store: MemoryStore, entry_id: str) -> Any:
    try:
        return store.history(entry_id)
    except MemoryStoreError as error:
        return type(error).__name__


@pytest.mark.parametrize("seed", PARAMS)
def test_random_operations_match_memory_store(seed: int) -> None:
    memory, sqlite, clock_a, clock_b = _stores(seed)
    rng = random.Random(seed)
    known: list[str] = []
    for step in range(260):
        if rng.random() < 0.7:
            clock_a.advance(1)
            clock_b.advance(1)
        op = _random_op(rng, known)
        expected = _call(op, memory)
        actual = _call(op, sqlite)
        assert actual == expected, f"seed {seed} step {step}"
        if expected[0] == "ok" and isinstance(expected[1], dict) and "entry" in expected[1]:
            known.append(expected[1]["entry"]["id"])
    # 끝 상태도 같다: 모든 항목(지운 것 포함)과 모든 쪽
    everything = MemoryQuery(include_archived=True, include_deleted=True, limit=500)
    assert _norm(sqlite.search(everything)) == _norm(memory.search(everything))
    assert _norm(sqlite.list_scopes()) == _norm(memory.list_scopes())


@pytest.mark.skipif(not fts5_trigram_available(), reason="FTS5 trigram 없음")
@pytest.mark.parametrize("seed", range(6))
def test_like_fallback_matches_memory_store(seed: int) -> None:
    memory, _sqlite, clock_a, clock_b = _stores(seed)
    counter = itertools.count(1)
    like = open_sqlite_memory_store(
        ":memory:",
        policy=memory.policy,
        clock=clock_b,
        new_id=lambda: f"e{next(counter)}",
        use_fts=False,
    )
    rng = random.Random(1000 + seed)
    known: list[str] = []
    for step in range(200):
        if rng.random() < 0.7:
            clock_a.advance(1)
            clock_b.advance(1)
        op = _random_op(rng, known)
        expected = _call(op, memory)
        assert _call(op, like) == expected, f"seed {seed} step {step}"
        if expected[0] == "ok" and isinstance(expected[1], dict) and "entry" in expected[1]:
            known.append(expected[1]["entry"]["id"])
