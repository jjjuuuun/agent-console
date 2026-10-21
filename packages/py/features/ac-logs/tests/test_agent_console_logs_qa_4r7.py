"""4R.7 QA: ac-logs 보완(회전 감지 세대·identity 호환·축소 후 read_bytes) 수집 전체 경로 확인."""

import json
from pathlib import Path
from typing import Any

from agent_console_contracts.logs import LogSettings
from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context
from agent_console_logs.testing import MemoryLogIndex

OWN = {"normalized-v1", "mapped-jsonl"}


def _row(i: int, pad: int = 0) -> bytes:
    row: dict[str, Any] = {
        "schema_version": 1,
        "category": "llm",
        "title": f"t{i}" + "x" * pad,
        "session": "S",
    }
    return (json.dumps(row) + "\n").encode()


def _settings(root: Path) -> LogSettings:
    return LogSettings.model_validate(
        {"sources": [{"id": "normalized-v1", "enabled": True, "config": {"roots": [str(root)]}}]}
    )


def _titles(idx: MemoryLogIndex) -> list[str]:
    page = idx.query_events(LogFilter(limit=1000), query_context(None))
    return sorted(str(e.title) for e in page.items)


def _ing() -> tuple[LogIngestor, MemoryLogIndex]:
    reg = LogRegistries()
    reg.load(enabled_sources=OWN, enabled_classifiers=OWN)
    idx = MemoryLogIndex()
    return LogIngestor(idx, reg), idx


def test_rotation_keeps_old_and_new_events_without_duplicates(tmp_path: Path) -> None:
    f = tmp_path / "s.jsonl"
    f.write_bytes(_row(1, 3000) + _row(2, 3000))
    ing, idx = _ing()
    ing.scan(_settings(tmp_path))
    first = _titles(idx)
    assert len(first) == 2
    ing.scan(_settings(tmp_path))  # 변경 없음
    assert _titles(idx) == first
    f.write_bytes(_row(11, 3000) + _row(12, 3000) + _row(13, 3000))  # 회전(앞 4KB 다름)
    ing.scan(_settings(tmp_path))
    ing.scan(_settings(tmp_path))
    after = _titles(idx)
    assert len(after) == 5  # 옛 2 + 새 3, 중복 0
    f.write_bytes(_row(21, 3000) + _row(22, 3000) + _row(23, 3000) + _row(24, 3000))
    ing.scan(_settings(tmp_path))
    assert len(_titles(idx)) == 9


def test_rotation_to_smaller_file_keeps_new_events(tmp_path: Path) -> None:
    # 새 파일이 옛 오프셋보다 작고 지문 길이보다도 짧아 앞부분을 비교할 수 없는 회전.
    f = tmp_path / "s.jsonl"
    f.write_bytes(_row(1) + _row(2) + _row(3))
    ing, idx = _ing()
    ing.scan(_settings(tmp_path))
    assert len(_titles(idx)) == 3
    f.write_bytes(_row(91) + _row(92))
    ing.scan(_settings(tmp_path))
    assert {"t91", "t92"} <= set(_titles(idx))


def test_shrink_with_same_first_line_keeps_generation_and_no_duplicates(tmp_path: Path) -> None:
    f = tmp_path / "s.jsonl"
    f.write_bytes(_row(1) + _row(2) + _row(3))
    ing, idx = _ing()
    ing.scan(_settings(tmp_path))
    f.write_bytes(_row(1) + _row(2))  # 같은 앞부분으로 잘림
    ing.scan(_settings(tmp_path))
    assert _titles(idx) == ["t1", "t2", "t3"]


def test_shrink_with_different_content_indexes_all_new_rows(tmp_path: Path) -> None:
    f = tmp_path / "s.jsonl"
    f.write_bytes(_row(1) + _row(2) + _row(3) + _row(4))
    ing, idx = _ing()
    ing.scan(_settings(tmp_path))
    f.write_bytes(_row(91) + _row(92))
    ing.scan(_settings(tmp_path))
    assert {"t91", "t92"} <= set(_titles(idx))
    assert len(_titles(idx)) == 6


def test_append_after_scan_is_read_incrementally(tmp_path: Path) -> None:
    f = tmp_path / "s.jsonl"
    f.write_bytes(_row(1) + _row(2))
    ing, idx = _ing()
    ing.scan(_settings(tmp_path))
    with f.open("ab") as out:
        out.write(_row(3))
    ing.scan(_settings(tmp_path))
    assert _titles(idx) == ["t1", "t2", "t3"]
