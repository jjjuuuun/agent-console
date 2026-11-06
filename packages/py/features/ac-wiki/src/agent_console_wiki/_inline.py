"""인라인 영역(문단·제목 원문 한 덩어리) 훑기: 코드 조각·자동 링크·이미지·마크다운 링크의 원문 위치.

블록 구조(코드 블록·HTML 블록·문단 경계)는 markdown-it-py가 정하고, 인라인 영역 안은 여기서 원문
위치를 그대로 얻는다. markdown-it-py 인라인 토큰은 원문 위치를 주지 않고 전체 인라인 파싱은 블록
파싱보다 열 배쯤 느리다(페이지 2,000개 기준 약 10초 — design §7R.14의 2초를 넘음, `[7R.7 구현]`).
그래서 CommonMark 규칙 중 링크 위치에 필요한 것만 따른다:

- 코드 조각: 백틱 n개로 열고 정확히 n개로 닫는다. 여는 백틱 앞 역슬래시는 그 백틱 하나를 글자로
만든다.
- 자동 링크 `<scheme:…>`: 링크 패턴을 걸지 않는다.
- 인라인 링크 `[글자](대상 "제목")`·이미지 `![…](…)`: 괄호 짝·`<…>` 대상·제목을 읽는다. 링크 안에
링크는
  없다. 참조 링크(`[글자][이름]`)는 읽지 않는다.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

__all__ = ["InlineScan", "MarkdownLink", "scan_inline"]

_BACKTICKS = re.compile(r"`+")
_AUTOLINK = re.compile(r"<[A-Za-z][A-Za-z0-9+.\-]{1,31}:[^\s<>]*>")
_SPECIAL = re.compile(r"[\[\]\\]")
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)", re.DOTALL)
_SPACE = " \t"


@dataclass(frozen=True, slots=True)
class MarkdownLink:
    """인라인 링크 하나(위치는 훑은 글 기준 코드 포인트).

    Attributes:
        start: `[` 위치.
        end: 닫는 `)` 다음 위치.
        label: 링크 글자 원문(`[`·`]` 안).
        dest: 대상 원문(`<…>`면 괄호 안).
        dest_start: 대상 원문 시작.
        dest_end: 대상 원문 끝.
    """

    start: int
    end: int
    label: str
    dest: str
    dest_start: int
    dest_end: int


@dataclass(slots=True)
class InlineScan:
    """인라인 영역 훑기 결과.

    Attributes:
        excluded: 링크 패턴을 걸지 않을 범위(코드 조각·자동 링크·이미지·마크다운 링크), 시작 순.
        links: 마크다운 인라인 링크(이미지 제외), 시작 순.
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


def scan_inline(text: str) -> InlineScan:
    """인라인 영역 원문을 훑는다(위치는 `text` 기준 코드 포인트)."""
    has_link = "](" in text
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
                if i + 1 < end and text[i + 1] == "(":
                    tail = _inline_link(text, i + 1, end)
                    if tail is not None:
                        d_start, d_end, close = tail
                        image = (
                            opener > 0
                            and text[opener - 1] == "!"
                            and not _escaped(text, opener - 1)
                        )
                        if image:
                            excluded.append((opener - 1, close))
                        else:
                            links.append(
                                MarkdownLink(
                                    start=opener,
                                    end=close,
                                    label=text[opener + 1 : i],
                                    dest=text[d_start:d_end],
                                    dest_start=d_start,
                                    dest_end=d_end,
                                )
                            )
                            excluded.append((opener, close))
                            stack.clear()
                        i = close
                        continue
            i += 1
    excluded.sort()
    return InlineScan(excluded=_merge(excluded), links=links)


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in spans:
        if out and s < out[-1][1]:
            if e > out[-1][1]:
                out[-1] = (out[-1][0], e)
            continue
        out.append((s, e))
    return out
