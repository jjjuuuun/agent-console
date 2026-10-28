"""QA(5.7R.9~11) 보강: 비밀 가림 모드의 키 거부, 가림 값의 저장소 잔존,
가져오기 문제 목록의 본문 노출."""

from __future__ import annotations

import io
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.memory import MemoryScopeRef
from agent_console_memory import (
    InMemoryMemoryStore,
    MemoryPolicy,
    MemorySecretGuard,
    MemoryStoreError,
    import_markdown,
)
from agent_console_memory.sqlite import open_sqlite_memory_store
from agent_console_memory.testing import FakeClock, user_author

SECRET = "sk-ant-api03-" + "A1b2C3d4E5f6G7h8" * 3
SCOPE = MemoryScopeRef(kind="notes", id="g1")


def _stores(tmp_path: Path) -> list[Any]:
    policy = MemoryPolicy(secrets=MemorySecretGuard(mode="redact"))
    return [
        InMemoryMemoryStore(policy=policy, clock=FakeClock()),
        open_sqlite_memory_store(tmp_path / "r.sqlite3", policy=policy, clock=FakeClock()),
    ]


def test_redact_mode_still_rejects_secret_in_key(tmp_path: Path) -> None:
    for store in _stores(tmp_path):
        with pytest.raises(MemoryStoreError):
            store.write(SCOPE, f"k/{SECRET}", "x", author=user_author())
        ok = store.write(SCOPE, "ok", "x", author=user_author()).entry
        with pytest.raises(MemoryStoreError):
            store.move(ok.id, author=user_author(), to_key=f"k/{SECRET}")


def test_redact_mode_leaves_no_secret_in_db(tmp_path: Path) -> None:
    store = _stores(tmp_path)[1]
    entry = store.write(
        SCOPE, "k", f"a {SECRET} b", author=user_author(), tags=[SECRET[:30], "t"]
    ).entry
    store.update(entry.id, author=user_author(), content=f"c {SECRET}")
    store.write(SCOPE, "k", f"d {SECRET}", author=user_author(), mode="append")
    store.close()
    with sqlite3.connect(tmp_path / "r.sqlite3") as conn:
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            for row in conn.execute(f'SELECT * FROM "{name}"'):
                for v in row:
                    raw = v.decode("latin-1") if isinstance(v, bytes) else str(v)
                    assert SECRET not in raw, name
                    assert SECRET[:30] not in raw, name


def _zip(files: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items():
            z.writestr(n, d)
    return buf.getvalue()


def test_problem_list_never_contains_any_file_text() -> None:
    marker = "ZZMARKERZZ-do-not-echo"
    files: dict[str, str | bytes] = {
        "notes/g1/yaml1.md": f"---\ntags: [{marker}\n---\nbody {marker}",
        "notes/g1/yaml2.md": f"---\n{marker}: [: :\n  - {marker}\n---\n{marker}",
        "notes/g1/type.md": f"---\ncontent_type: '{marker}; x'\n---\n{marker}",
        "notes/g1/flag.md": f"---\npinned: {marker}\n---\n{marker}",
        "notes/g1/tags.md": f"---\ntags: {marker}\n---\n{marker}",
        f"notes/g1/{marker}.txt": marker,
        "notes/g1/bin.md": b"\xff\xfe" + marker.encode(),
        "notes/g1/leak.md": f"{SECRET} {marker}",
    }
    for policy in (MemoryPolicy(), MemoryPolicy(secrets=MemorySecretGuard(mode="redact"))):
        store = InMemoryMemoryStore(policy=policy, clock=FakeClock())
        for dry in (True, False):
            result = import_markdown(store, _zip(files), dry_run=dry)
            dumped = result.model_dump_json()
            for needle in (SECRET, f"body {marker}", f"{marker}; x", f"[{marker}"):
                assert needle not in dumped, needle
            for e in result.errors:
                assert marker not in e.message, (e.path, e.message)
