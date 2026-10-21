"""보관본 HTML(스크립트 없음, design §4R.10·F-13).

agent_bench `render_archive`는 웹 JS·CSS와 데이터(`<script>`)를 박아 넣었다. 여기서는 데이터를
HTML로 바로 그려 스크립트 없이 네트워크 없이 연다(`Content-Security-Policy`로 스크립트·외부 자원
차단).
데이터는 모두 이스케이프한다(`<`·`>`·`&`·따옴표, U+2028·U+2029는 숫자 참조, 제어 문자는 U+FFFD).
범주 이름·색·강조(`tone`)는 보관본의 분류 체계 데이터에서 온다(범주 id를 모른다).
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime, tzinfo
from typing import Any

from agent_console_contracts.logs import (
    LogArchive,
    LogCategory,
    LogEvent,
    LogEvidenceLink,
    LogSessionSummary,
)

from ._taxonomy import error_categories
from ._values import scrub_surrogates

__all__ = ["DEFAULT_ARCHIVE_TITLE", "FOLD_CHARS", "escape_html", "render_archive"]

DEFAULT_ARCHIVE_TITLE = "Agent Console 로그 보관본"
"""`render_archive` 기본 제목."""

FOLD_CHARS = 160
"""이보다 긴 요약은 접어서 보인다(`<details>`)."""

_FONT = (
    "'Pretendard', 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', system-ui, sans-serif"
)
_MONO = "ui-monospace, 'Cascadia Mono', 'D2Coding', Consolas, 'Noto Sans Mono', monospace"

_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SAFE_COLOR = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,40})$")
_CLASS_CHARS = re.compile(r"[^a-z0-9_-]")

_CSS = f"""
:root {{ color-scheme: light; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 24px; font-family: {_FONT}; font-size: 14px; line-height: 1.55;
  color: #111827; background: #f9fafb; word-break: keep-all; overflow-wrap: break-word; }}
h1 {{ font-size: 22px; margin: 0 0 12px; }}
h2 {{ font-size: 18px; margin: 28px 0 10px; }}
h3 {{ font-size: 16px; margin: 20px 0 8px; }}
a {{ color: #1d4ed8; }}
.meta {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 0; }}
.meta dt {{ color: #4b5563; }}
.meta dd {{ margin: 0; }}
.notice {{ margin: 12px 0; padding: 10px 12px; border: 1px solid #f59e0b; background: #fffbeb;
  border-radius: 6px; }}
.table-wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; background: #fff; font-size: 13px; }}
th, td {{ border: 1px solid #e5e7eb; padding: 6px 8px; text-align: left; vertical-align: top; }}
th {{ background: #f3f4f6; white-space: nowrap; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 0; margin: 0; list-style: none; }}
.badge {{ display: inline-block; max-width: 100%; padding: 1px 8px; border: 1px solid #9ca3af;
  border-left-width: 4px; border-radius: 4px; background: #fff; font-size: 12px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; vertical-align: middle; }}
.tone-danger {{ border-color: #dc2626; color: #991b1b; background: #fef2f2; }}
.tone-warning {{ border-color: #d97706; color: #92400e; background: #fffbeb; }}
.tone-success {{ border-color: #16a34a; color: #166534; background: #f0fdf4; }}
.tone-info {{ border-color: #2563eb; color: #1e40af; background: #eff6ff; }}
.tone-neutral {{ border-color: #9ca3af; color: #374151; }}
ol.events {{ list-style: none; padding: 0; margin: 0; }}
li.event {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px 12px;
  margin: 0 0 8px; }}
li.event.is-danger {{ border-color: #fca5a5; }}
li.event:target {{ outline: 2px solid #2563eb; }}
.ev-head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; }}
.ev-head .time, .ev-head .seq {{ color: #4b5563; font-size: 12px; font-variant-numeric:
  tabular-nums; white-space: nowrap; }}
.ev-head .lane, .ev-head .stage {{ color: #374151; font-size: 12px; }}
.ev-title {{ font-weight: 600; }}
.summary {{ margin: 4px 0 0; white-space: pre-wrap; }}
.fields {{ display: grid; grid-template-columns: max-content 1fr; gap: 2px 12px; margin: 6px 0 0;
  font-size: 12px; }}
.fields dt {{ color: #4b5563; }}
.fields dd {{ margin: 0; }}
details {{ margin: 6px 0 0; }}
summary {{ cursor: pointer; color: #1f2937; font-size: 13px; }}
pre {{ margin: 6px 0 0; padding: 8px; background: #f3f4f6; border-radius: 4px; font-family: {_MONO};
  font-size: 12px; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 480px;
  overflow: auto; }}
.links {{ margin: 6px 0 0; font-size: 12px; }}
.muted {{ color: #6b7280; }}
footer {{ margin-top: 32px; color: #6b7280; font-size: 12px; }}
"""


def escape_html(value: object) -> str:
    """HTML 본문·속성값 이스케이프(`&<>"'`, U+2028·U+2029 → 숫자 참조, 제어 문자·외톨이 서로게이트 →
    U+FFFD)."""
    text = scrub_surrogates(value if isinstance(value, str) else str(value))
    text = _CONTROL.sub("\ufffd", text)
    return html.escape(text, quote=True).replace("\u2028", "&#x2028;").replace("\u2029", "&#x2029;")


def _time(value: float | None, tz: tzinfo) -> str:
    if value is None:
        return "-"
    try:
        return datetime.fromtimestamp(value, tz).isoformat(sep=" ", timespec="milliseconds")
    except (OverflowError, OSError, ValueError):
        return str(value)


def _json(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _tone_class(tone: str | None) -> str:
    if not tone:
        return ""
    cleaned = _CLASS_CHARS.sub("", tone.lower())
    return f"tone-{cleaned}" if cleaned else ""


class _Page:
    """분류 체계·줄 표시 정보를 들고 조각을 그린다."""

    def __init__(self, archive: LogArchive, tz: tzinfo) -> None:
        self.archive = archive
        self.tz = tz
        self.categories: dict[str, LogCategory] = dict(archive.taxonomy.categories)
        self.lanes = {lane.id: lane for lane in archive.lanes}
        self.uids = {e.uid for e in archive.events}
        self.danger = error_categories(archive.taxonomy)

    # ------------------------------------------------------------ 조각

    def badge(self, category: str) -> str:
        info = self.categories.get(category)
        label = (info.label if info and info.label else None) or category
        classes = " ".join(c for c in ("badge", _tone_class(info.tone if info else None)) if c)
        style = ""
        if info and info.color and _SAFE_COLOR.match(info.color):
            style = f' style="border-left-color: {escape_html(info.color)}"'
        title = (
            escape_html(info.description) if info and info.description else escape_html(category)
        )
        return f'<span class="{classes}"{style} title="{title}">{escape_html(label)}</span>'

    def lane_label(self, lane_id: str) -> str:
        lane = self.lanes.get(lane_id)
        return (lane.label if lane and lane.label else None) or lane_id

    def folded(self, text: str, *, css: str) -> str:
        if len(text) <= FOLD_CHARS:
            return f'<p class="{css}">{escape_html(text)}</p>'
        head = escape_html(text[:FOLD_CHARS]) + "…"
        return (
            f'<details class="{css}"><summary>{head}</summary>'
            f'<p class="{css}">{escape_html(text)}</p></details>'
        )

    def is_danger(self, category: str) -> bool:
        return category in self.danger

    # ------------------------------------------------------------ 영역

    def header(self, title: str) -> str:
        a = self.archive
        rows = [
            ("내보낸 시각", _time(a.exported_at, self.tz)),
            ("형식", f"LogArchive v{a.version}"),
            ("이벤트", f"{len(a.events)}개"),
            ("세션", f"{len(a.sessions)}개"),
        ]
        meta = "".join(f"<dt>{escape_html(k)}</dt><dd>{escape_html(v)}</dd>" for k, v in rows)
        flt = (
            ", ".join(f"{k}={_json(v)}" for k, v in sorted(a.filter.items()))
            if a.filter
            else "(전체)"
        )
        meta += f"<dt>필터</dt><dd>{escape_html(flt)}</dd>"
        notice = (
            '<p class="notice" role="note">보관본 크기 한도에 걸려 앞부분만 담았습니다. '
            "필터를 좁혀 다시 내보내면 나머지를 볼 수 있습니다.</p>"
            if a.truncated
            else ""
        )
        return f"<header><h1>{escape_html(title)}</h1><dl class='meta'>{meta}</dl>{notice}</header>"

    def legend(self) -> str:
        used = list(dict.fromkeys(e.category for e in self.archive.events))
        if not used:
            return ""
        order = self.archive.taxonomy.order or []
        rank = {c: i for i, c in enumerate(order)}
        used.sort(key=lambda c: (rank.get(c, len(rank)), c))
        items = "".join(f"<li>{self.badge(c)}</li>" for c in used)
        return (
            '<section aria-labelledby="h-legend"><h2 id="h-legend">범주</h2>'
            f'<ul class="legend">{items}</ul></section>'
        )

    def sessions_table(self, anchors: dict[str, str]) -> str:
        sessions = self.archive.sessions
        if not sessions:
            return ""
        head = "".join(
            f"<th scope='col'>{h}</th>"
            for h in (
                "세션",
                "제목",
                "프로젝트",
                "처음",
                "마지막",
                "이벤트",
                "오류",
                "줄",
                "모델",
                "토큰",
            )
        )
        body = "".join(self.session_row(s, anchors) for s in sessions)
        return (
            '<section aria-labelledby="h-sessions"><h2 id="h-sessions">세션</h2>'
            f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></div></section>"
        )

    def session_row(self, s: LogSessionSummary, anchors: dict[str, str]) -> str:
        anchor = anchors.get(s.session)
        name = escape_html(s.session)
        link = f'<a href="#{anchor}">{name}</a>' if anchor else name
        project = s.project.label or s.project.id if s.project else ""
        tokens = s.tokens.total if s.tokens and s.tokens.total is not None else None
        cells = [
            link,
            escape_html(s.title),
            escape_html(project),
            escape_html(_time(s.first_time, self.tz)),
            escape_html(_time(s.last_time, self.tz)),
        ]
        nums = [s.events, s.errors, s.thread_count]
        return (
            "<tr>"
            + "".join(f"<td>{c}</td>" for c in cells)
            + "".join(f'<td class="num">{n}</td>' for n in nums)
            + f"<td>{escape_html(', '.join(s.models))}</td>"
            + f'<td class="num">{"-" if tokens is None else tokens}</td>'
            + "</tr>"
        )

    def fields(self, e: LogEvent) -> str:
        pairs: list[tuple[str, str]] = []

        def add(name: str, value: object) -> None:
            if value not in (None, "", [], {}):
                pairs.append((name, value if isinstance(value, str) else _json(value)))

        add("출처", f"{e.source}" + (f" · {e.ref}" if e.ref else ""))
        add("행위자", e.actor)
        add("보낸 쪽", ", ".join(e.from_))
        add("받는 쪽", ", ".join(e.to))
        add("전달 수단", e.via)
        add("도구", e.tool)
        add("호출 id", e.call_id)
        add("응답 id", e.message_id)
        add("모델", e.model)
        add("상태", e.status)
        add("소요 시간", f"{e.duration_ms:.0f} ms" if e.duration_ms is not None else None)
        add("실행", e.run_id)
        add("노드", "/".join(e.node_path))
        add("작업 폴더", e.cwd)
        add("태그", ", ".join(e.tags))
        add("문서", ", ".join(f"{d.path} ({d.kind}, {d.action})" for d in e.documents))
        add("근거", e.evidence)
        if not pairs:
            return ""
        inner = "".join(f"<dt>{escape_html(k)}</dt><dd>{escape_html(v)}</dd>" for k, v in pairs)
        return f'<details><summary>필드</summary><dl class="fields">{inner}</dl></details>'

    def links(self, uid: str) -> str:
        found: list[LogEvidenceLink] = self.archive.evidence_links.get(uid, [])
        if not found:
            return ""
        parts = []
        for link in found:
            label = escape_html(link.title or link.uid)
            basis = escape_html(f"{link.basis}={link.value}")
            target = (
                f'<a href="#ev-{escape_html(link.uid)}">{label}</a>'
                if link.uid in self.uids
                else f'<span class="muted">{label}</span>'
            )
            parts.append(f"{target} <span class='muted'>({basis})</span>")
        return f'<p class="links">연결: {", ".join(parts)}</p>'

    def event(self, e: LogEvent) -> str:
        danger = " is-danger" if self.is_danger(e.category) else ""
        when = _time(e.time if e.time is not None else e.observed_at, self.tz)
        head = (
            f'<span class="time">{escape_html(when)}</span>'
            f'<span class="seq">#{e.seq}</span>'
            f"{self.badge(e.category)}"
            + (f'<span class="stage">{escape_html(e.stage)}</span>' if e.stage else "")
            + (
                f'<span class="lane">{escape_html(self.lane_label(e.thread))}</span>'
                if e.thread
                else ""
            )
            + f'<span class="ev-title">{escape_html(e.title or e.category)}</span>'
        )
        parts = [f'<div class="ev-head">{head}</div>']
        if e.summary:
            parts.append(self.folded(e.summary, css="summary"))
        parts.append(self.fields(e))
        for name, label in (("detail", "본문"), ("raw", "원문")):
            value = getattr(e, name)
            if value is not None:
                parts.append(
                    f"<details><summary>{label}</summary><pre>{escape_html(_json(value))}</pre></details>"
                )
        parts.append(self.links(e.uid))
        return f'<li class="event{danger}" id="ev-{escape_html(e.uid)}">{"".join(parts)}</li>'

    def groups(self) -> tuple[str, dict[str, str]]:
        """세션별 이벤트 묶음(보관본 순서 유지, 세션 없는 이벤트는 마지막 묶음)."""
        grouped: dict[str, list[LogEvent]] = {}
        for e in self.archive.events:
            grouped.setdefault(e.session, []).append(e)
        titles = {s.session: s.title for s in self.archive.sessions}
        anchors: dict[str, str] = {}
        out = []
        for i, (session, events) in enumerate(grouped.items()):
            anchor = f"s-{i}"
            if session:
                anchors[session] = anchor
            name = session or "(세션 없음)"
            title = titles.get(session) or ""
            heading = escape_html(name) + (
                f' <span class="muted">— {escape_html(title)}</span>' if title else ""
            )
            items = "".join(self.event(e) for e in events)
            out.append(
                f'<section id="{anchor}"><h3>{heading} '
                f'<span class="muted">({len(events)}개)</span></h3>'
                f'<ol class="events">{items}</ol></section>'
            )
        empty = '<p class="muted">필터에 맞는 이벤트가 없습니다.</p>'
        body = "".join(out) if out else empty
        return (
            f'<section aria-labelledby="h-events"><h2 id="h-events">이벤트</h2>{body}</section>',
            anchors,
        )


def _join(parts: Iterable[str]) -> str:
    return "\n".join(p for p in parts if p)


def render_archive(
    archive: LogArchive, *, tz: tzinfo | None = None, title: str = DEFAULT_ARCHIVE_TITLE
) -> str:
    """보관본을 스크립트 없는 HTML 문서 하나로 그린다(네트워크 없이 열림).

    Args:
        archive: `LogArchive` v1(보통 `build_archive` 결과).
        tz: 시각 표시 시간대. None이면 UTC.
        title: 문서 제목.

    Returns:
        UTF-8로 저장할 HTML 문자열(`<meta charset="UTF-8">`, `<script>` 없음).
    """
    page = _Page(archive, tz or UTC)
    events, anchors = page.groups()
    body = _join(
        [
            page.header(title),
            page.legend(),
            page.sessions_table(anchors),
            events,
            "<footer>이 파일은 네트워크 없이 열리는 읽기 전용 보관본입니다. "
            "본문은 색인 사본이며 비밀 의심 값은 가려져 있습니다.</footer>",
        ]
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ko">\n<head>\n<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'; style-src 'unsafe-inline'; img-src data:\">\n"
        '<meta name="referrer" content="no-referrer">\n'
        f"<title>{escape_html(title)}</title>\n<style>{_CSS}</style>\n</head>\n"
        f"<body>\n{body}\n</body>\n</html>\n"
    )
