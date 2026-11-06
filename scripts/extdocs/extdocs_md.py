"""마크다운 도우미: 코드 펜스·제목·앵커(GitHub 방식)·링크·절·생성 구간 표지.

순수 함수만 있다(파일을 읽지 않는다).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

FENCE_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
REF_DEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$")
INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")
HTML_ANCHOR_RE = re.compile(r"<a\s+(?:[^>]*\s)?(?:id|name)=\"([^\"]+)\"", re.IGNORECASE)
FACTS_START = "<!-- extdocs:facts {slug} -->"
FACTS_END = "<!-- /extdocs:facts -->"
FACTS_RE = re.compile(
    r"<!-- extdocs:facts (?P<slug>[a-z0-9-]+) -->\n(?P<body>.*?)<!-- /extdocs:facts -->",
    re.DOTALL,
)
TODO_MARK = "extdocs:todo"


@dataclass(frozen=True)
class Line:
    number: int  # 1부터
    text: str
    in_fence: bool


def lines(text: str) -> Iterator[Line]:
    """줄마다 코드 펜스 안인지 알려 준다(펜스 여는·닫는 줄도 펜스 안으로 본다)."""
    fence: str | None = None
    for i, raw in enumerate(text.split("\n"), start=1):
        m = FENCE_RE.match(raw)
        if fence is None and m:
            fence = m.group(2)[0] * len(m.group(2))
            yield Line(i, raw, True)
            continue
        if fence is not None:
            if m and m.group(2).startswith(fence) and not m.group(3).strip():
                fence = None
            yield Line(i, raw, True)
            continue
        yield Line(i, raw, False)


@dataclass(frozen=True)
class Fence:
    info: str
    body: str
    line: int  # 여는 줄 번호


def fences(text: str) -> list[Fence]:
    """코드 펜스 목록(정보 문자열·본문·여는 줄)."""
    out: list[Fence] = []
    src = text.split("\n")
    i = 0
    while i < len(src):
        m = FENCE_RE.match(src[i])
        if not m:
            i += 1
            continue
        marker = m.group(2)
        info = m.group(3).strip()
        start = i + 1
        body: list[str] = []
        i += 1
        while i < len(src):
            close = FENCE_RE.match(src[i])
            if (
                close
                and close.group(2).startswith(marker[0] * len(marker))
                and not close.group(3).strip()
            ):
                break
            body.append(src[i])
            i += 1
        out.append(Fence(info, "\n".join(body) + ("\n" if body else ""), start))
        i += 1
    return out


def strip_inline(text: str) -> str:
    """제목 글자에서 인라인 꾸밈(코드 따옴표·강조·링크)을 벗긴다."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("`", "").replace("*", "").replace("~~", "")


def github_slug(text: str) -> str:
    """GitHub 제목 앵커(소문자, 글자·숫자·밑줄·하이픈·공백만 남기고 공백 → 하이픈)."""
    plain = strip_inline(text).strip().lower()
    plain = re.sub(r"[^\w\- ]", "", plain)
    return plain.replace(" ", "-")


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    anchor: str
    line: int


def headings(text: str) -> list[Heading]:
    """펜스 밖 ATX 제목 목록. 같은 앵커가 거듭되면 ``-1``·``-2``를 붙인다(GitHub과 같다)."""
    seen: dict[str, int] = {}
    out: list[Heading] = []
    for ln in lines(text):
        if ln.in_fence:
            continue
        m = HEADING_RE.match(ln.text)
        if not m:
            continue
        base = github_slug(m.group(2))
        count = seen.get(base, 0)
        seen[base] = count + 1
        anchor = base if count == 0 else f"{base}-{count}"
        out.append(Heading(len(m.group(1)), m.group(2), anchor, ln.number))
    return out


def anchors(text: str) -> set[str]:
    """제목 앵커 + ``<a id|name="...">`` 앵커."""
    found = {h.anchor for h in headings(text)}
    for ln in lines(text):
        if not ln.in_fence:
            found.update(HTML_ANCHOR_RE.findall(ln.text))
    return found


@dataclass(frozen=True)
class Link:
    target: str
    line: int


def links(text: str) -> list[Link]:
    """펜스·인라인 코드 밖의 링크·이미지·참조 정의 대상."""
    out: list[Link] = []
    for ln in lines(text):
        if ln.in_fence:
            continue
        plain = INLINE_CODE_RE.sub("", ln.text)
        for regex in (LINK_RE, IMAGE_RE):
            out.extend(Link(t, ln.number) for t in regex.findall(plain))
        m = REF_DEF_RE.match(plain)
        if m:
            out.append(Link(m.group(1), ln.number))
    return out


def section_span(text: str, anchor: str) -> tuple[int, int] | None:
    """앵커 제목 절의 줄 범위 [시작, 끝)(0부터, 제목 줄 포함). 다음 같은·높은 제목 앞까지."""
    hs = headings(text)
    for i, h in enumerate(hs):
        if h.anchor != anchor:
            continue
        end = len(text.split("\n"))
        for later in hs[i + 1 :]:
            if later.level <= h.level:
                end = later.line - 1
                break
        return h.line - 1, end
    return None


def section_text(text: str, anchor: str) -> str | None:
    span = section_span(text, anchor)
    if span is None:
        return None
    return "\n".join(text.split("\n")[span[0] : span[1]])


def hand_text(section: str) -> str:
    """절에서 손으로 쓴 글만 남긴다(제목 줄·생성 구간·HTML 주석·빈 줄 제외)."""
    body = FACTS_RE.sub("", section)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    kept = [line for line in body.split("\n")[1:] if line.strip() and not HEADING_RE.match(line)]
    return "\n".join(kept).strip()


def facts_block(slug: str, body: str) -> str:
    """생성 구간 하나(표지 포함, 본문 끝 줄바꿈 보장)."""
    if body and not body.endswith("\n"):
        body += "\n"
    return f"{FACTS_START.format(slug=slug)}\n{body}{FACTS_END}"


def facts_slugs(text: str) -> list[str]:
    return [m.group("slug") for m in FACTS_RE.finditer(text)]


def replace_facts(text: str, render: dict[str, str]) -> str:
    """``render``에 있는 slug의 생성 구간 본문을 바꾼다(없는 slug는 그대로 둔다)."""

    def sub(m: re.Match[str]) -> str:
        slug = m.group("slug")
        if slug not in render:
            return m.group(0)
        return facts_block(slug, render[slug])

    return FACTS_RE.sub(sub, text)


__all__ = [
    "FACTS_END",
    "FACTS_RE",
    "FACTS_START",
    "TODO_MARK",
    "Fence",
    "Heading",
    "Line",
    "Link",
    "anchors",
    "facts_block",
    "facts_slugs",
    "fences",
    "github_slug",
    "hand_text",
    "headings",
    "lines",
    "links",
    "replace_facts",
    "section_span",
    "section_text",
    "strip_inline",
]
