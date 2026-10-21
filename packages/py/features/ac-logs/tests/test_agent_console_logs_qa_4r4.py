"""4R.4 QA: R8.1 토큰 1회(여러 행·여러 파일·재수집), 증분 경계, 경로 탈출, 비밀 가리기."""

import json
import os
from pathlib import Path
from typing import Any

from agent_console_contracts.logs import LogAggregateRequest, LogSettings
from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context
from agent_console_logs.plugins.normalized import NormalizedV1Source
from agent_console_logs.testing import MemoryLogIndex, no_writes_under, tree_digest

OWN_PLUGINS = {"normalized-v1", "mapped-jsonl"}


def _row(i: int, **extra: Any) -> bytes:
    row = {"schema_version": 1, "category": "llm", "title": f"t{i}", "session": "S", **extra}
    return (json.dumps(row) + "\n").encode()


def _usage(mid: str | None, out: int | None, inp: int = 100) -> dict[str, Any]:
    row: dict[str, Any] = {"thread": "T", "usage": {"input_tokens": inp}}
    if out is not None:
        row["usage"]["output_tokens"] = out
    if mid is not None:
        row["message_id"] = mid
    return row


def _settings(root: Path) -> LogSettings:
    return LogSettings.model_validate(
        {"sources": [{"id": "normalized-v1", "enabled": True, "config": {"roots": [str(root)]}}]}
    )


def _ing(**kw: Any) -> tuple[LogIngestor, MemoryLogIndex]:
    reg = LogRegistries()
    # 이 패키지의 기본 출처만(워크스페이스에 설치된 다른 플러그인 출처가 섞이지 않게)
    reg.load(enabled_sources=OWN_PLUGINS, enabled_classifiers=OWN_PLUGINS)
    idx = MemoryLogIndex()
    return LogIngestor(idx, reg, **kw), idx


def _out(idx: MemoryLogIndex, metric: str = "tokens.output") -> float | None:
    rows = idx.aggregate(LogAggregateRequest(metric=metric), query_context(None))
    return rows[0].value if rows else None


def test_tokens_once_across_rows_and_files_and_rescan(tmp_path: Path) -> None:
    (tmp_path / "a.jsonl").write_bytes(
        _row(1, **_usage("m1", 5)) + _row(2, **_usage("m1", 30)) + _row(3, **_usage("m1", 12))
    )
    (tmp_path / "b.jsonl").write_bytes(_row(4, **_usage("m1", 30)) + _row(5, **_usage("m2", 7)))
    ing, idx = _ing()
    ing.scan(_settings(tmp_path))
    assert _out(idx) == 37.0  # m1=30 한 번 + m2=7
    # 재수집(파일 줄었다 다시 커짐 = 처음부터 읽기)해도 불변
    (tmp_path / "a.jsonl").write_bytes(_row(1, **_usage("m1", 5)))
    ing.scan(_settings(tmp_path))
    (tmp_path / "a.jsonl").write_bytes(
        _row(1, **_usage("m1", 5)) + _row(2, **_usage("m1", 30)) + _row(3, **_usage("m1", 12))
    )
    ing.scan(_settings(tmp_path))
    ing.scan(_settings(tmp_path), final=True)
    assert _out(idx) == 37.0
    assert len(idx.token_samples(LogFilter(), query_context(None))) == 2


def test_token_boundaries_without_message_id_and_missing_output(tmp_path: Path) -> None:
    # message_id 없음: 행마다 독립 키(합산되지만 재수집으로 늘지 않는다)
    (tmp_path / "a.jsonl").write_bytes(_row(1, **_usage(None, 4)) + _row(2, **_usage(None, 6)))
    # output 없는 표본 뒤에 값이 오면 값을 취한다. 값 뒤에 없는 표본이 와도 유지.
    (tmp_path / "b.jsonl").write_bytes(
        _row(3, **_usage("m", None)) + _row(4, **_usage("m", 9)) + _row(5, **_usage("m", None))
    )
    ing, idx = _ing()
    ing.scan(_settings(tmp_path))
    assert _out(idx) == 19.0
    ing.scan(_settings(tmp_path))
    (tmp_path / "a.jsonl").write_bytes(b"")  # 비움 → 다시 읽어도 늘지 않음
    ing.scan(_settings(tmp_path))
    assert _out(idx) == 19.0


def test_same_size_different_content_and_rotation(tmp_path: Path) -> None:
    f = tmp_path / "e.jsonl"
    f.write_bytes(_row(1) + _row(2))
    ing, idx = _ing()
    assert ing.scan(_settings(tmp_path)).new_events == 2
    # 같은 크기 다른 내용(mtime 변경): 앞부분 지문이 달라 처음부터 다시 읽는다(4R.7 보완)
    f.write_bytes(_row(8) + _row(9))
    os.utime(f, (1, 1))
    assert ing.scan(_settings(tmp_path)).new_events == 2
    # 회전: 같은 이름의 더 큰 새 파일 → 앞부분을 건너뛰지 않고 전부 읽는다
    f.write_bytes(_row(10) + _row(11) + _row(12) + _row(13))
    assert ing.scan(_settings(tmp_path)).new_events == 4
    # 다시 수집해도 중복 0(uid)
    assert ing.scan(_settings(tmp_path)).new_events == 0
    (tmp_path / "r.jsonl").write_bytes(_row(20))
    assert ing.scan(_settings(tmp_path)).new_events == 1
    assert idx.max_seq() is not None


def test_same_size_same_head_is_documented_limit(tmp_path: Path) -> None:
    # 앞부분(지문 범위)과 크기가 같고 그 뒤만 바뀌면 감지하지 못한다(README 한계).
    from agent_console_logs._jsonl import HEAD_FINGERPRINT_BYTES

    pad = "x" * HEAD_FINGERPRINT_BYTES
    f = tmp_path / "e.jsonl"
    f.write_bytes(_row(1, pad=pad) + _row(2))
    ing, _idx = _ing()
    assert ing.scan(_settings(tmp_path)).new_events == 2
    f.write_bytes(_row(1, pad=pad) + _row(3))
    os.utime(f, (1, 1))
    assert ing.scan(_settings(tmp_path)).new_events == 0


def test_ref_escape_rejected(tmp_path: Path) -> None:
    from agent_console_logs import Cursor, LogSourceContext, SourceRef
    from agent_console_logs.testing import RecordingOpen

    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "secret.jsonl").write_bytes(_row(1))
    (root / "ok.jsonl").write_bytes(_row(2))
    rec = RecordingOpen()
    ctx = LogSourceContext(
        source_id="normalized-v1",
        config={"roots": [str(root)]},
        environ={},
        paths={},
        open_read=rec,
        now=lambda: 0.0,
    )
    src = NormalizedV1Source()
    for bad in (
        "../secret.jsonl",
        "a/../../secret.jsonl",
        str(tmp_path / "secret.jsonl"),
        "/etc/passwd",
        "C:/x.jsonl",
        "",
    ):
        res = src.read(
            SourceRef(ref=bad, size=None, mtime=None, meta={}),
            Cursor(),
            ctx,
            budget=1000,
            final=True,
        )
        assert res.records == [], bad
    assert rec.opened == []


def test_redaction_injected_and_originals_untouched(tmp_path: Path) -> None:
    (tmp_path / "e.jsonl").write_bytes(
        _row(1, detail={"k": "sk-SECRET123"}, raw={"k": "sk-SECRET123"}, title="sk-SECRET123 t")
    )
    before = tree_digest(tmp_path)

    def red(v: Any) -> Any:
        return json.loads(json.dumps(v).replace("sk-SECRET123", "***"))

    ing, idx = _ing(redact=red)
    with no_writes_under(tmp_path):
        ing.scan(_settings(tmp_path))
    assert tree_digest(tmp_path) == before
    ev = idx.query_events(LogFilter(), query_context(None)).items[0]
    d = idx.get_event(ev.uid, query_context(None))
    assert d is not None
    blob = d.event.model_dump_json()
    assert "SECRET" not in blob
    assert "SECRET" not in ev.summary
    assert "SECRET" not in ev.title


def test_redact_failure_does_not_leak_into_error_message(tmp_path: Path) -> None:
    ing, _ = _ing(redact=lambda v: v)
    (tmp_path / "e.jsonl").write_bytes(_row(1))
    report = ing.scan(
        LogSettings.model_validate(
            {
                "sources": [
                    {
                        "id": "normalized-v1",
                        "enabled": True,
                        "config": {"roots": [str(tmp_path)], "include": 5},
                    }
                ]
            }
        )
    )
    assert report.sources[0].error_code is not None
