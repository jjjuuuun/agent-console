"""1R.4 QA: 서로 다른 연결(엔진)이 같은 SQLite 파일에 동시에 응답·닫기·늦은 save를 해도 일관된다."""

import threading
from pathlib import Path
from typing import Any

from agent_console_contracts import Interaction
from agent_console_store import InteractionClosed, open_sqlite


def _inter(id: str) -> Interaction:
    return Interaction(
        id=id,
        run_id="r1",
        node_id="n1",
        kind="question",
        status="pending",
        created_at=1.0,
        payload={},
        response_schema={"type": "object"},
    )


def test_two_connections_answer_expire_and_late_save_race(tmp_path: Path) -> None:
    path = tmp_path / "race.sqlite3"
    stores = [open_sqlite(path), open_sqlite(path)]
    wins: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()
    try:
        for round_no in range(15):
            wins.clear()
            iid = f"i{round_no}"
            stores[0].interactions.save(_inter(iid))
            barrier = threading.Barrier(6)

            def run(fn: Any, tag: str, barrier: threading.Barrier = barrier) -> None:
                barrier.wait()
                try:
                    won = fn()
                except InteractionClosed:
                    return
                except BaseException as exc:
                    with lock:
                        errors.append(exc)
                    return
                if won:
                    with lock:
                        wins.append(tag)

            def answer(s: int, iid: str = iid) -> bool:
                stores[s].interactions.close(
                    iid, status="answered", closed_at=2.0, response={"s": s}, answered_by="user"
                )
                return True

            def sweep(iid: str = iid) -> bool:
                return bool(
                    stores[1].interactions.close_pending(
                        status="expired", closed_at=3.0, run_id="r1", close_reason="interrupted"
                    )
                )

            def late_save(iid: str = iid) -> bool:
                stores[0].interactions.save(_inter(iid))
                return False

            jobs = [
                (lambda: answer(0), "a0"),
                (lambda: answer(1), "a1"),
                (lambda: answer(0), "a0b"),
                (sweep, "sweep"),
                (late_save, "save"),
                (late_save, "save2"),
            ]
            threads = [threading.Thread(target=run, args=job) for job in jobs]
            for th in threads:
                th.start()
            for th in threads:
                th.join()
            assert errors == []
            final = stores[0].interactions.get(iid)
            assert final is not None
            # 늦은 save가 pending으로 되살리지 못한다
            assert final.status in ("answered", "expired")
            assert len(wins) == 1
    finally:
        for s in stores:
            s.close()
