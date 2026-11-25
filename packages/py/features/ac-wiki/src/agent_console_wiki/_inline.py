"""인라인 영역(문단·제목 원문 한 덩어리) 훑기: 코드 조각·자동 링크·이미지·마크다운 링크의 원문 위치.

블록 구조(코드 블록·HTML 블록·문단 경계)는 markdown-it-py가 정하고, 인라인 영역 안은 여기서 원문
위치를 그대로 얻는다. markdown-it-py 인라인 토큰은 원문 위치를 주지 않고 전체 인라인 파싱은 블록
파싱보다 열 배쯤 느리다(페이지 2,000개 기준 약 10초 — design §7R.14의 2초를 넘음, `[7R.7 구현]`).
그래서 CommonMark 규칙 중 링크 위치에 필요한 것만 따른다:

- 코드 조각: 백틱 n개로 열고 정확히 n개로 닫는다. 여는 백틱 앞 역슬래시는 그 백틱 하나를 글자로
만든다.
- 자동 링크 `<scheme:…>`: 링크 패턴을 걸지 않는다.
- 인라인 링크 `[글자](대상 "제목")`·이미지 `![…](…)`: 괄호 짝·`<…>` 대상·제목을 읽는다. 링크 안에
  링크는 없다.
- 참조 링크 `[글자][이름]`·`[이름][]`·`[이름]`: 정의(`[이름]: 대상`)가 있는 이름만 링크다(이름
  비교는 CommonMark처럼 앞뒤 공백을 떼고 공백을 하나로, 대소문자 무시). 정의는 블록 파서가 찾아
  넘긴다(`references`). 정의가 없는 이름은 글자 그대로다.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Mapping
from dataclasses import dataclass

from markdown_it.common.utils import normalizeReference

__all__ = ["InlineScan", "LinkReference", "MarkdownLink", "reference_key", "scan_inline"]

_BACKTICKS = re.compile(r"`+")
_AUTOLINK = re.compile(r"<[A-Za-z][A-Za-z0-9+.\-]{1,31}:[^\s<>]*>")
_SPECIAL = re.compile(r"[\[\]\\]")
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)", re.DOTALL)
_SPACE = " \t"
_MAX_LABEL = 999  # CommonMark 참조 이름 최대 글자 수


def reference_key(label: str) -> str:
    """참조 이름 비교 키(CommonMark 규칙 — markdown-it-py `normalizeReference`와 같다).

    >>> reference_key("  Foo   Bar ") == reference_key("foo bar")
    True
    """
    return normalizeReference(label)


@dataclass(frozen=True, slots=True)
class LinkReference:
    """참조 링크 정의(`[이름]: 대상`) 하나. 위치는 부르는 쪽이 정한 기준(파서는 본문 전체 기준).

    Attributes:
        dest: 대상 원문(`<…>`면 괄호 안).
        dest_start: 대상 원문 시작.
        dest_end: 대상 원문 끝.
    """

    dest: str
    dest_start: int
    dest_end: int


@dataclass(frozen=True, slots=True)
class MarkdownLink:
    """마크다운 링크 하나(위치는 훑은 글 기준 코드 포인트).

    Attributes:
        start: `[` 위치.
        end: 링크 원문 끝(인라인은 닫는 `)`, 참조는 마지막 `]` 다음).
        label: 링크 글자 원문(첫 `[`·`]` 안).
        dest: 대상 원문(`<…>`면 괄호 안).
        dest_start: 대상 원문 시작(참조 링크는 정의의 `LinkReference.dest_start` 그대로).
        dest_end: 대상 원문 끝(참조 링크는 정의 기준).
        reference: 참조 링크면 정의 이름 키(`reference_key`), 인라인 링크면 None.
    """

    start: int
    end: int
    label: str
    dest: str
    dest_start: int
    dest_end: int
    reference: str | None = None


@dataclass(slots=True)
class InlineScan:
    """인라인 영역 훑기 결과.

    Attributes:
        excluded: 링크 패턴을 걸지 않을 범위(코드 조각·자동 링크·이미지·마크다운 링크), 시작 순.
        links: 마크다운 링크(인라인·참조, 이미지 제외), 시작 순.
    """

    excluded: list[tuple[int, int]]
    links: list[MarkdownLink]

    def overlaps(self, start: int, end: int) -> bool:
        """`[start, end)`가 제외 범위와 겹치는지."""
        spans = self.excluded
        i = bisect.bisect_right(spans, (start, float("inf"))) - 1
        if i >= 0 and spans[i][1] > start:
            return True
        return i + 1 < len(spans) and spans[i + 1][0] < end


def _escaped(text: str, pos: int) -> bool:
    """`text[pos]` 앞의 역슬래시 수가 홀수인지."""
    n = 0
    i = pos - 1
    while i >= 0 and text[i] == "\\":
        n += 1
        i -= 1
    return n % 2 == 1


def _code_spans(text: str) -> list[tuple[int, int]]:
    if "`" not in text:
        return []
    if "\\`" not in text:
        # 빠른 길: 여는 백틱 묶음과 정확히 같은 길이의 다음 묶음(역슬래시가 없으면
        # `_code_spans_scan`과
        # 같은 결과 — 테스트가 견준다).
        return [m.span() for m in _CODE_SPAN.finditer(text)]
    return _code_spans_scan(text)


def _code_spans_scan(text: str) -> list[tuple[int, int]]:
    """코드 조각 찾기 일반 길(여는 백틱 앞 역슬래시 처리)."""
    runs = [(m.start(), m.end() - m.start()) for m in _BACKTICKS.finditer(text)]
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(runs):
        pos, length = runs[i]
        if _escaped(text, pos):
            pos, length = pos + 1, length - 1
        if length == 0:
            i += 1
            continue
        close = next((j for j in range(i + 1, len(runs)) if runs[j][1] == length), None)
        if close is None:
            i += 1
            continue
        spans.append((pos, runs[close][0] + length))
        i = close + 1
    return spans


def _skip_space(text: str, pos: int, end: int) -> int:
    newline = False
    while pos < end:
        ch = text[pos]
        if ch in _SPACE:
            pos += 1
        elif ch == "\n" and not newline:
            newline = True
            pos += 1
        elif ch == "\r" and not newline:
            newline = True
            pos += 2 if text.startswith("\r\n", pos) else 1
        else:
            break
    return pos


def _destination(text: str, pos: int, end: int) -> tuple[int, int, int] | None:
    """(대상 시작, 대상 끝, 다음 위치). `<…>`면 괄호 안 범위."""
    if pos < end and text[pos] == "<":
        i = pos + 1
        while i < end:
            ch = text[i]
            if ch in "\r\n" or (ch == "<" and not _escaped(text, i)):
                return None
            if ch == ">" and not _escaped(text, i):
                return pos + 1, i, i + 1
            i += 1
        return None
    i = pos
    depth = 0
    while i < end:
        ch = text[i]
        if ch in " \t\r\n" or ord(ch) < 32:
            break
        if ch == "\\" and i + 1 < end:
            i += 2
            continue
        if ch == "(":
            depth += 1
            if depth > 32:
                return None
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
        i += 1
    if depth != 0:
        return None
    return pos, i, i


def _title(text: str, pos: int, end: int) -> int | None:
    """제목 다음 위치(제목이 없으면 `pos`, 틀리면 None)."""
    if pos >= end:
        return pos
    opener = text[pos]
    closer = {'"': '"', "'": "'", "(": ")"}.get(opener)
    if closer is None:
        return pos
    i = pos + 1
    while i < end:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == closer:
            return i + 1
        if opener == "(" and ch == "(":
            return None
        i += 1
    return None


def _inline_link(text: str, paren: int, end: int) -> tuple[int, int, int] | None:
    """`(` 위치에서 인라인 링크 꼬리를 읽는다 → (대상 시작, 대상 끝, 닫는 괄호 다음)."""
    pos = _skip_space(text, paren + 1, end)
    dest = _destination(text, pos, end)
    if dest is None:
        return None
    d_start, d_end, pos = dest
    after_dest = pos
    pos = _skip_space(text, pos, end)
    if pos > after_dest:
        titled = _title(text, pos, end)
        if titled is None:
            return None
        pos = _skip_space(text, titled, end)
    if pos < end and text[pos] == ")":
        return d_start, d_end, pos + 1
    return None


def _label_end(text: str, pos: int, end: int) -> int | None:
    """`text[pos] == "["`인 참조 이름의 닫는 `]` 위치(이름이 틀리면 None)."""
    i = pos + 1
    limit = min(end, pos + 1 + _MAX_LABEL + 1)
    while i < limit:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "[":
            return None
        if ch == "]":
            return i
        i += 1
    return None


def scan_inline(text: str, references: Mapping[str, LinkReference] | None = None) -> InlineScan:
    """인라인 영역 원문을 훑는다(위치는 `text` 기준 코드 포인트).

    Args:
        text: 인라인 영역 원문(문단·제목 하나).
        references: 참조 이름 키(`reference_key`) → 정의. 비었거나 None이면 참조 링크를 읽지 않는다.

    Returns:
        `InlineScan`.

    >>> refs = {reference_key("Docs"): LinkReference("guide.md", 100, 108)}
    >>> [(link.label, link.dest) for link in scan_inline("see [the guide][docs]", refs).links]
    [('the guide', 'guide.md')]
    """
    refs = references or {}
    has_link = "](" in text or (bool(refs) and "]" in text)
    if not has_link and "`" not in text and "<" not in text:
        return InlineScan(excluded=[], links=[])
    code = _code_spans(text)
    excluded: list[tuple[int, int]] = list(code)
    starts = [s for s, _ in code]

    def in_code(pos: int) -> tuple[int, int] | None:
        i = bisect.bisect_right(starts, pos) - 1
        if i >= 0 and code[i][1] > pos:
            return code[i]
        return None

    auto: list[tuple[int, int]] = []
    if "<" in text:
        auto = [
            (m.start(), m.end()) for m in _AUTOLINK.finditer(text) if in_code(m.start()) is None
        ]
        excluded.extend(auto)
    auto_starts = [s for s, _ in auto]

    def skip_to(pos: int) -> int | None:
        span = in_code(pos)
        if span is not None:
            return span[1]
        i = bisect.bisect_right(auto_starts, pos) - 1
        if i >= 0 and auto[i][1] > pos:
            return auto[i][1]
        return None

    links: list[MarkdownLink] = []
    if has_link:
        stack: list[int] = []
        end = len(text)
        i = 0
        while i < end:
            m = _SPECIAL.search(text, i)
            if m is None:
                break
            i = m.start()
            jump = skip_to(i)
            if jump is not None:
                i = jump
                continue
            ch = text[i]
            if ch == "\\":
                i += 2
                continue
            if ch == "[":
                stack.append(i)
            elif ch == "]" and stack:
                opener = stack.pop()
                image = opener > 0 and text[opener - 1] == "!" and not _escaped(text, opener - 1)
                found: MarkdownLink | None = None
                close = -1
                if i + 1 < end and text[i + 1] == "(":
                    tail = _inline_link(text, i + 1, end)
                    if tail is not None:
                        d_start, d_end, close = tail
                        found = MarkdownLink(
                            start=opener,
                            end=close,
                            label=text[opener + 1 : i],
                            dest=text[d_start:d_end],
                            dest_start=d_start,
                            dest_end=d_end,
                        )
                if found is None and refs:
                    found = _reference_link(text, opener, i, end, refs)
                    if found is not None:
                        close = found.end
                if found is not None:
                    if image:
                        excluded.append((opener - 1, close))
                    else:
                        links.append(found)
                        excluded.append((opener, close))
                        stack.clear()
                    i = close
                    continue
            i += 1
    excluded.sort()
    return InlineScan(excluded=_merge(excluded), links=links)


def _reference_link(
    text: str, opener: int, closer: int, end: int, refs: Mapping[str, LinkReference]
) -> MarkdownLink | None:
    """`[글자]` 뒤의 참조 링크 꼴(`[이름]`·`[]`·없음)을 읽는다. 정의가 없는 이름이면 None.

    CommonMark처럼 `[글자][이름]`의 이름이 정의에 없으면 링크가 아니다(`[글자]`만 줄임 꼴로 보지
    않는다). `[글자][]`·`[글자]`는 글자를 이름으로 쓴다.
    """
    label_text = text[opener + 1 : closer]
    stop = closer + 1
    if stop < end and text[stop] == "[":
        label_close = _label_end(text, stop, end)
        if label_close is not None:
            name = text[stop + 1 : label_close]
            if name.strip():
                key = reference_key(name)
                return _reference(opener, label_close + 1, label_text, key, refs.get(key))
            stop = label_close + 1  # `[]`: 글자를 이름으로(아래)
    if not label_text.strip() or len(label_text) > _MAX_LABEL:
        return None
    key = reference_key(label_text)
    return _reference(opener, stop, label_text, key, refs.get(key))


def _reference(
    start: int, end: int, label: str, key: str, ref: LinkReference | None
) -> MarkdownLink | None:
    if ref is None:
        return None
    return MarkdownLink(
        start=start,
        end=end,
        label=label,
        dest=ref.dest,
        dest_start=ref.dest_start,
        dest_end=ref.dest_end,
        reference=key,
    )


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in spans:
        if out and s < out[-1][1]:
            if e > out[-1][1]:
                out[-1] = (out[-1][0], e)
            continue
        out.append((s, e))
    return out
