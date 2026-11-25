"""`RecordsStores`(5.7R.33y2): 프로젝트 id → 기록 DB 위의 저장소 묶음."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_console_store import (
    RecordsDb,
    RecordsStores,
    RecordsUnavailable,
    SqliteStorage,
    UnknownSpace,
    open_records_db,
)


class Handle:
    """`RecordsHandle` 모양(테스트용): `RecordsDb` + `host_id` + 대기 줄 목록."""

    def __init__(self, db: RecordsDb, host_id: str = "host-a") -> None:
        self.db = db
        self.host_id = host_id
        self.spooled: list[tuple[str, str]] = []

    @property
    def state(self):  # type: ignore[no-untyped-def]
        return self.db.state

    @property
    def engine(self):  # type: ignore[no-untyped-def]
        return self.db.engine

    def read_engine(self):  # type: ignore[no-untyped-def]
        return self.db.read_engine()

    def writable_engine(self):  # type: ignore[no-untyped-def]
        return self.db.writable_engine()

    def spool(self, run_id: str, kind: str, data: object) -> None:
        self.spooled.append((run_id, kind))

    def close(self) -> None:
        self.db.close()


class Spaces:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.handles: dict[str, Handle] = {}
        self.opened: list[str] = []

    def open(self, space: str) -> Handle:
        self.opened.append(space)
        if space == "project:missing":
            raise LookupError(space)
        if space not in self.handles:
            root = self.tmp / space.replace(":", "_")
            self.handles[space] = Handle(
                open_records_db(root / "records.sqlite3", backup_dir=root / "backups")
            )
        return self.handles[space]

    def state(self, space: str):  # type: ignore[no-untyped-def]
        return self.open(space).state

    def close(self, space: str) -> None:
        pass

    def close_all(self) -> None:
        for handle in self.handles.values():
            handle.close()


@pytest.fixture
def spaces(tmp_path: Path):  # type: ignore[no-untyped-def]
    found = Spaces(tmp_path)
    yield found
    found.close_all()


def test_reader_does_not_create_file_writer_does(spaces: Spaces, tmp_path: Path) -> None:
    stores = RecordsStores(lambda: spaces, SqliteStorage)
    assert stores.available
    assert stores.reader("p1") is None
    assert not (tmp_path / "project_p1" / "records.sqlite3").exists()
    writer = stores.writer("p1")
    assert (tmp_path / "project_p1" / "records.sqlite3").exists()
    assert stores.writer("p1") is writer  # 같은 엔진이면 같은 묶음
    reader = stores.reader("p1")
    assert reader is not None
    assert reader.runs.list() == []
    assert spaces.opened[0] == "project:p1"
    assert stores.host_id("p1") == "host-a"


def test_no_port_is_link_disabled_with_project_id() -> None:
    stores: RecordsStores[SqliteStorage] = RecordsStores(lambda: None, SqliteStorage)
    assert not stores.available
    with pytest.raises(RecordsUnavailable) as caught:
        stores.writer("p1")
    assert caught.value.reason == "link_disabled"
    assert caught.value.details() == {"reason": "link_disabled", "project_id": "p1"}


def test_unknown_project_is_unknown_space(spaces: Spaces) -> None:
    stores = RecordsStores(lambda: spaces, SqliteStorage)
    with pytest.raises(UnknownSpace) as caught:
        stores.reader("missing")
    assert caught.value.space == "missing"
    assert caught.value.code == "project.not_found"


def test_unwritable_error_carries_project_id(spaces: Spaces) -> None:
    stores = RecordsStores(lambda: spaces, SqliteStorage, prefix="x:")

    class Readonly(Spaces):
        def open(self, space: str) -> Handle:
            handle = super().open(space)

            def refuse() -> None:
                raise RecordsUnavailable("readonly")

            handle.writable_engine = refuse  # type: ignore[method-assign]
            return handle

    ro = Readonly(spaces.tmp)
    stores = RecordsStores(lambda: ro, SqliteStorage, prefix="x:")
    try:
        with pytest.raises(RecordsUnavailable) as caught:
            stores.ensure_writable("p9")
        assert caught.value.project_id == "p9"
        assert caught.value.details()["reason"] == "readonly"
    finally:
        ro.close_all()


def test_on_open_runs_once_and_retries_until_done(spaces: Spaces) -> None:
    calls: list[str] = []
    results = iter([False, True])

    def hook(project_id: str) -> bool:
        calls.append(project_id)
        return next(results)

    stores = RecordsStores(lambda: spaces, SqliteStorage, on_open=hook)
    stores.reader("p1")
    stores.reader("p1")  # 처음 결과가 거짓이라 다시
    stores.reader("p1")  # 끝남 → 더 부르지 않는다
    assert calls == ["p1", "p1"]


def test_on_open_exception_does_not_break_open(spaces: Spaces) -> None:
    def hook(project_id: str) -> bool:
        raise RuntimeError("boom")

    stores = RecordsStores(lambda: spaces, SqliteStorage, on_open=hook)
    assert stores.reader("p1") is None


def test_other_thread_waits_for_on_open_hook(spaces: Spaces) -> None:
    """훅(재시작 복구)이 도는 동안 같은 공간을 여는 다른 스레드는 끝날 때까지 기다린다.

    회귀(11/20): 시작 직후 로그 수집이 공간을 먼저 열어 복구하는 사이 첫 요청이 기다리지 않고
    복구 전 상태(`running`)를 읽었다.
    """
    import threading

    started = threading.Event()
    release = threading.Event()
    order: list[str] = []

    def hook(project_id: str) -> bool:
        started.set()
        assert stores.reader(project_id) is None  # 훅 안에서 다시 열기는 기다리지 않는다
        release.wait(5)
        order.append("hook-done")
        return True

    stores = RecordsStores(lambda: spaces, SqliteStorage, on_open=hook)
    first = threading.Thread(target=stores.reader, args=("p1",))
    first.start()
    assert started.wait(5)

    def second() -> None:
        stores.reader("p1")
        order.append("second-read")

    other = threading.Thread(target=second)
    other.start()
    other.join(0.2)
    assert other.is_alive()  # 훅이 끝나기 전에는 읽지 않는다
    release.set()
    first.join(5)
    other.join(5)
    assert order == ["hook-done", "second-read"]


def test_waiter_retries_hook_when_owner_did_not_finish(spaces: Spaces) -> None:
    """먼저 연 스레드의 훅이 거짓이면, 기다리던 스레드가 이어서 다시 부른다."""
    import threading

    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def hook(project_id: str) -> bool:
        calls.append(threading.current_thread().name)
        if len(calls) == 1:
            started.set()
            release.wait(5)
            return False
        return True

    stores = RecordsStores(lambda: spaces, SqliteStorage, on_open=hook)
    first = threading.Thread(target=stores.reader, args=("p1",), name="first")
    first.start()
    assert started.wait(5)
    other = threading.Thread(target=stores.reader, args=("p1",), name="other")
    other.start()
    release.set()
    first.join(5)
    other.join(5)
    assert calls == ["first", "other"]


def test_wait_for_hook_is_bounded(spaces: Spaces) -> None:
    """훅이 멈춰도 다른 스레드는 `open_wait`가 지나면 기다리지 않고 연다."""
    import threading

    started = threading.Event()
    release = threading.Event()

    def hook(project_id: str) -> bool:
        started.set()
        release.wait(5)
        return True

    stores = RecordsStores(lambda: spaces, SqliteStorage, on_open=hook, open_wait=0.05)
    first = threading.Thread(target=stores.reader, args=("p1",))
    first.start()
    try:
        assert started.wait(5)
        assert stores.reader("p1") is None  # 기다림 상한 뒤 그냥 연다
    finally:
        release.set()
        first.join(5)


def test_closed_db_read_is_not_reported_as_corrupt(tmp_path: Path) -> None:
    """닫힌 기록 DB를 읽으면 깨짐(`corrupt`)이 아니라 닫힘 이유(`folder_missing`)."""
    db = open_records_db(tmp_path / "records.sqlite3", backup_dir=tmp_path / "backups")
    db.writable_engine()
    db.close()
    with pytest.raises(RecordsUnavailable) as caught:
        db.read_engine()
    assert caught.value.reason == "folder_missing"


def test_batch_delegates_to_port_or_is_empty_block(spaces: Spaces) -> None:
    """`batch()`: 포트가 `BatchRecordsSpaces`면 그 블록, 아니거나 포트가 없으면 빈 블록."""
    from collections.abc import Iterator
    from contextlib import contextmanager

    from agent_console_store import BatchRecordsSpaces

    assert not isinstance(spaces, BatchRecordsSpaces)
    with RecordsStores(lambda: spaces, SqliteStorage).batch():
        pass
    with RecordsStores(lambda: None, SqliteStorage).batch():
        pass

    calls: list[str] = []

    class Batched(Spaces):
        @contextmanager
        def batch(self) -> Iterator[None]:
            calls.append("enter")
            yield
            calls.append("exit")

    batched = Batched(spaces.tmp)
    assert isinstance(batched, BatchRecordsSpaces)
    with RecordsStores(lambda: batched, SqliteStorage).batch():
        assert calls == ["enter"]
    assert calls == ["enter", "exit"]
