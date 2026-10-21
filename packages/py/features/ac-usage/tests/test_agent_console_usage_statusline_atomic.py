"""QA: 쓰기 도중 끊김·동시 쓰기에서도 기존 파일이 부분적으로 덮이지 않는다."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from agent_console_usage.statusline import (
    read_statusline_file,
    update_statusline_file,
    write_statusline_file,
)

FUTURE = 4_000_000_000


def _payload(pct: float) -> dict[str, Any]:
    return {"rate_limits": {"five_hour": {"used_percentage": pct, "resets_at": FUTURE}}}


def test_interrupted_write_keeps_old_file_and_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "s.json"
    update_statusline_file(path, _payload(10), now=1.0)
    before = path.read_bytes()

    def boom(*_a: Any, **_k: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("agent_console_usage.statusline.os.replace", boom)
    with pytest.raises(KeyboardInterrupt):
        write_statusline_file(path, {"format": 1, "windows": {"x": {"observed_at": 2}}})
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["s.json"]


def test_concurrent_writers_never_leave_partial_file(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    update_statusline_file(path, _payload(1), now=1.0)
    stop = threading.Event()
    bad: list[str] = []

    def reader() -> None:
        while not stop.is_set():
            try:
                doc = read_statusline_file(path)
            except Exception as exc:
                bad.append(repr(exc))
                return
            if doc is None or "windows" not in doc:
                bad.append(json.dumps(doc))
                return

    def writer(base: int) -> None:
        for i in range(40):
            update_statusline_file(path, _payload(base + i), now=2.0 + i)

    r = threading.Thread(target=reader)
    ws = [threading.Thread(target=writer, args=(b,)) for b in (0, 100, 200)]
    r.start()
    for w in ws:
        w.start()
    for w in ws:
        w.join()
    stop.set()
    r.join()
    assert bad == []
    assert [p.name for p in tmp_path.iterdir()] == ["s.json"]
