"""JsonlFileSource 증분 규칙(agent_bench `_ingest`와 같음)."""

import json
from pathlib import Path
from typing import ClassVar

import pytest

from agent_console_contracts.logs import LogSourceDescriptor
from agent_console_logs import (
    DIAGNOSTIC_META_KEY,
    JSONL_CONFIG_SCHEMA,
    Cursor,
    JsonlFileSource,
    LogSourceContext,
    SourceRef,
    effective_config,
)
from agent_console_logs.testing import RecordingOpen, WriteAttempt, no_writes_under, tree_digest


class _Src(JsonlFileSource):
    descriptor: ClassVar[LogSourceDescriptor] = LogSourceDescriptor(
        id="t", title="t", format="t", config_schema=JSONL_CONFIG_SCHEMA
    )


def _ctx(root: Path, opener: RecordingOpen | None = None, **cfg: object) -> LogSourceContext:
    config = effective_config(JSONL_CONFIG_SCHEMA, {"roots": [str(root)], **cfg})
    return LogSourceContext(
        source_id="t", config=config, open_read=opener or RecordingOpen(), environ={"HOME": "/h"}
    )


def _line(i: int) -> bytes:
    return (json.dumps({"i": i}) + "\n").encode()


def test_discover_include_exclude_and_relative_refs(tmp_path: Path) -> None:
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "x.jsonl").write_bytes(_line(1))
    (tmp_path / "a" / "b" / "y.jsonl").write_bytes(_line(1))
    (tmp_path / "a" / "skip.jsonl").write_bytes(_line(1))
    (tmp_path / "a" / "z.txt").write_bytes(b"")
    refs = list(_Src().discover(_ctx(tmp_path, exclude=["a/skip.jsonl"])))
    assert [r.ref for r in refs] == ["x.jsonl", "a/b/y.jsonl"]
    assert refs[0].size == len(_line(1))


def test_partial_last_line_held_until_final(tmp_path: Path) -> None:
    f = tmp_path / "s.jsonl"
    f.write_bytes(_line(1) + b'{"i": 2}')
    src, ctx = _Src(), _ctx(tmp_path)
    ref = next(iter(src.discover(ctx)))
    res = src.read(ref, Cursor(), ctx, budget=1000, final=False)
    assert [r.data for r in res.records] == [{"i": 1}]
    assert res.cursor.offset == len(_line(1))
    assert res.exhausted
    final = src.read(ref, res.cursor, ctx, budget=1000, final=True)
    assert [r.data for r in final.records] == [{"i": 2}]


def test_budget_resumes_next_time(tmp_path: Path) -> None:
    (tmp_path / "s.jsonl").write_bytes(b"".join(_line(i) for i in range(10)))
    src, ctx = _Src(), _ctx(tmp_path)
    ref = next(iter(src.discover(ctx)))
    first = src.read(ref, Cursor(), ctx, budget=len(_line(0)) * 3, final=False)
    assert [r.data["i"] for r in first.records] == [0, 1, 2]
    assert not first.exhausted
    rest = src.read(ref, first.cursor, ctx, budget=10_000, final=False)
    assert [r.data["i"] for r in rest.records] == list(range(3, 10))
    assert rest.exhausted


def test_shrunk_file_restarts(tmp_path: Path) -> None:
    f = tmp_path / "s.jsonl"
    f.write_bytes(_line(1) + _line(2))
    src, ctx = _Src(), _ctx(tmp_path)
    ref = next(iter(src.discover(ctx)))
    res = src.read(ref, Cursor(), ctx, budget=1000, final=False)
    f.write_bytes(_line(9))
    ref = next(iter(src.discover(ctx)))
    again = src.read(ref, res.cursor, ctx, budget=1000, final=False)
    assert [r.data for r in again.records] == [{"i": 9}]
    assert again.records[0].offset == 0


def test_bad_line_becomes_diagnostic_record(tmp_path: Path) -> None:
    (tmp_path / "s.jsonl").write_bytes(b"not json\n\n" + _line(3))
    src, ctx = _Src(), _ctx(tmp_path)
    res = src.read(next(iter(src.discover(ctx))), Cursor(), ctx, budget=1000, final=False)
    assert len(res.records) == 2
    assert DIAGNOSTIC_META_KEY in res.records[0].meta
    assert res.records[0].data == {"text": "not json"}
    assert res.records[1].offset == len(b"not json\n\n")


def test_reads_only_through_open_read_and_never_writes(tmp_path: Path) -> None:
    (tmp_path / "s.jsonl").write_bytes(_line(1) + _line(2))
    before = tree_digest(tmp_path)
    opener = RecordingOpen()
    src, ctx = _Src(), _ctx(tmp_path, opener)
    with no_writes_under(tmp_path):
        for ref in src.discover(ctx):
            src.read(ref, Cursor(), ctx, budget=1000, final=True)
        with pytest.raises(WriteAttempt):
            (tmp_path / "s.jsonl").open("ab")  # 감시가 실제로 동작한다
    assert opener.opened == [tmp_path / "s.jsonl"]
    assert tree_digest(tmp_path) == before


def test_resolve_rejects_escape(tmp_path: Path) -> None:
    src, ctx = _Src(), _ctx(tmp_path)
    assert src.resolve("../etc/passwd", ctx) is None
    assert src.resolve("/abs", ctx) is None
    res = src.read(SourceRef(ref="../x"), Cursor(), ctx, budget=1, final=False)
    assert res.records == []
    assert res.exhausted


def test_home_expansion_uses_injected_environ(tmp_path: Path) -> None:
    src = _Src()
    ctx = LogSourceContext(source_id="t", config={"roots": ["~/logs"]}, environ={"HOME": "/h"})
    assert src.roots(ctx) == [Path("/h/logs")]
    assert src.roots(LogSourceContext(source_id="t")) == []


def test_rotated_larger_file_is_read_from_start(tmp_path: Path) -> None:
    f = tmp_path / "s.jsonl"
    f.write_bytes(_line(1) + _line(2))
    src, ctx = _Src(), _ctx(tmp_path)
    first = src.read(next(iter(src.discover(ctx))), Cursor(), ctx, budget=1000, final=False)
    assert "jsonl_head" in first.cursor.state
    f.write_bytes(_line(7) + _line(8) + _line(9) + _line(10))  # 같은 이름, 더 큰 새 파일
    again = src.read(next(iter(src.discover(ctx))), first.cursor, ctx, budget=1000, final=False)
    assert [r.data["i"] for r in again.records] == [7, 8, 9, 10]
    assert again.read_bytes == f.stat().st_size
    assert {r.generation for r in again.records} == {1}  # 새 내용 = 새 세대(identity가 갈림)
    assert again.cursor.state["jsonl_generation"] == 1
    # 같은 세대에서 이어 쓰면 세대가 그대로다
    with f.open("ab") as out:
        out.write(_line(11))
    more = src.read(next(iter(src.discover(ctx))), again.cursor, ctx, budget=1000, final=False)
    assert [(r.data["i"], r.generation) for r in more.records] == [(11, 1)]


def test_identity_includes_generation_only_when_rotated() -> None:
    from agent_console_logs import LogEventDraft, identity_for

    draft = LogEventDraft(category="x")
    assert identity_for(draft, source_id="s", origin="a.jsonl", offset=5, index=0) == (
        "s:a.jsonl:5"
    )
    assert (
        identity_for(draft, source_id="s", origin="a.jsonl", offset=5, index=1, generation=2)
        == "s:a.jsonl@2:5:1"
    )


def test_appended_file_keeps_offset_and_head(tmp_path: Path) -> None:
    f = tmp_path / "s.jsonl"
    f.write_bytes(_line(1))
    src, ctx = _Src(), _ctx(tmp_path)
    first = src.read(next(iter(src.discover(ctx))), Cursor(), ctx, budget=1000, final=False)
    with f.open("ab") as out:
        out.write(_line(2))
    nxt = src.read(next(iter(src.discover(ctx))), first.cursor, ctx, budget=1000, final=False)
    assert [r.data["i"] for r in nxt.records] == [2]
    assert nxt.read_bytes == len(_line(2))


def test_cursor_without_head_state_is_trusted(tmp_path: Path) -> None:
    # 지문이 없는 옛 커서는 그대로 이어 읽는다(호환).
    f = tmp_path / "s.jsonl"
    f.write_bytes(_line(1) + _line(2))
    src, ctx = _Src(), _ctx(tmp_path)
    res = src.read(
        next(iter(src.discover(ctx))), Cursor(offset=len(_line(1))), ctx, budget=1000, final=False
    )
    assert [r.data["i"] for r in res.records] == [2]


def test_read_bytes_after_shrink_counts_from_restart(tmp_path: Path) -> None:
    f = tmp_path / "s.jsonl"
    f.write_bytes(b"".join(_line(i) for i in range(5)))
    src, ctx = _Src(), _ctx(tmp_path)
    first = src.read(next(iter(src.discover(ctx))), Cursor(), ctx, budget=10_000, final=False)
    f.write_bytes(b"".join(_line(i) for i in range(20, 24)))  # 더 작은 파일
    assert f.stat().st_size < first.cursor.offset
    again = src.read(next(iter(src.discover(ctx))), first.cursor, ctx, budget=10_000, final=False)
    assert again.read_bytes == f.stat().st_size == again.cursor.offset


def _symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("심볼릭 링크를 만들 수 없는 환경")


def test_discover_skips_file_links_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(_line(1))
    (root / "own.jsonl").write_bytes(_line(2))
    _symlink(root / "leak.jsonl", outside)
    src, ctx = _Src(), _ctx(root)
    assert [r.ref for r in src.discover(ctx)] == ["own.jsonl"]
    assert src.resolve("leak.jsonl", ctx) is None
    res = src.read(SourceRef(ref="leak.jsonl"), Cursor(), ctx, budget=1000, final=True)
    assert res.records == []


def test_discover_dedupes_links_to_same_file_inside_root(tmp_path: Path) -> None:
    (tmp_path / "real.jsonl").write_bytes(_line(1))
    _symlink(tmp_path / "a-latest.jsonl", tmp_path / "real.jsonl")
    (tmp_path / "other.jsonl").write_bytes(_line(2))
    _symlink(tmp_path / "b-alias.jsonl", tmp_path / "other.jsonl")
    src, ctx = _Src(), _ctx(tmp_path)
    assert sorted(r.ref for r in src.discover(ctx)) == ["other.jsonl", "real.jsonl"]


def test_resolve_rejects_folder_link_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "x.jsonl").write_bytes(_line(1))
    _symlink(root / "dir", tmp_path / "out")
    src, ctx = _Src(), _ctx(root)
    assert list(src.discover(ctx)) == []  # 폴더 링크는 따라가지 않는다
    assert src.resolve("dir/x.jsonl", ctx) is None


def test_shrunk_file_with_same_first_line_keeps_generation(tmp_path: Path) -> None:
    # 같은 파일이 잘린 경우(첫 줄 같음): 세대 유지 → 같은 내용 줄은 identity로 중복 0
    f = tmp_path / "s.jsonl"
    f.write_bytes(_line(1) + _line(2) + _line(3))
    src, ctx = _Src(), _ctx(tmp_path)
    first = src.read(next(iter(src.discover(ctx))), Cursor(), ctx, budget=1000, final=False)
    f.write_bytes(_line(1))
    again = src.read(next(iter(src.discover(ctx))), first.cursor, ctx, budget=1000, final=False)
    assert [(r.data["i"], r.generation, r.offset) for r in again.records] == [(1, 0, 0)]


def test_shrunk_file_with_new_content_bumps_generation(tmp_path: Path) -> None:
    f = tmp_path / "s.jsonl"
    f.write_bytes(_line(1) + _line(2) + _line(3))
    src, ctx = _Src(), _ctx(tmp_path)
    first = src.read(next(iter(src.discover(ctx))), Cursor(), ctx, budget=1000, final=False)
    f.write_bytes(_line(8) + _line(9))  # 더 작은 새 파일(첫 줄 다름)
    again = src.read(next(iter(src.discover(ctx))), first.cursor, ctx, budget=1000, final=False)
    assert [(r.data["i"], r.generation) for r in again.records] == [(8, 1), (9, 1)]
    f.write_bytes(b"")  # 첫 줄보다 짧음 = 확인 불가 → 새 내용으로 본다
    empty = src.read(next(iter(src.discover(ctx))), again.cursor, ctx, budget=1000, final=False)
    assert empty.cursor.state["jsonl_generation"] == 2
