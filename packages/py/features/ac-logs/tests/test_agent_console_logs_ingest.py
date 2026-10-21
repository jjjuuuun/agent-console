"""LogIngestor: 증분 수집·중복 0·예산·진단·출처 실패 격리·런타임 출처·가리기."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, ClassVar

import pytest

from agent_console_contracts.logs import (
    LogClassifierDescriptor,
    LogSettings,
    LogSourceDescriptor,
    LogTaxonomy,
    TokenSample,
)
from agent_console_logs import (
    ERROR_INVALID_CONFIG,
    ERROR_SOURCE_FAILED,
    ERROR_UNKNOWN_CLASSIFIER,
    ClassifyContext,
    Cursor,
    LogEventDraft,
    LogFilter,
    LogIngestor,
    LogRegistries,
    LogSourceContext,
    RawRecord,
    ReadResult,
    SourceRef,
    query_context,
)
from agent_console_logs.testing import MemoryLogIndex, RecordingOpen, no_writes_under, tree_digest

OWN_PLUGINS = {"normalized-v1", "mapped-jsonl"}


def _v1(i: int, **extra: Any) -> bytes:
    row = {"schema_version": 1, "category": "llm", "title": f"t{i}", "session": "S", **extra}
    return (json.dumps(row, ensure_ascii=False) + "\n").encode()


def _settings(root: Path, **cfg: Any) -> LogSettings:
    return LogSettings.model_validate(
        {
            "sources": [
                {"id": "normalized-v1", "enabled": True, "config": {"roots": [str(root)], **cfg}}
            ]
        }
    )


def _ingestor(index: MemoryLogIndex | None = None, **kw: Any) -> tuple[LogIngestor, MemoryLogIndex]:
    registries = LogRegistries()
    # 이 패키지의 기본 출처만(워크스페이스에 설치된 다른 플러그인 출처가 섞이지 않게)
    registries.load(enabled_sources=OWN_PLUGINS, enabled_classifiers=OWN_PLUGINS)
    index = index or MemoryLogIndex()
    clock = iter(range(1, 10_000))
    kw.setdefault("clock", lambda: float(next(clock)))
    return LogIngestor(index, registries, **kw), index


def _titles(index: MemoryLogIndex) -> list[str]:
    ctx = query_context(None)
    return [e.title for e in index.query_events(LogFilter(limit=200), ctx).items]


def test_incremental_scan_no_duplicates(tmp_path: Path) -> None:
    f = tmp_path / "e.jsonl"
    f.write_bytes(_v1(1) + _v1(2) + b'{"schema_version": 1, "categ')
    ingestor, index = _ingestor()
    report = ingestor.scan(_settings(tmp_path))
    assert report.new_events == 2
    assert report.sources[0].source_id == "normalized-v1"
    assert (report.sources[0].pending_bytes or 0) > 0
    # 미완성 줄이 완성되면 다음 수집에서 읽는다
    f.write_bytes(_v1(1) + _v1(2) + _v1(3))
    assert ingestor.scan(_settings(tmp_path)).new_events == 1
    assert ingestor.scan(_settings(tmp_path)).new_events == 0
    assert _titles(index) == ["t1", "t2", "t3"]


def test_disabled_by_default(tmp_path: Path) -> None:
    (tmp_path / "e.jsonl").write_bytes(_v1(1))
    ingestor, _ = _ingestor()
    report = ingestor.scan(None)
    assert report.sources == []
    infos = {i.descriptor.id: i for i in ingestor.sources(None)}
    assert set(infos) == {"normalized-v1", "mapped-jsonl"}
    assert not any(i.enabled for i in infos.values())
    assert all(i.origin == "plugin" for i in infos.values())


def test_shrunk_file_reread_without_duplicates(tmp_path: Path) -> None:
    f = tmp_path / "e.jsonl"
    f.write_bytes(_v1(1) + _v1(2))
    ingestor, index = _ingestor()
    ingestor.scan(_settings(tmp_path))
    f.write_bytes(_v1(1))  # 같은 내용으로 줄어듦 → 처음부터, identity로 중복 0
    assert ingestor.scan(_settings(tmp_path)).new_events == 0
    assert _titles(index) == ["t1", "t2"]


def test_budget_carries_over(tmp_path: Path) -> None:
    (tmp_path / "e.jsonl").write_bytes(b"".join(_v1(i) for i in range(10)))
    ingestor, index = _ingestor(budget_bytes=len(_v1(0)) * 4)
    first = ingestor.scan(_settings(tmp_path))
    assert first.new_events == 4
    assert first.sources[0].pending_bytes == len(_v1(0)) * 6
    ingestor.scan(_settings(tmp_path))
    ingestor.scan(_settings(tmp_path))
    assert len(_titles(index)) == 10


def test_final_reads_unterminated_line(tmp_path: Path) -> None:
    (tmp_path / "e.jsonl").write_bytes(_v1(1).rstrip(b"\n"))
    ingestor, _ = _ingestor()
    assert ingestor.scan(_settings(tmp_path)).new_events == 0
    assert ingestor.scan(_settings(tmp_path), final=True).new_events == 1


def test_bad_rows_become_diagnostics(tmp_path: Path) -> None:
    (tmp_path / "e.jsonl").write_bytes(b"garbage\n" + b'{"schema_version": 2}\n' + _v1(1))
    ingestor, index = _ingestor()
    report = ingestor.scan(_settings(tmp_path))
    assert report.sources[0].diagnostics == 2
    assert report.new_events == 3
    ctx = query_context(None)
    diag = index.query_events(LogFilter(source=("diagnostic",)), ctx).items
    assert [e.category for e in diag] == ["error", "error"]
    assert all("diagnostic" in e.tags for e in diag)
    assert diag[0].title == "로그 형식 해석 실패"
    assert diag[1].title == "로그 분류 실패"
    detail = index.get_event(diag[1].uid, ctx)
    assert detail is not None
    assert "schema_version" in json.dumps(detail.event.detail)


def test_batches_and_cursor(tmp_path: Path) -> None:
    (tmp_path / "e.jsonl").write_bytes(b"".join(_v1(i) for i in range(7)))
    writes: list[int] = []

    class Spy(MemoryLogIndex):
        def write(self, batch):  # type: ignore[no-untyped-def]
            writes.append(len(batch.records))
            return super().write(batch)

    ingestor, index = _ingestor(Spy(), batch_size=3)
    ingestor.scan(_settings(tmp_path))
    assert writes == [3, 3, 1]
    cursor = index.get_cursor("normalized-v1", "e.jsonl")
    assert cursor is not None
    assert cursor.offset == (tmp_path / "e.jsonl").stat().st_size
    writes.clear()
    ingestor.scan(_settings(tmp_path))
    assert writes == []  # 바뀌지 않은 파일은 읽지도 쓰지도 않는다


def test_source_never_writes_originals(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "e.jsonl").write_bytes(_v1(1) + b"bad\n")
    before = tree_digest(tmp_path)
    opener = RecordingOpen()
    ingestor, _ = _ingestor(open_read=opener)
    with no_writes_under(tmp_path):
        ingestor.scan(_settings(tmp_path), final=True)
    assert tree_digest(tmp_path) == before
    assert opener.opened  # open_read로만 열었다


def test_redaction_applies_before_store(tmp_path: Path) -> None:
    (tmp_path / "e.jsonl").write_bytes(_v1(1, detail={"token": "sk-SECRET"}))

    def redact(value: Any) -> Any:
        return json.loads(json.dumps(value).replace("sk-SECRET", "[가림]"))

    ingestor, index = _ingestor(redact=redact)
    ingestor.scan(_settings(tmp_path))
    ev = index.query_events(LogFilter(), query_context(None)).items[0]
    detail = index.get_event(ev.uid, query_context(None))
    assert detail is not None
    assert "sk-SECRET" not in json.dumps(detail.event.model_dump(mode="json"))
    assert "[가림]" in ev.summary


def test_unknown_classifier_and_bad_config_isolated(tmp_path: Path) -> None:
    (tmp_path / "e.jsonl").write_bytes(_v1(1))
    ingestor, index = _ingestor()
    settings = LogSettings.model_validate(
        {
            "sources": [
                {"id": "mapped-jsonl", "enabled": True, "config": {"roots": 5}},
                {
                    "id": "normalized-v1",
                    "enabled": True,
                    "config": {"roots": [str(tmp_path)], "classifier": {"id": "nope"}},
                },
            ]
        }
    )
    report = ingestor.scan(settings)
    codes = {r.source_id: r.error_code for r in report.sources}
    assert codes == {
        "mapped-jsonl": ERROR_INVALID_CONFIG,
        "normalized-v1": ERROR_UNKNOWN_CLASSIFIER,
    }
    status = {i.descriptor.id: i.status.error_code for i in ingestor.sources(settings)}
    assert status["normalized-v1"] == ERROR_UNKNOWN_CLASSIFIER
    assert index.max_seq() is None


class _Boom:
    descriptor: ClassVar[LogSourceDescriptor] = LogSourceDescriptor(
        id="boom", title="boom", format="x", default_enabled=True, reads_paths=False
    )

    def discover(self, ctx: LogSourceContext) -> Iterable[SourceRef]:
        raise RuntimeError("discover failed")

    def read(
        self, ref: SourceRef, cursor: Cursor, ctx: LogSourceContext, *, budget: int, final: bool
    ) -> ReadResult:
        raise AssertionError


class _Runs:
    """런타임 출처 예: Run별 이벤트 목록(오프셋 = 다음 인덱스)."""

    descriptor: ClassVar[LogSourceDescriptor] = LogSourceDescriptor(
        id="runs", title="runs", format="runs", default_enabled=True, reads_paths=False
    )

    def __init__(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self.data = data

    def discover(self, ctx: LogSourceContext) -> Iterable[SourceRef]:
        return [SourceRef(ref=k, size=len(v), meta={"run": k}) for k, v in self.data.items()]

    def read(
        self, ref: SourceRef, cursor: Cursor, ctx: LogSourceContext, *, budget: int, final: bool
    ) -> ReadResult:
        rows = self.data[ref.ref][cursor.offset :]
        records = [
            RawRecord(origin=ref.ref, offset=cursor.offset + i, data=r, meta=ref.meta)
            for i, r in enumerate(rows)
        ]
        return ReadResult(
            records=records,
            cursor=Cursor(offset=cursor.offset + len(rows)),
            read_bytes=len(rows),
            exhausted=True,
        )


class _RunClassifier:
    descriptor: ClassVar[LogClassifierDescriptor] = LogClassifierDescriptor(id="runs", title="runs")

    def classify(self, record: RawRecord, ctx: ClassifyContext) -> list[LogEventDraft]:
        if record.data.get("boom"):
            raise KeyError("boom")
        return [
            LogEventDraft(
                category=record.data["kind"],
                run_id=str(record.meta["run"]),
                session="R",
                thread="n1",
                message_id=record.data.get("mid", ""),
                usage=TokenSample(output_tokens=record.data["out"])
                if "out" in record.data
                else None,
            )
        ]


def test_runtime_source_and_failure_isolation() -> None:
    ingestor, index = _ingestor()
    ingestor.add_runtime_source(_Boom(), classifier=_RunClassifier())
    runs = _Runs({"r1": [{"kind": "a", "mid": "m", "out": 3}, {"kind": "b", "mid": "m", "out": 9}]})
    ingestor.add_runtime_source(runs, classifier=_RunClassifier())
    with pytest.raises(ValueError, match="runs"):
        ingestor.add_runtime_source(runs, classifier=_RunClassifier())
    with pytest.raises(ValueError, match="normalized-v1"):
        ingestor.add_runtime_source(_Named("normalized-v1"), classifier=_RunClassifier())
    report = ingestor.scan(None)
    by_id = {r.source_id: r for r in report.sources}
    assert by_id["boom"].error_code == ERROR_SOURCE_FAILED
    assert "discover failed" in (by_id["boom"].message or "")
    assert by_id["runs"].new_events == 2
    runs.data["r1"].append({"kind": "c", "boom": True})
    assert ingestor.scan(None, source_ids=["runs"]).sources[0].diagnostics == 1
    samples = index.token_samples(LogFilter(), query_context(None))
    assert [s.output_tokens for s in samples] == [9]
    infos = {i.descriptor.id: i.origin for i in ingestor.sources(None)}
    assert infos["runs"] == "runtime"


class _Named(_Boom):
    def __init__(self, sid: str) -> None:
        self.descriptor = _Boom.descriptor.model_copy(update={"id": sid})  # type: ignore[misc]


def test_usage_without_message_id_gets_unique_key() -> None:
    ingestor, index = _ingestor()
    ingestor.add_runtime_source(
        _Runs({"r": [{"kind": "a", "out": 1}, {"kind": "a", "out": 2}]}),
        classifier=_RunClassifier(),
    )
    ingestor.scan(None)
    samples = index.token_samples(LogFilter(), query_context(None))
    assert sorted(s.output_tokens or 0 for s in samples) == [1, 2]
    assert all(s.message_id.startswith("~") for s in samples)


def test_empty_taxonomy_still_works(tmp_path: Path) -> None:
    """R0.1: 분류 체계를 통째로 비워도 수집·질의가 동작한다."""
    (tmp_path / "e.jsonl").write_bytes(_v1(1, category="whatever") + _v1(2, category="error"))
    ingestor, index = _ingestor()
    ingestor.scan(_settings(tmp_path))
    ctx = query_context(None, base_taxonomy=LogTaxonomy())
    assert ctx.error_categories == frozenset()
    sessions = index.list_sessions(LogFilter(), ctx)
    assert sessions[0].events == 2
    assert sessions[0].errors == 0
    tl = index.timeline("S", ctx)
    assert tl is not None
    assert [e.category for e in tl.events] == ["whatever", "error"]


def test_repo_root_from_worktree(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: /repo/.git/worktrees/wt\n", encoding="utf-8")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "e.jsonl").write_bytes(_v1(1, cwd=str(wt)))
    ingestor, index = _ingestor()
    ingestor.scan(_settings(logs))
    ev = index.query_events(LogFilter(), query_context(None)).items[0]
    assert ev.repo_root == "/repo"
    off = LogSettings.model_validate(
        {**_settings(logs).model_dump(exclude_unset=True), "projects": {"git_worktrees": False}}
    )
    (logs / "e.jsonl").write_bytes(_v1(1, cwd=str(wt)) + _v1(2, cwd=str(wt)))
    ingestor.scan(off)
    newest = index.query_events(LogFilter(order="desc", limit=1), query_context(None)).items[0]
    assert newest.repo_root == ""


def test_invalid_constructor_values() -> None:
    with pytest.raises(ValueError, match="budget"):
        LogIngestor(MemoryLogIndex(), LogRegistries(), budget_bytes=0)
