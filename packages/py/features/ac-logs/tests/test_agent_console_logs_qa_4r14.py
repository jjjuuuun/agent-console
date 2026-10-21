"""QA 4R.14: 보관본 HTML 적대적 입력(모든 필드 주입, 서로게이트, 위험 속성)."""

from __future__ import annotations

from datetime import UTC
from html.parser import HTMLParser

from agent_console_contracts.logs import LogCategory, LogTaxonomy
from agent_console_logs import (
    AgentInfo,
    IndexBatch,
    LogFilter,
    QueryContext,
    build_archive,
    render_archive,
)
from agent_console_logs.testing import MemoryLogIndex, make_record

NASTY = (
    '"><img src=x onerror=alert(1)></style><script>x</script>javascript:alert(1)'
    + chr(0x2028)
    + chr(0x2029)
    + chr(0)
)
CTX = QueryContext(error_categories=frozenset(), tz=UTC)


def _page(color: str = "red;background:url(http://x/y)") -> str:
    tax = LogTaxonomy(
        categories={
            NASTY: LogCategory(label=NASTY, tone=NASTY, color=color, description=NASTY),
            "plain": LogCategory(label="p", tone="danger", color="#abc"),
        },
        order=[NASTY],
    )
    index = MemoryLogIndex()
    rec = make_record(
        NASTY,
        title=NASTY,
        session=NASTY,
        thread=NASTY,
        tool=NASTY,
        call_id=NASTY,
        stage=NASTY,
        model=NASTY,
        cwd=NASTY,
        tags=(NASTY,),
        detail={NASTY: NASTY},
        time=1.0,
        agent=AgentInfo(id=NASTY, label=NASTY, parent_id=None),
    )
    rec2 = make_record("plain", title="b", session="ok", call_id=NASTY, time=2.0)
    index.write(IndexBatch(records=[rec, rec2]))
    archive = build_archive(index, LogFilter(), CTX, exported_at=3.0, taxonomy=tax)
    archive = archive.model_copy(update={"filter": {"q": NASTY, NASTY: [NASTY]}})
    return render_archive(archive, title=NASTY)


class _Collect(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: set[str] = set()
        self.attrs: list[tuple[str, str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.add(tag)
        self.attrs.extend((tag, k, v) for k, v in attrs)


SAFE_TAGS = {
    "html", "head", "meta", "title", "style", "body", "header", "h1", "h2", "h3", "dl", "dt",
    "dd", "p", "section", "ul", "ol", "li", "span", "div", "table", "thead", "tbody", "tr",
    "th", "td", "a", "details", "summary", "pre", "footer",
}  # fmt: skip


def test_hostile_values_produce_inert_html() -> None:
    page = _page()
    low = page.lower()
    c = _Collect()
    c.feed(page)
    assert c.tags <= SAFE_TAGS, c.tags - SAFE_TAGS
    assert not [a for a in c.attrs if a[1].startswith("on")]
    assert not [a for a in c.attrs if a[1] in {"src", "srcset", "action", "formaction"}]
    assert all((v or "").startswith("#") for t, k, v in c.attrs if t == "a" and k == "href")
    assert "url(" not in low
    assert "http://" not in low
    assert "https://" not in low
    assert page.count("</style>") == 1
    assert "\u2028" not in page
    assert "\u2029" not in page
    assert "\x00" not in page


def test_unsafe_color_variants_dropped() -> None:
    for color in ("red;background:url(x)", "#fff;x", "expression(1)", "var(--x)", 'red"onclick="1'):
        c = _Collect()
        c.feed(_page(color))
        styles = [v or "" for _, k, v in c.attrs if k == "style"]
        assert all("#abc" in v for v in styles), (color, styles)


def test_lone_surrogate_renders_and_encodes() -> None:
    index = MemoryLogIndex()
    index.write(
        IndexBatch(records=[make_record("t", title="a\ud800b", session="s\udc00", time=1.0)])
    )
    archive = build_archive(index, LogFilter(), CTX, exported_at=1.0)
    page = render_archive(archive, title="x\ud800")
    page.encode("utf-8")  # 서로게이트가 남으면 응답 인코딩이 500이 된다
