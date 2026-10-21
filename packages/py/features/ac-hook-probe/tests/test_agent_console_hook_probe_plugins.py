"""X5 `hook-probe-jsonl`·X6 `hook-probe`: 기본 루트·글롭·Run 경로 맥락·이벤트·소요 시간·상관."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.logs import LogSettings
from agent_console_hook_probe import RECORD_FORMAT
from agent_console_hook_probe.plugins import (
    CLASSIFIER_ID,
    SOURCE_ID,
    HookProbeClassifier,
    HookProbeSource,
)
from agent_console_logs import (
    ClassifyContext,
    LogFilter,
    LogIngestor,
    LogRegistries,
    LogSourceContext,
    RawRecord,
    SourceRef,
    effective_config,
    pair_durations,
    query_context,
    source_enabled,
)
from agent_console_logs.testing import MemoryLogIndex, no_writes_under, tree_digest


def _row(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "format": RECORD_FORMAT,
        "probe_id": "p1",
        "event": "PreToolUse",
        "session_id": "S",
        "tool_use_id": "toolu_1",
        "tool": "Bash",
        "agent_id": None,
        "agent_type": None,
        "cwd": "/proj",
        "matcher": "Bash",
        "context": {},
        "form": "shell",
        "shell": "sh",
        "command_digest": "sha256:00",
        "started_at": 100.0,
        "ended_at": 100.25,
        "duration_ms": 250.0,
        "exit_code": 0,
        "signal": None,
        "forwarded_signal": None,
        "error": None,
        "decision": {"value": "deny", "source": "json", "reason": "no"},
        "input": {"tool_input": {"command": "ls"}},
        "stdout": "{}",
        "stdout_json": {},
        "stderr": "",
        "bytes": {"stdin": 1, "stdout": 2, "stderr": 0},
        "truncated": {"stdin": False, "stdout": False, "stderr": False},
    }
    row.update(over)
    return row


def _write(path: Path, *rows: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_descriptors_and_registration() -> None:
    registries = LogRegistries()
    registries.load()
    assert SOURCE_ID in [d.id for d in registries.source_descriptors()]
    assert CLASSIFIER_ID in [d.id for d in registries.classifier_descriptors()]
    desc = HookProbeSource.descriptor
    assert (desc.format, desc.default_enabled, desc.reads_paths) == (CLASSIFIER_ID, True, True)
    assert source_enabled(desc, None) is True
    defaults = effective_config(desc.config_schema, {})
    assert defaults["include"] == ["**/hook-probe/*.jsonl"]
    assert defaults["run_layout"] is True


def test_default_root_is_state_runs_and_run_layout_meta(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _write(state / "runs" / "R1" / "team" / "dev" / "hook-probe" / "S.jsonl", _row())
    _write(state / "runs" / "R1" / "other.jsonl", _row())  # 글롭 밖
    src = HookProbeSource()
    cfg = effective_config(src.descriptor.config_schema, {})
    ctx = LogSourceContext(source_id=SOURCE_ID, config=cfg, paths={"state": state})
    [ref] = list(src.discover(ctx))
    assert ref.ref == "R1/team/dev/hook-probe/S.jsonl"
    assert ref.meta == {"run_id": "R1", "node_path": ["team", "dev"]}
    no_layout = LogSourceContext(
        source_id=SOURCE_ID, config={**cfg, "run_layout": False}, paths={"state": state}
    )
    assert next(iter(src.discover(no_layout))).meta == {}
    assert list(src.discover(LogSourceContext(source_id=SOURCE_ID, config=cfg))) == []


def _classify(row: Any, meta: dict[str, Any] | None = None, **cfg: Any) -> list[Any]:
    clf = HookProbeClassifier()
    config = effective_config(clf.descriptor.config_schema, cfg)
    ctx = ClassifyContext(source_id=SOURCE_ID, ref=SourceRef(ref="r"), config=config)
    return clf.classify(RawRecord(origin="r", offset=0, data=row, meta=meta or {}), ctx)


def test_classifier_start_and_complete_pair() -> None:
    start, end = _classify(_row(context={"run_id": "R9", "node_path": "a/b"}), {"run_id": "R1"})
    assert (start.stage, end.stage) == ("start", "complete")
    assert start.category == end.category == "hook"
    assert start.call_id == end.call_id == "p1"
    assert (start.time, end.time) == (100.0, 100.25)
    assert end.status == "deny"
    assert "PreToolUse Bash" in end.title
    assert "deny" in end.title
    assert end.correlation == {"call_id": "toolu_1", "hook_probe": "p1"}
    assert (end.run_id, end.node_path) == ("R9", ("a", "b"))  # 기록 context가 경로보다 우선
    assert end.session == "S"
    assert end.tool == "Bash"
    assert end.via == "PreToolUse"
    assert "hook" in end.tags
    assert "decision:deny" in end.tags
    assert end.detail is not None
    assert "input" not in end.detail
    assert start.detail == {"input": {"tool_input": {"command": "ls"}}, "matcher": "Bash"}


def test_classifier_error_category_is_config() -> None:
    _s, end = _classify(_row(exit_code=1, decision={"value": "error"}))
    assert end.category == "error"
    _s, end = _classify(_row(exit_code=1, decision={"value": "error"}), error_category="hook")
    assert end.category == "hook"
    _s, end = _classify(_row(exit_code=None, error="spawn_failed: X", decision={"value": "error"}))
    assert "spawn_failed" in end.title


def test_unknown_format_raises() -> None:
    with pytest.raises(ValueError, match="형식"):
        _classify(_row(format="hook-probe/99"))
    with pytest.raises(ValueError, match="객체"):
        _classify([1])


def test_ingest_end_to_end_read_only_with_duration(tmp_path: Path) -> None:
    state = tmp_path / "state"
    folder = state / "runs" / "R1" / "dev" / "hook-probe"
    _write(
        folder / "S.jsonl",
        _row(),
        _row(probe_id="p2", tool_use_id="toolu_2", started_at=200.0, ended_at=201.0),
    )
    (folder / "S.jsonl").open("a").write("not json\n")
    before = tree_digest(state)
    registries = LogRegistries()
    registries.load(enabled_sources={SOURCE_ID}, enabled_classifiers={CLASSIFIER_ID})
    index = MemoryLogIndex()
    ingestor = LogIngestor(index, registries, paths={"state": state})
    settings = LogSettings.model_validate({"sources": []})  # 기본 켜짐
    with no_writes_under(state):
        report = ingestor.scan(settings)
    assert tree_digest(state) == before
    [result] = [r for r in report.sources if r.source_id == SOURCE_ID]
    assert result.new_events == 5  # 기록 2개의 시작·끝 4 + 진단 1
    assert result.diagnostics == 1
    assert ingestor.scan(settings).new_events == 0  # 증분
    events = index.query_events(LogFilter(), query_context(settings)).items
    hook_events = [e for e in events if e.source == SOURCE_ID]
    assert {e.run_id for e in hook_events} == {"R1"}
    assert {tuple(e.node_path) for e in hook_events} == {("dev",)}
    durations = pair_durations(hook_events)
    assert sorted(set(durations.values())) == [250.0, 1000.0]
