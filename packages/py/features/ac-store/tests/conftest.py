"""두 구현(SQLite/파일, 인메모리)에 같은 스위트를 돌리기 위한 픽스처."""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from agent_console_store import (
    DefinitionStore,
    FileDefinitionStore,
    InMemoryDefinitionStore,
    InMemoryStorage,
    SqliteStorage,
    open_sqlite,
)


class Clock:
    """테스트용 단조 증가 시계."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture(params=["sqlite", "memory"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Any]:
    """런타임 기록 묶음(runs, events, versions, ...)."""
    impl: SqliteStorage | InMemoryStorage
    impl = (
        open_sqlite(tmp_path / "db" / "console.sqlite3")
        if request.param == "sqlite"
        else InMemoryStorage()
    )
    yield impl
    impl.close()


@pytest.fixture(params=["file+sqlite", "file", "memory"])
def definitions(
    request: pytest.FixtureRequest, tmp_path: Path, clock: Clock
) -> Iterator[DefinitionStore]:
    if request.param == "memory":
        yield InMemoryDefinitionStore(clock=clock)
    elif request.param == "file":
        yield FileDefinitionStore(tmp_path / "ws", clock=clock)
    else:
        db = open_sqlite(tmp_path / "console.sqlite3")
        yield FileDefinitionStore(tmp_path / "ws", versions=db.versions, clock=clock)
        db.close()


@pytest.fixture
def make_graph() -> Callable[..., dict[str, Any]]:
    """그래프 문서 팩토리: `make_graph(id="g1", nodes=2, **extra)`."""
    return _make_graph


def _make_graph(id: str = "g1", nodes: int = 2, **extra: Any) -> dict[str, Any]:
    return {
        "id": id,
        "name": f"그래프 {id}",
        "nodes": [{"id": f"n{i}", "type": "custom.anything"} for i in range(nodes)],
        "edges": [
            {
                "id": "e1",
                "source": {"node": "n0", "port": "out"},
                "target": {"node": "n1", "port": "in"},
                "kind": "data",
            }
        ]
        if nodes >= 2
        else [],
        **extra,
    }
