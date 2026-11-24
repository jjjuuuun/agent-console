import threading

from agent_console_write_budget import WriteBudget, WriteBudgetLike


def test_limit() -> None:
    b = WriteBudget(2)
    assert [b.take() for _ in range(4)] == [True, True, False, False]
    assert b.used == 2


def test_zero_and_none() -> None:
    assert WriteBudget(0).take() is False
    unlimited = WriteBudget(None)
    assert all(unlimited.take() for _ in range(100))
    assert unlimited.used == 100


def test_thread_safe() -> None:
    b = WriteBudget(500)
    got: list[bool] = []
    lock = threading.Lock()

    def worker() -> None:
        for _ in range(100):
            ok = b.take()
            with lock:
                got.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert got.count(True) == 500
    assert b.used == 500


def test_protocol() -> None:
    class Always:
        def take(self) -> bool:
            return True

    assert isinstance(Always(), WriteBudgetLike)
    assert isinstance(WriteBudget(1), WriteBudgetLike)
