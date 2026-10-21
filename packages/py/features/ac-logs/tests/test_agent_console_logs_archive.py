"""오프라인 보관본(작업 4R.14): 필터 범위·크기 한도·가림·이스케이프·스크립트 없는 HTML."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.logs import LogArchive, LogCategory, LogTaxonomy
from agent_console_logs import (
    ARCHIVE_VERSION,
    AgentInfo,
    IndexBatch,
    IndexRecord,
    LogFilter,
    LogIndex,
    QueryContext,
    build_archive,
    escape_html,
    filter_to_params,
    parse_log_filter,
    render_archive,
)
from agent_console_logs.sqlite import open_log_index
from agent_console_logs.testing import MemoryLogIndex, make_record

CTX = QueryContext(error_categories=frozenset({"oops"}), tz=UTC)
TAXONOMY = LogTaxonomy(
    categories={
        "oops": LogCategory(label="문제", tone="danger", color="#ff0000"),
        "talk": LogCategory(label="대화", color="red;}body{display:none"),
    },
    order=["talk", "oops"],
)


@pytest.fixture(params=["memory", "sqlite"])
def index(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[LogIndex]:
    if request.param == "memory":
        yield MemoryLogIndex()
        return
    found = open_log_index(tmp_path / "logs.sqlite3")
    yield found
    found.close()


def _write(index: LogIndex, *records: IndexRecord) -> None:
    index.write(IndexBatch(records=list(records)))


def _rec(category: str, **kw: Any) -> IndexRecord:
    return make_record(category, **kw)


# ---------------------------------------------------------------- build_archive


def test_filter_scope_sessions_lanes_and_links(index: LogIndex) -> None:
    _write(
        index,
        _rec("talk", title="a1", session="A", thread="main", call_id="c1", time=10.0),
        _rec(
            "oops",
            title="a2",
            session="A",
            thread="sub",
            call_id="c1",
            time=11.0,
            agent=AgentInfo(id="sub", label="도우미", parent_id="main"),
        ),
        _rec("talk", title="b1", session="B", thread="other", time=12.0),
        _rec("oops", title="b2", session="B", thread="other", call_id="c1", time=13.0),
    )
    flt = parse_log_filter({"session": "A"})
    archive = build_archive(index, flt, CTX, exported_at=99.0, taxonomy=TAXONOMY)
    assert archive.version == ARCHIVE_VERSION == 1
    assert archive.exported_at == 99.0
    assert [e.title for e in archive.events] == ["a1", "a2"]
    assert [s.session for s in archive.sessions] == ["A"]
    assert archive.sessions[0].events == 2
    assert archive.sessions[0].errors == 1
    assert {lane.id for lane in archive.lanes} == {"main", "sub"}
    assert next(lane for lane in archive.lanes if lane.id == "sub").label == "도우미"
    # 근거 연결은 보관본 안의 이벤트끼리만(B의 같은 call_id는 범위 밖)
    a1, a2 = archive.events
    assert [link.uid for link in archive.evidence_links[a1.uid]] == [a2.uid]
    assert archive.filter == {"session": ["A"]}
    assert archive.taxonomy == TAXONOMY
    assert not archive.truncated

    by_category = build_archive(index, LogFilter(category=("oops",)), CTX, exported_at=0.0)
    assert [e.title for e in by_category.events] == ["a2", "b2"]
    assert by_category.sessions[0].events == 1  # 세션 요약도 필터 범위
    newest_first = build_archive(index, LogFilter(order="desc"), CTX, exported_at=0.0)
    assert [e.title for e in newest_first.events] == ["b2", "b1", "a2", "a1"]
    nothing = build_archive(index, LogFilter(session=("none",)), CTX, exported_at=0.0)
    assert (nothing.events, nothing.sessions, nothing.truncated) == ([], [], False)


def test_pages_past_page_size_and_ignores_limit_cursor(index: LogIndex) -> None:
    _write(index, *[_rec("talk", title=f"e{i}", session="S", time=float(i)) for i in range(450)])
    archive = build_archive(index, LogFilter(limit=3, cursor="2"), CTX, exported_at=0.0)
    assert len(archive.events) == 450
    assert not archive.truncated
    assert "limit" not in archive.filter
    assert "cursor" not in archive.filter


def test_size_limits_truncate(index: LogIndex) -> None:
    _write(
        index,
        *[_rec("talk", title=f"e{i}", session="S", detail="x" * 1000) for i in range(30)],
    )
    exact = build_archive(index, LogFilter(), CTX, exported_at=0.0, max_events=30)
    assert len(exact.events) == 30
    assert not exact.truncated
    by_count = build_archive(index, LogFilter(), CTX, exported_at=0.0, max_events=7)
    assert len(by_count.events) == 7
    assert by_count.truncated
    one = len(by_count.events[0].model_dump_json(by_alias=True).encode())
    by_bytes = build_archive(index, LogFilter(), CTX, exported_at=0.0, max_bytes=one * 5 + 10)
    assert len(by_bytes.events) == 5
    assert by_bytes.truncated
    with pytest.raises(ValueError, match="max_events"):
        build_archive(index, LogFilter(), CTX, exported_at=0.0, max_events=0)


def test_detail_included_clipped_or_skipped(index: LogIndex) -> None:
    _write(index, _rec("talk", title="t", session="S", detail={"k": "v" * 500}, raw={"r": 1}))
    full = build_archive(index, LogFilter(), CTX, exported_at=0.0)
    assert full.events[0].detail == {"k": "v" * 500}
    assert full.events[0].raw == {"r": 1}
    assert full.events[0].seq == 1
    clipped = build_archive(index, LogFilter(), CTX, exported_at=0.0, max_detail_bytes=50)
    assert isinstance(clipped.events[0].detail, str)
    assert len(clipped.events[0].detail.encode()) <= 50
    bare = build_archive(index, LogFilter(), CTX, exported_at=0.0, with_detail=False)
    assert bare.events[0].detail is None
    assert bare.events[0].summary


def test_redact_applies_to_text_body_session_title_and_filter(index: LogIndex) -> None:
    secret = "sk-archive-secret"
    _write(
        index,
        _rec(
            "talk",
            title=f"제목 {secret}",
            session="S",
            detail={"key": secret},
            raw=[secret],
            tags=("session_title",),
        ),
    )

    def redact(value: Any) -> Any:
        if isinstance(value, str):
            return value.replace(secret, "***")
        if isinstance(value, dict):
            return {k: redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [redact(v) for v in value]
        return value

    archive = build_archive(index, LogFilter(q="제목"), CTX, exported_at=0.0, redact=redact)
    dumped = archive.model_dump_json()
    assert secret not in dumped
    assert archive.events[0].title == "제목 ***"
    assert archive.events[0].detail == {"key": "***"}
    plain = build_archive(index, LogFilter(), CTX, exported_at=0.0)
    assert secret in plain.model_dump_json()
    assert secret not in render_archive(archive)


def test_filter_to_params_round_trips() -> None:
    flt = parse_log_filter({"category": "a,b", "since": "5", "q": "x", "from": "m", "limit": "9"})
    params = filter_to_params(flt)
    assert params == {"category": ["a", "b"], "from": ["m"], "since": 5.0, "q": "x"}
    assert parse_log_filter(params) == flt.with_(limit=LogFilter().limit)


def test_archive_json_round_trips(index: LogIndex) -> None:
    _write(index, _rec("talk", title="안녕", session="S", detail="\u2028"))
    archive = build_archive(index, LogFilter(), CTX, exported_at=1.0, taxonomy=TAXONOMY)
    again = LogArchive.model_validate_json(archive.model_dump_json(by_alias=True))
    assert again == archive


# ---------------------------------------------------------------- render_archive


def _archive(**kw: Any) -> LogArchive:
    index = MemoryLogIndex()
    records = kw.pop("records", None) or [
        _rec("talk", title="첫 요청", session="S", thread="main", time=1_760_000_000.0),
        _rec("oops", title="실패", session="S", thread="main", time=1_760_000_001.0),
    ]
    _write(index, *records)
    return build_archive(
        index, LogFilter(), CTX, exported_at=1_760_000_100.0, taxonomy=TAXONOMY, **kw
    )


def test_html_rules_charset_fonts_wrapping_no_script() -> None:
    page = render_archive(_archive())
    assert page.startswith("<!DOCTYPE html>")
    assert '<meta charset="UTF-8">' in page
    assert '<html lang="ko">' in page
    fonts = "'Pretendard', 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', system-ui"
    assert f"{fonts}, sans-serif" in page
    assert "word-break: keep-all" in page
    assert "overflow-wrap: break-word" in page
    assert "<script" not in page.lower()
    assert "Content-Security-Policy" in page
    assert "default-src 'none'" in page
    # 외부 자원 없음(네트워크 없이 열림)
    assert not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//""", page)
    assert "url(" not in page
    sizes = [int(px) for px in re.findall(r"font-size:\s*(\d+)px", page)]
    assert sizes
    assert min(sizes) >= 12


def test_html_shows_taxonomy_labels_tone_and_safe_color() -> None:
    page = render_archive(_archive())
    assert ">대화</span>" in page
    assert ">문제</span>" in page
    assert 'class="badge tone-danger"' in page
    assert "border-left-color: #ff0000" in page
    assert "display:none" not in page  # 색 값이 CSS 주입이면 버린다
    assert 'class="event is-danger"' in page  # 오류 표시는 tone == danger 범주(F-25)
    assert "LogArchive v1" in page
    assert '<a href="#s-0">S</a>' in page  # 세션 표 → 이벤트 묶음 앵커


def test_html_escapes_markup_separators_and_controls() -> None:
    nasty = '</span><script>alert(1)</script><img src=x onerror="y">'
    archive = _archive(
        records=[
            _rec("<b>cat</b>", title=nasty, session='S"<', detail={"t": "a\u2028b\u2029c\x00d"}),
        ]
    )
    page = render_archive(archive, title="<i>제목</i>")
    assert "<script" not in page.lower()
    assert "<img" not in page.lower()
    assert "<b>" not in page
    assert "&lt;/span&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "&lt;i&gt;제목&lt;/i&gt;" in page
    assert "\u2028" not in page
    assert "\u2029" not in page
    assert "\x00" not in page
    assert "&#x2028;" in page
    assert "&#x2029;" in page
    assert escape_html("a\u2028<\x07") == "a&#x2028;&lt;\ufffd"


def test_html_folds_long_values() -> None:
    long_detail = "가" * 5000
    archive = _archive(records=[_rec("talk", title="긴 값", session="S", detail=long_detail)])
    page = render_archive(archive)
    # 요약이 접기 기준보다 길면 <details>, 본문·원문은 항상 <details>
    assert '<details class="summary"><summary>' in page
    assert "<details><summary>본문</summary><pre>" in page
    assert long_detail in page


def test_html_truncated_notice_empty_archive_and_timezone() -> None:
    truncated = render_archive(_archive(max_events=1))
    assert 'class="notice"' in truncated
    empty = render_archive(LogArchive(exported_at=0.0))
    assert "필터에 맞는 이벤트가 없습니다" in empty
    assert 'class="notice"' not in empty
    assert "1970-01-01 00:00:00.000+00:00" in empty
    kst = render_archive(LogArchive(exported_at=0.0), tz=timezone(timedelta(hours=9)))
    assert "1970-01-01 09:00:00.000+09:00" in kst
