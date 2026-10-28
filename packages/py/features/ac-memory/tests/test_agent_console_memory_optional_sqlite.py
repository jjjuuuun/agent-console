"""extra `sqlite` 없이도 최상위·`testing`의 나머지 도구가 동작한다.

sqlalchemy를 막은 새 프로세스에서 확인한다.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def test_top_level_and_testing_work_without_sqlalchemy() -> None:
    script = textwrap.dedent(
        """
        import sys
        sys.modules["sqlalchemy"] = None  # import하면 ImportError
        import agent_console_memory
        from agent_console_memory import InMemoryMemoryStore, iter_entries, retention_plan
        from agent_console_memory.testing import FakeClock, user_author
        from agent_console_contracts.memory import MemoryScopeRef
        store = InMemoryMemoryStore(clock=FakeClock())
        store.write(MemoryScopeRef(kind="notes", id=""), "a", "x", author=user_author())
        assert [e.key for e in iter_entries(store, with_content=False)] == ["a"]
        assert "sqlalchemy" not in {m for m in sys.modules if sys.modules[m] is not None}
        for name in ("agent_console_memory.sqlite",):
            try:
                __import__(name)
            except ImportError:
                pass
            else:
                raise SystemExit(name + " imported without sqlalchemy")
        try:
            from agent_console_memory.testing import build_scale_store
        except ImportError:
            pass
        else:
            raise SystemExit("scale tools imported without sqlalchemy")
        print("ok")
        """
    )
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=120, check=False
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok"
