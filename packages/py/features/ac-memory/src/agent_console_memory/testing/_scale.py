"""규모 측정 도구(design §5.7R.10): 큰 SQLite 메모리 저장소를 만들고, 질의의 작업량과 시간을 잰다.

- ``build_scale_store``: 항목 수·범위 수·평균 크기를 정해 결정적인 데이터(같은 인자 = 같은 데이터)를
  넣는다. 한 범위가 가장 크고(``heavy_scope``), 모든 항목에 고유 낱말, 일부에 흔한 낱말을 둔다.
- ``WorkCounter``: SQLite 가상 기계 명령 수(작업량)를 센다. 시간과 달리 장비·부하에 흔들리지 않는다.
- ``perf_strict``·``percentile``·``time_calls``: ``AGENT_CONSOLE_PERF=strict``일 때만
  벽시계를 단언한다.
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import event

from agent_console_contracts.memory import MemoryAuthor, MemoryEntry, MemoryScopeRef
from agent_console_memory._policy import MemoryPolicy, content_digest
from agent_console_memory.sqlite import SqliteMemoryStore, open_sqlite_memory_store

__all__ = [
    "ScaleLayout",
    "WorkCounter",
    "build_scale_store",
    "percentile",
    "perf_strict",
    "time_calls",
]

_BASE_TIME = 1_700_000_000.0
_ALPHABET = "abcdefghijklmnopqrstuvwxyz"
_STEP = 5  # 진행 처리기를 부르는 가상 기계 명령 간격(문장마다 세므로 작게)


def perf_strict() -> bool:
    """``AGENT_CONSOLE_PERF=strict``이면 참(벽시계 단언을 켠다)."""
    return os.environ.get("AGENT_CONSOLE_PERF", "") == "strict"


@dataclass(frozen=True, slots=True)
class ScaleLayout:
    """``build_scale_store``가 만든 데이터의 모양.

    Attributes:
        entries: 항목 수.
        scopes: 범위 목록(가장 큰 것이 맨 앞).
        heavy_scope: 항목이 가장 많은 범위.
        heavy_count: 그 범위의 항목 수.
        keys: (범위 종류, 범위 id) → 키 목록(일부만, 읽기·쓰기 표본용).
        common_word: 항목의 약 1/5에 들어 있는 낱말.
        common_tag: 항목의 약 1/10에 붙은 태그.
        unique_word: 항목 ``i``의 고유 낱말을 만드는 함수 이름(``unique_word_of``)을 위한 접두.
        total_bytes: 본문 바이트 합.
    """

    entries: int
    scopes: tuple[MemoryScopeRef, ...]
    heavy_scope: MemoryScopeRef
    heavy_count: int
    keys: dict[tuple[str, str], list[str]]
    common_word: str
    common_tag: str
    unique_prefix: str
    total_bytes: int

    def unique_word_of(self, index: int) -> str:
        """항목 ``index``(0부터)의 고유 낱말. 이 낱말을 찾으면 그 항목 하나뿐이다."""
        return f"{self.unique_prefix}{index:07d}"


class WorkCounter:
    """저장소가 연결을 빌릴 때마다 SQLite 가상 기계 명령 수를 센다(``with``로 구간을 잰다).

    >>> from agent_console_memory import MemoryQuery
    >>> from agent_console_memory.sqlite import open_sqlite_memory_store
    >>> store = open_sqlite_memory_store(":memory:")
    >>> counter = WorkCounter(store)
    >>> with counter.measure():
    ...     _ = store.search(MemoryQuery())
    >>> counter.steps > 0
    True
    """

    def __init__(self, store: SqliteMemoryStore) -> None:
        self.steps = 0
        self._store = store

    @contextmanager
    def measure(self) -> Iterator[None]:
        """구간 안 가상 기계 명령 수를 ``steps``에 담는다(구간 시작 때 0으로 되돌린다)."""
        self.steps = 0
        engine = self._store._engine

        def handler() -> int:
            self.steps += _STEP
            return 0

        @event.listens_for(engine, "checkout")
        def _install(dbapi: Any, _record: object, _proxy: object) -> None:
            dbapi.set_progress_handler(handler, _STEP)

        @event.listens_for(engine, "checkin")
        def _remove(dbapi: Any, _record: object) -> None:
            dbapi.set_progress_handler(None, 0)

        try:
            yield
        finally:
            event.remove(engine, "checkout", _install)
            event.remove(engine, "checkin", _remove)


def percentile(values: Sequence[float], q: float) -> float:
    """``q``(0~1) 분위수(가까운 순위). 빈 목록이면 0."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def time_calls(fn: Callable[[int], object], count: int) -> list[float]:
    """``fn(0..count-1)``을 차례로 부르며 걸린 초를 모은다."""
    out: list[float] = []
    for i in range(count):
        started = time.perf_counter()
        fn(i)
        out.append(time.perf_counter() - started)
    return out


def _word(rng: random.Random) -> str:
    return "".join(rng.choice(_ALPHABET) for _ in range(rng.randint(3, 9)))


def build_scale_store(
    path: str | Path,
    *,
    entries: int = 100_000,
    scopes: int = 200,
    avg_bytes: int = 2048,
    heavy_entries: int = 5_000,
    seed: int = 1,
    policy: MemoryPolicy | None = None,
    use_fts: bool | None = None,
) -> tuple[SqliteMemoryStore, ScaleLayout]:
    """큰 데이터를 가진 SQLite 저장소를 만든다(결정적: 같은 인자 = 같은 내용).

    범위 하나(``heavy_entries``개)가 가장 크고 나머지는 고르게 나눈다. 본문은 낱말 단락 은행에서
    이어 붙이고 항목마다 고유 낱말 하나를 넣는다. 일부 항목에 흔한 낱말·태그를 둔다.

    Args:
        path: DB 파일.
        entries: 항목 수.
        scopes: 범위 수.
        avg_bytes: 본문 평균 크기(바이트).
        heavy_entries: 가장 큰 범위의 항목 수(``entries``보다 클 수 없다).
        seed: 난수 시드.
        policy: 저장소 정책(기본값 그대로).
        use_fts: 검색 방식(None = 가능하면 FTS5).

    Returns:
        (저장소, 데이터 모양).
    """
    rng = random.Random(seed)
    heavy = min(heavy_entries, entries)
    rest = entries - heavy
    others = max(scopes - 1, 1)
    sizes = [heavy] + [rest // others + (1 if i < rest % others else 0) for i in range(others)]
    scope_list = tuple(MemoryScopeRef(kind=f"sk{i % 3}", id=f"s{i:04d}") for i in range(len(sizes)))
    common_word = "deploy"
    common_tag = "tag-common"
    unique_prefix = "uniq"
    vocabulary = [_word(rng) for _ in range(4000)]
    para_len = max(avg_bytes // 4, 40)
    paragraphs: list[str] = []
    for _ in range(400):
        words: list[str] = []
        size = 0
        while size < para_len:
            word = rng.choice(vocabulary)
            words.append(word)
            size += len(word) + 1
        paragraphs.append(" ".join(words))
    authors = [
        MemoryAuthor(kind="agent", agent_id=f"agent-{i % 20}", run_id=f"run-{i}")
        for i in range(500)
    ]
    keys: dict[tuple[str, str], list[str]] = {(s.kind, s.id): [] for s in scope_list}
    store = open_sqlite_memory_store(path, policy=policy, use_fts=use_fts)
    total_bytes = 0

    def generate() -> Iterator[MemoryEntry]:
        nonlocal total_bytes
        index = 0
        for scope, count in zip(scope_list, sizes, strict=True):
            for n in range(count):
                parts = [rng.choice(paragraphs) for _ in range(rng.randint(2, 6))]
                head = f"{unique_prefix}{index:07d}"
                if index % 5 == 0:
                    head += f" {common_word}"
                body = head + "\n" + "\n".join(parts)
                size, digest = content_digest(body)
                total_bytes += size
                at = _BASE_TIME + index
                author = authors[index % len(authors)]
                key = f"area{n % 7}/item-{n:05d}"
                if len(keys[(scope.kind, scope.id)]) < 200:
                    keys[(scope.kind, scope.id)].append(key)
                yield MemoryEntry(
                    id=f"e{index:07d}",
                    scope=scope,
                    key=key,
                    content=body,
                    tags=["tag-a", f"tag-{index % 20}"] + ([common_tag] if index % 10 == 0 else []),
                    version=1,
                    bytes=size,
                    sha256=digest,
                    created_at=at,
                    created_by=author,
                    updated_at=at,
                    updated_by=author,
                )
                index += 1

    store.bulk_insert(generate(), batch=2000)
    store.optimize()
    layout = ScaleLayout(
        entries=entries,
        scopes=scope_list,
        heavy_scope=scope_list[0],
        heavy_count=heavy,
        keys=keys,
        common_word=common_word,
        common_tag=common_tag,
        unique_prefix=unique_prefix,
        total_bytes=total_bytes,
    )
    return store, layout
