"""페이지 파싱: 원문 → `ParsedPage`(머리말·제목과 그 출처·태그·별칭·제목들·링크 원문 위치).

블록 구조는 markdown-it-py(인라인 파싱 끔)가 정하고, 링크는 인라인 영역(문단·제목) 원문에서만
찾는다. 코드 블록·HTML 블록·인라인 코드 안의 글은 링크가 아니다. 패턴 링크는 문법 데이터
정규식(`ac-safe-regex`), 마크다운 링크는 상대 경로이고 확장자가 페이지 확장자인 인라인 링크다. 링크
대상 해석은 `build_index`가 한다(여기서는 원문만).
"""

from __future__ import annotations

import hashlib
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from markdown_it import MarkdownIt

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import (
    EffectiveWikiSyntax,
    KnownWikiFrontMatterRoles,
    KnownWikiLinkKinds,
    KnownWikiTitleSources,
    WikiHeading,
    WikiIssue,
)
from agent_console_safe_regex import RegexTimeoutError

from ._compiled import CompiledLinkRule, CompiledWikiSyntax, compile_syntax
from ._frontmatter import read_front_matter
from ._inline import InlineScan, scan_inline
from ._paths import split_extension
from ._text import Utf16Map, line_of, line_starts

__all__ = ["PageText", "ParsedLink", "ParsedPage", "decode_page", "parse_page"]

type PageText = str | bytes
"""페이지 원문: 글(str) 또는 UTF-8 바이트."""

_URL_SCHEME = (
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+.-",
)


@dataclass(frozen=True, slots=True)
class ParsedLink:
    """페이지 안 링크 원문 하나(해석 전). 위치는 본문 전체 기준 코드 포인트.

    Attributes:
        start: 링크 원문 시작.
        end: 링크 원문 끝(제외).
        raw: 링크 원문 그대로.
        kind: 링크 규칙 종류(`pattern`·`markdown`).
        rule_id: 찾은 링크 규칙 id.
        resolve: 그 규칙의 대상 찾는 순서.
        target: 링크가 적은 대상(앞뒤 공백 뺌, 마크다운은 `#`·`?` 앞 경로를 퍼센트 풀기).
        label: 링크 글자(패턴 `label` 묶음 → 없으면 대상, 마크다운은 링크 글자 → 비면 대상 원문).
        anchor: 절 이름(`#` 뒤), 없으면 None.
        line: 링크가 시작하는 줄(1부터).
        target_start: 이름 바꾸기에서 바꿀 대상 원문 시작(없으면 None).
        target_end: 그 끝.
    """

    start: int
    end: int
    raw: str
    kind: str
    rule_id: str
    resolve: tuple[str, ...]
    target: str
    label: str
    anchor: str | None
    line: int
    target_start: int | None = None
    target_end: int | None = None


@dataclass(slots=True)
class ParsedPage:
    """페이지 하나를 파싱한 결과(본문은 담지 않는다 — 캐시에 두기 가볍게).

    Attributes:
        path: 페이지 경로(위키 폴더 기준, 확장자 없음).
        title: 문법의 제목 출처 순서로 정한 제목(못 정하면 빈 문자열).
        title_source: 제목을 정한 출처(`front_matter`·`first_heading`·`file_name`, 없으면 None).
        tags: 머리말 태그 역할 값.
        aliases: 머리말 별칭 역할 값.
        front_matter: 읽은 머리말(깨졌으면 빈 객체).
        headings: 제목 목록(줄 순서).
        links: 링크 원문(위치 순).
        issues: 이 페이지 이슈(`wiki.front_matter_invalid`·`wiki.parse_timeout`).
        content_hash: 본문 sha256(16진수, 원문 바이트 기준).
        bytes: 원문 바이트 수.
        utf16: 코드 포인트 → UTF-16 위치 변환.
        body_start: 머리말 뒤 본문 시작 위치.
    """

    path: str
    title: str
    title_source: str | None
    tags: list[str]
    aliases: list[str]
    front_matter: dict[str, Any]
    headings: list[WikiHeading]
    links: list[ParsedLink]
    issues: list[WikiIssue]
    content_hash: str
    bytes: int
    utf16: Utf16Map = field(repr=False)
    body_start: int = 0


class _TimeoutError(Exception):
    pass


class _Deadline:
    __slots__ = ("_clock", "_deadline")

    def __init__(self, clock: Callable[[], float], budget_ms: float | None) -> None:
        self._clock = clock
        self._deadline = None if budget_ms is None else clock() + budget_ms / 1000.0

    def check(self) -> None:
        if self._deadline is not None and self._clock() > self._deadline:
            raise _TimeoutError


@cache
def _markdown() -> MarkdownIt:
    # 블록 구조만: 인라인 파싱을 끄면 열 배쯤 빠르다(인라인 영역은 `scan_inline`이 원문에서 읽는다).
    md = MarkdownIt("commonmark")
    md.disable(["inline", "text_join"], ignoreInvalid=True)
    return md


def decode_page(text: PageText) -> tuple[str, str, int]:
    """원문 → (글, sha256, 바이트 수). 바이트는 UTF-8로 풀고 깨진 바이트는 대체 글자로 읽는다.

    줄바꿈은 바꾸지 않는다(`\\r\\n`이 그대로 남아 위치·이름 바꾸기가 원문 바이트를 지킨다).
    """
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace"), hashlib.sha256(text).hexdigest(), len(text)
    data = text.encode("utf-8", errors="surrogatepass")
    return text, hashlib.sha256(data).hexdigest(), len(data)


def _issue(code: str, message: str, *, severity: str = "warning", **kw: Any) -> WikiIssue:
    return WikiIssue.model_validate({"severity": severity, "code": code, "message": message, **kw})


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in items:
        if item is None or isinstance(item, dict | list):
            continue
        text = str(item).strip()
        if text and text not in out:
            out.append(text)
    return out


def _has_url_scheme(dest: str) -> bool:
    if not dest or dest[0] not in _URL_SCHEME[0]:
        return False
    for i, ch in enumerate(dest[1:], start=1):
        if ch == ":":
            return i >= 1
        if ch not in _URL_SCHEME[1]:
            return False
    return False


def _pattern_links(
    unit: str,
    base: int,
    rule: CompiledLinkRule,
    scan: InlineScan,
    taken: list[tuple[int, int]],
    starts: list[int],
) -> list[ParsedLink]:
    assert rule.pattern is not None
    out: list[ParsedLink] = []
    has_label = "label" in rule.groups
    has_anchor = "anchor" in rule.groups
    excluded = bool(scan.excluded)
    for m in rule.pattern.finditer(unit):
        m_start, m_end = m.start, m.end
        if m_end <= m_start or (excluded and scan.overlaps(m_start, m_end)):
            continue
        if taken and any(s < m_end and m_start < e for s, e in taken):
            continue
        span = m.span("target")
        raw_target = m.group("target") or ""
        target = raw_target.strip()
        if not target or span is None:
            continue
        lead = len(raw_target) - len(raw_target.lstrip())
        t_start = base + span[0] + lead
        label = (m.group("label") or "").strip() if has_label else ""
        anchor = (m.group("anchor") or "").strip() if has_anchor else ""
        out.append(
            ParsedLink(
                start=base + m_start,
                end=base + m_end,
                raw=m.text,
                kind=rule.kind,
                rule_id=rule.id,
                resolve=rule.resolve,
                target=target,
                label=label or target,
                anchor=anchor or None,
                line=line_of(starts, base + m_start),
                target_start=t_start,
                target_end=t_start + len(target),
            )
        )
        taken.append((m_start, m_end))
    return out


def _markdown_links(
    unit: str,
    base: int,
    rule: CompiledLinkRule,
    scan: InlineScan,
    syntax: CompiledWikiSyntax,
    starts: list[int],
) -> list[ParsedLink]:
    out: list[ParsedLink] = []
    for link in scan.links:
        dest = link.dest
        scheme = next((s for s in syntax.schemes if dest.startswith(s.prefix)), None)
        label = link.label.strip()
        if scheme is not None:
            out.append(
                ParsedLink(
                    start=base + link.start,
                    end=base + link.end,
                    raw=unit[link.start : link.end],
                    kind=rule.kind,
                    rule_id=rule.id,
                    resolve=rule.resolve,
                    target=dest,
                    label=label or dest,
                    anchor=None,
                    line=line_of(starts, base + link.start),
                )
            )
            continue
        if not dest or dest[0] in "/#?" or _has_url_scheme(dest):
            continue
        cut = len(dest)
        for mark in "#?":
            at = dest.find(mark)
            if at != -1:
                cut = min(cut, at)
        anchor = dest[dest.find("#") + 1 :] if "#" in dest else None
        raw_path = dest[:cut]
        path = urllib.parse.unquote(raw_path)
        if not path or split_extension(path, syntax.page_extensions) is None:
            continue
        t_start = base + link.dest_start
        out.append(
            ParsedLink(
                start=base + link.start,
                end=base + link.end,
                raw=unit[link.start : link.end],
                kind=rule.kind,
                rule_id=rule.id,
                resolve=rule.resolve,
                target=path,
                label=label or dest,
                anchor=urllib.parse.unquote(anchor) if anchor else None,
                line=line_of(starts, base + link.start),
                target_start=t_start,
                target_end=t_start + len(raw_path),
            )
        )
    return out


def parse_page(
    path: str,
    text: PageText,
    syntax: CompiledWikiSyntax | EffectiveWikiSyntax,
    *,
    timeout_ms: float | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> ParsedPage:
    """페이지 하나를 파싱한다(서버 없이 쓰는 순수 함수).

    Args:
        path: 페이지 경로(위키 폴더 기준, 확장자 없음). 제목 출처 `file_name`이 마지막 구성요소를
            쓴다.
        text: 원문(글 또는 UTF-8 바이트, 머리말 포함).
        syntax: 컴파일한 문법(`compile_syntax`) 또는 유효 문법(부를 때마다 컴파일).
        timeout_ms: 링크 찾기 시간 상한. 넘으면 링크 없이 읽고 `wiki.parse_timeout`.
        clock: 시간 상한에 쓰는 시계(초, 테스트 주입용).

    Returns:
        `ParsedPage`. 링크는 위치 순이고 겹치지 않는다(같은 곳에 여러 규칙이 맞으면 문법 순서의 앞
        규칙, 마크다운 링크 안에는 패턴 링크를 찾지 않는다).
    """
    compiled = syntax if isinstance(syntax, CompiledWikiSyntax) else compile_syntax(syntax)
    content, digest, size = decode_page(text)
    issues: list[WikiIssue] = []
    starts = line_starts(content)

    front = read_front_matter(content, compiled.delimiter)
    if front.error is not None:
        issues.append(
            _issue(
                KnownIssueCodes.WIKI_FRONT_MATTER_INVALID,
                f"{front.error} 본문으로 읽습니다.",
                page=path,
                line=front.error_line,
            )
        )
    body_start = front.body_start
    first_line = front.body_line - 1  # 0부터

    tokens = _markdown().parse(content[body_start:])
    headings: list[WikiHeading] = []
    units: list[tuple[int, int]] = []
    pending_heading: int | None = None
    last = len(starts)
    for token in tokens:
        if token.type == "heading_open":
            pending_heading = int(token.tag[1:]) if token.tag[1:].isdigit() else 1
            continue
        if token.type != "inline" or token.map is None:
            continue
        l0 = first_line + token.map[0]
        l1 = first_line + token.map[1]
        a = starts[l0] if l0 < last else len(content)
        b = starts[l1] if l1 < last else len(content)
        units.append((a, b))
        if pending_heading is not None:
            headings.append(
                WikiHeading(level=pending_heading, text=token.content.strip(), line=l0 + 1)
            )
            pending_heading = None

    roles = compiled.roles
    data = front.data
    tags = (
        _strings(data.get(roles[KnownWikiFrontMatterRoles.TAGS]))
        if KnownWikiFrontMatterRoles.TAGS in roles
        else []
    )
    aliases = (
        _strings(data.get(roles[KnownWikiFrontMatterRoles.ALIASES]))
        if KnownWikiFrontMatterRoles.ALIASES in roles
        else []
    )
    title, title_source = "", None
    for source in compiled.title_sources:
        if source == KnownWikiTitleSources.FRONT_MATTER:
            key = roles.get(KnownWikiFrontMatterRoles.TITLE)
            values = _strings(data.get(key)) if key else []
            if values:
                title, title_source = values[0], source
                break
        elif source == KnownWikiTitleSources.FIRST_HEADING:
            h1 = next((h for h in headings if h.level == 1 and h.text), None)
            if h1 is not None:
                title, title_source = h1.text, source
                break
        elif source == KnownWikiTitleSources.FILE_NAME:
            name = path.rsplit("/", 1)[-1]
            if name:
                title, title_source = name, source
                break

    links: list[ParsedLink] = []
    if compiled.links and units:
        deadline = _Deadline(clock, timeout_ms)
        try:
            for a, b in units:
                deadline.check()
                unit = content[a:b]
                scan = scan_inline(unit)
                taken: list[tuple[int, int]] = []
                found: list[ParsedLink] = []
                for rule in compiled.links:
                    if rule.kind == KnownWikiLinkKinds.PATTERN:
                        found.extend(_pattern_links(unit, a, rule, scan, taken, starts))
                    elif rule.kind == KnownWikiLinkKinds.MARKDOWN and scan.links:
                        md = [
                            link
                            for link in _markdown_links(unit, a, rule, scan, compiled, starts)
                            if not any(s < link.end - a and link.start - a < e for s, e in taken)
                        ]
                        taken.extend((link.start - a, link.end - a) for link in md)
                        found.extend(md)
                found.sort(key=lambda link: link.start)
                links.extend(found)
        except (_TimeoutError, RegexTimeoutError):
            links = []
            issues.append(
                _issue(
                    KnownIssueCodes.WIKI_PARSE_TIMEOUT,
                    "페이지를 읽는 시간이 상한을 넘어 링크 없이 읽었습니다.",
                    page=path,
                    details={"timeout_ms": timeout_ms},
                )
            )

    return ParsedPage(
        path=path,
        title=title,
        title_source=title_source,
        tags=tags,
        aliases=aliases,
        front_matter=data,
        headings=headings,
        links=links,
        issues=issues,
        content_hash=digest,
        bytes=size,
        utf16=Utf16Map(content),
        body_start=body_start,
    )
