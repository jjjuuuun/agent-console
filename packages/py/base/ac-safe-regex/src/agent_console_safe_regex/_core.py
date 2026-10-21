"""사용자 정규식 검증·컴파일과 시간 제한 실행(내부 구현)."""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

import regex

DEFAULT_MAX_PATTERN_CHARS = 512
"""패턴 최대 길이 기본값."""

DEFAULT_MAX_INPUT_CHARS = 4096
"""매치 대상(입력 앞부분) 최대 길이 기본값."""

DEFAULT_TIMEOUT_SECONDS = 0.1
"""매치 1회의 시간 제한 기본값(초)."""


class UnsafeRegexError(ValueError):
    """사용자 정규식이 잘못됐거나 허용 범위를 벗어났다. 메시지는 사람이 읽는 문장."""


class RegexTimeoutError(TimeoutError):
    """매치가 시간 제한을 넘었다(과도한 백트래킹 등)."""


@dataclass(frozen=True, slots=True)
class SafeMatch:
    """매치 결과: 입력 기준 위치와 이름 그룹 값(구현 라이브러리 타입은 노출하지 않음)."""

    start: int
    end: int
    text: str
    named: Mapping[str, str | None] = field(default_factory=dict)
    spans: Mapping[str, tuple[int, int] | None] = field(default_factory=dict)
    """이름 그룹의 입력 기준 (시작, 끝). 참여하지 않은 그룹은 None."""

    def group(self, name: str) -> str | None:
        """이름 그룹 값. 그룹이 없거나 참여하지 않았으면 None."""
        return self.named.get(name)

    def span(self, name: str) -> tuple[int, int] | None:
        """이름 그룹의 (시작, 끝). 그룹이 없거나 참여하지 않았으면 None."""
        return self.spans.get(name)


@dataclass(frozen=True, slots=True)
class SafePattern:
    """검사를 통과한 사용자 정규식. 매치는 입력 앞부분만, 시간 제한 안에서 수행한다.

    Attributes:
        source: 원본 패턴 문자열.
        timeout: 매치 1회 시간 제한(초).
        max_input_chars: 검사할 입력 앞부분 길이.
    """

    source: str
    timeout: float
    max_input_chars: int
    _compiled: regex.Pattern[str] = field(repr=False, compare=False)

    @property
    def group_names(self) -> frozenset[str]:
        """패턴의 이름 그룹들."""
        return frozenset(self._compiled.groupindex)

    def search(self, text: str) -> SafeMatch | None:
        """입력 앞 ``max_input_chars`` 글자에서 처음 매치를 찾는다.

        Raises:
            RegexTimeoutError: 시간 제한 초과.
        """
        return self._run(text, anchored=False)

    def match(self, text: str) -> SafeMatch | None:
        """입력 시작 위치에서 매치한다(``search`` 와 같은 제한).

        Raises:
            RegexTimeoutError: 시간 제한 초과.
        """
        return self._run(text, anchored=True)

    def finditer(self, text: str, *, overlapped: bool = False) -> list[SafeMatch]:
        """입력 앞 ``max_input_chars`` 글자에서 모든 매치(앞에서부터).

        기본은 겹치지 않는 매치다. ``overlapped=True``면 시작 위치마다 매치를 찾아 서로 겹칠 수
        있다(앞 매치가 뒤 후보를 삼키지 않게 할 때). 시간 제한은 훑기 전체에 한 번 적용된다.

        Raises:
            RegexTimeoutError: 시간 제한 초과.
        """
        target = text[: self.max_input_chars]
        try:
            found = self._compiled.finditer(target, overlapped=overlapped, timeout=self.timeout)
            return [_wrap(m) for m in found]
        except TimeoutError as exc:
            raise RegexTimeoutError(
                f"정규식 매치가 시간 제한({self.timeout}초)을 넘었다: {self.source[:80]!r}"
            ) from exc

    def _run(self, text: str, *, anchored: bool) -> SafeMatch | None:
        target = text[: self.max_input_chars]
        try:
            if anchored:
                m = self._compiled.match(target, timeout=self.timeout)
            else:
                m = self._compiled.search(target, timeout=self.timeout)
        except TimeoutError as exc:
            raise RegexTimeoutError(
                f"정규식 매치가 시간 제한({self.timeout}초)을 넘었다: {self.source[:80]!r}"
            ) from exc
        if m is None:
            return None
        return _wrap(m)


def _wrap(m: regex.Match[str]) -> SafeMatch:
    spans: dict[str, tuple[int, int] | None] = {}
    for name in m.re.groupindex:
        start, end = m.span(name)
        spans[name] = None if start < 0 else (start, end)
    return SafeMatch(
        start=m.start(), end=m.end(), text=m.group(0), named=m.groupdict(), spans=spans
    )


# ---------------------------------------------------------------- 위험 패턴 휴리스틱


@dataclass
class _Frame:
    content_start: int
    atomic: bool
    alt_splits: list[int] = field(default_factory=list)
    inner_quantified: bool = False


def _skip_class(p: str, i: int) -> int:
    """``[`` 위치에서 문자 클래스 끝 다음 위치를 돌려준다."""
    j = i + 1
    if j < len(p) and p[j] == "^":
        j += 1
    if j < len(p) and p[j] == "]":
        j += 1
    depth = 1
    while j < len(p) and depth:
        if p[j] == "\\":
            j += 2
            continue
        if p[j] == "[":
            depth += 1  # regex 모듈의 중첩 집합
        elif p[j] == "]":
            depth -= 1
        j += 1
    return j


def _group_prefix(p: str, i: int) -> tuple[int, bool, bool]:
    """``(`` 위치 → (내용 시작 위치, 원자 그룹 여부, 내용 없는 인라인 플래그 여부)."""
    if not p.startswith("(?", i):
        return i + 1, False, False
    rest = p[i + 2 :]
    if rest.startswith(">"):
        return i + 3, True, False
    for lead in (":", "=", "!", "|"):
        if rest.startswith(lead):
            return i + 3, False, False
    for lead in ("<=", "<!"):
        if rest.startswith(lead):
            return i + 4, False, False
    if rest.startswith(("P<", "<")):
        close = p.find(">", i)
        return (close + 1 if close != -1 else len(p)), False, False
    # 인라인 플래그 (?i) 또는 (?i:...)
    j = i + 2
    while j < len(p) and (p[j].isalpha() or p[j] == "-"):
        j += 1
    if j < len(p) and p[j] == ":":
        return j + 1, False, False
    return j, False, True


def _quantifier(p: str, i: int) -> tuple[int, bool, bool]:
    """``i`` 위치의 수량자 → (길이, 반복 수량자인지(최대>1), 소유 수량자인지)."""
    if i >= len(p):
        return 0, False, False
    length, repeating = 0, False
    if p[i] in "*+":
        length, repeating = 1, True
    elif p[i] == "?":
        length = 1
    elif p[i] == "{":
        m = regex.match(r"\{(\d*)(,?)(\d*)\}", p[i:])
        if m is not None:
            length = len(m.group(0))
            lo, comma, hi = m.group(1), m.group(2), m.group(3)
            # {n,} {n,m}: 상한 없음 또는 >1 / {n}: n>1
            repeating = (hi == "" or int(hi) > 1) if comma else (lo != "" and int(lo) > 1)
    if length == 0:
        return 0, False, False
    possessive = i + length < len(p) and p[i + length] == "+"
    lazy = i + length < len(p) and p[i + length] == "?"
    return length + (1 if possessive or lazy else 0), repeating, possessive


def _alternatives(p: str, frame: _Frame, end: int) -> list[str]:
    bounds = [frame.content_start - 1, *frame.alt_splits, end]
    return [p[a + 1 : b] for a, b in itertools.pairwise(bounds)]


def _overlapping(alts: list[str]) -> bool:
    """대안끼리 같은 입력을 여러 방식으로 매치할 수 있어 보이면 True(보수적 휴리스틱)."""
    if len(alts) < 2:
        return False
    for a in alts:
        if a == "" or a.startswith("."):
            return True
    for x in range(len(alts)):
        for y in range(len(alts)):
            if x != y and alts[y].startswith(alts[x]):
                return True  # 같거나 접두어 관계: (a|a), (a|ab)
    return False


def _check_backtracking(p: str) -> None:
    stack = [_Frame(content_start=0, atomic=False)]
    i = 0
    while i < len(p):
        c = p[i]
        if c == "\\":
            i += 2
            continue
        if c == "[":
            i = _skip_class(p, i)
            continue
        if c == "(":
            start, atomic, flags_only = _group_prefix(p, i)
            if flags_only:
                i = start + 1  # ")" 다음
                continue
            stack.append(_Frame(content_start=start, atomic=atomic))
            i = start
            continue
        if c == ")" and len(stack) > 1:
            frame = stack.pop()
            qlen, repeating, possessive = _quantifier(p, i + 1)
            if repeating and not possessive and not frame.atomic:
                if frame.inner_quantified:
                    raise UnsafeRegexError(
                        "반복되는 그룹 안에 다시 반복이 있다(예: (a+)+, (.*a){20}). 과도한 "
                        "백트래킹 위험이 있어 허용하지 않는다. 원자 그룹 (?>...)이나 "
                        "소유 수량자(a++)로 바꿔 쓸 수 있다"
                    )
                if _overlapping(_alternatives(p, frame, i)):
                    raise UnsafeRegexError(
                        "반복되는 그룹 안의 대안이 서로 겹친다(예: (a|a)*, (a|ab)+). 과도한 "
                        "백트래킹 위험이 있어 허용하지 않는다"
                    )
            stack[-1].inner_quantified |= frame.inner_quantified or repeating
            i += 1 + qlen
            continue
        if c == "|":
            stack[-1].alt_splits.append(i)
        elif c in "*+{":
            qlen, repeating, _ = _quantifier(p, i)
            if qlen:
                stack[-1].inner_quantified |= repeating
                i += qlen
                continue
        i += 1


def check_user_regex(
    pattern: str,
    *,
    required_groups: Iterable[str] = (),
    max_pattern_chars: int = DEFAULT_MAX_PATTERN_CHARS,
    ignore_case: bool = False,
) -> None:
    """검증만 한다(설정 저장 전 검사용). 규칙은 ``compile_user_regex`` 와 같다.

    Raises:
        UnsafeRegexError: 검사 실패.
    """
    _compile(pattern, tuple(required_groups), max_pattern_chars, ignore_case)


def _compile(
    pattern: str, required_groups: tuple[str, ...], max_pattern_chars: int, ignore_case: bool
) -> regex.Pattern[str]:
    if not pattern:
        raise UnsafeRegexError("정규식이 비어 있다")
    if len(pattern) > max_pattern_chars:
        raise UnsafeRegexError(f"정규식이 너무 길다({len(pattern)}자, 최대 {max_pattern_chars}자)")
    flags = regex.VERSION0 | (regex.IGNORECASE if ignore_case else 0)
    try:
        compiled = regex.compile(pattern, flags)
    except regex.error as exc:
        raise UnsafeRegexError(f"정규식 문법 오류: {exc}") from exc
    _check_backtracking(pattern)
    missing = [g for g in required_groups if g not in compiled.groupindex]
    if missing:
        names = ", ".join(missing)
        raise UnsafeRegexError(f"이름 그룹이 필요하다: {names} (예: (?P<{missing[0]}>...))")
    return compiled


def compile_user_regex(
    pattern: str,
    *,
    required_groups: Iterable[str] = (),
    max_pattern_chars: int = DEFAULT_MAX_PATTERN_CHARS,
    ignore_case: bool = False,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
) -> SafePattern:
    """사용자 정규식을 검사하고 시간 제한 실행용 ``SafePattern`` 으로 만든다.

    Args:
        pattern: 사용자 정규식(Python ``re`` 와 호환되는 문법).
        required_groups: 반드시 있어야 하는 이름 그룹.
        max_pattern_chars: 패턴 최대 길이.
        ignore_case: 대소문자 무시.
        timeout: 매치 1회 시간 제한(초, > 0).
        max_input_chars: 매치할 입력 앞부분 길이(>= 1).

    Raises:
        UnsafeRegexError: 비었거나, 너무 길거나, 문법 오류, 위험 패턴(중첩 반복·겹치는 대안),
            필수 이름 그룹 없음.
        ValueError: ``timeout``/``max_input_chars`` 가 범위 밖.
    """
    if timeout <= 0:
        raise ValueError("timeout은 0보다 커야 한다")
    if max_input_chars < 1:
        raise ValueError("max_input_chars는 1 이상이어야 한다")
    compiled = _compile(pattern, tuple(required_groups), max_pattern_chars, ignore_case)
    return SafePattern(
        source=pattern, timeout=timeout, max_input_chars=max_input_chars, _compiled=compiled
    )
