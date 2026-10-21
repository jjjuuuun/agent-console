"""4R.5 QA: 다른 계보(chat·usage)가 올라간 DB에 logs 계보만 올리고 내려도 나머지는 불변."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

from agent_console_mod_logs.storage import BRANCH
from agent_console_store import SqliteDatabase


def test_logs_branch_up_down_leaves_other_branches_untouched(tmp_path: Path) -> None:
    chat = pytest.importorskip("agent_console_mod_chat.storage")
    usage = pytest.importorskip("agent_console_mod_usage.storage")
    db = SqliteDatabase.open(tmp_path / "host.sqlite3")
    db.upgrade([chat.BRANCH, usage.BRANCH])
    before = set(sa.inspect(db.engine).get_table_names())
    revs = (db.revision(), db.revision("chat"), db.revision("usage"))
    db.upgrade([chat.BRANCH, usage.BRANCH, BRANCH])
    assert db.revision("logs") == "logs_0001"
    assert (db.revision(), db.revision("chat"), db.revision("usage")) == revs
    db.downgrade_branch(BRANCH)
    after = set(sa.inspect(db.engine).get_table_names())
    assert after == before | {"alembic_version_logs"}
    assert (db.revision(), db.revision("chat"), db.revision("usage")) == revs
    db.close()
