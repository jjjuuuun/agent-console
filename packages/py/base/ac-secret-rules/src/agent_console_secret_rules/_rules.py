"""비밀 의심 판정과 의심 값 가리기(내부 구현).

규칙은 세 가지 데이터로 이뤄진다.

- **키 이름**(`key_names`): 이름을 단어로 나눠(구분자·camelCase) 이어지는 단어를 붙인 것이 키 이름과
  같으면 비밀 이름이다. 키 이름도 같은 방식으로 단어로 나눠 비교한다(`api_key` = `apikey`).
- **이름 예외 단어**(`name_exceptions`): 비밀 단어 뒤에 이 단어가 오면 비밀 이름이 아니다.
- **값 패턴**(`value_patterns`): 텍스트 안 비밀 모양 정규식(`ac-safe-regex`로 검사·실행).
  이름 그룹 `secret`(가릴 부분)·`name`(비밀 이름이어야 함)을 쓸 수 있다.

사용자 규칙은 `with_extra`로 **더하기만** 한다. 기본 규칙을 줄이는 방법은 공개하지 않는다.
판정 결과(`Finding`)에는 값을 담지 않는다.
"""

from __future__ import annotations

import functools
import logging
import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agent_console_safe_regex import (
    RegexTimeoutError,
    SafePattern,
    UnsafeRegexError,
    check_user_regex,
    compile_user_regex,
)

from ._defaults import DEFAULT_KEY_NAMES, DEFAULT_NAME_EXCEPTIONS, DEFAULT_VALUE_PATTERNS

__all__ = [
    "DEFAULT_MAX_SCAN_CHARS",
    "DEFAULT_SCAN_TIMEOUT_SECONDS",
    "REDACTED",
    "Finding",
    "FindingReason",
    "InvalidSecretRuleError",
    "RuleProblem",
    "SecretRules",
    "check_extra_rules",
    "default_is_reference",
    "default_rules",
]

_log = logging.getLogger(__name__)

REDACTED = "[REDACTED]"
"""가린 자리에 넣는 기본 문자열."""

DEFAULT_MAX_SCAN_CHARS = 1_000_000
"""패턴 하나가 한 번에 훑는 글자 수. 더 긴 텍스트는 겹치는 조각으로 나눠 훑는다."""

DEFAULT_SCAN_TIMEOUT_SECONDS = 1.0
"""패턴 하나가 조각 하나를 훑는 시간 제한(초)."""

_MASK_FILL = "x"
"""가린 자리를 다시 훑을 때 그 자리에 채우는 글자(모든 기본 값 패턴이 값 글자로 받는다)."""

_CHUNK_OVERLAP = 4096
"""조각 경계에 걸친 비밀을 놓치지 않게 겹치는 글자 수."""

SECRET_REF_PREFIX = "secret://"


def default_is_reference(value: str) -> bool:
    """`secret://…` 비밀 참조면 참(참조는 값이 아니라 이름이므로 의심하지 않는다)."""
    return value.startswith(SECRET_REF_PREFIX)


class FindingReason:
    """`Finding.reason` 값(문서 상수)."""

    KEY_NAME: Final = "key_name"
    """가까운(또는 이어받은) 키 이름이 비밀 이름이다."""
    VALUE_PATTERN: Final = "value_pattern"
    """문자열 안에 비밀 모양(값 패턴)이 있다."""
    TIMEOUT: Final = "timeout"
    """패턴 검사가 시간 제한을 넘었다(안전한 쪽으로 의심)."""


@dataclass(frozen=True, slots=True)
class Finding:
    """의심 위치 하나. 값은 담지 않는다.

    Attributes:
        path: 검사한 값 기준 JSON Pointer(`find_suspected`의 `path` 접두 포함).
        reason: `FindingReason` 값.
    """

    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class RuleProblem:
    """사용자 규칙 하나의 문제(설정 저장 전 검사용).

    Attributes:
        field: `extra_key_names` 또는 `extra_value_patterns`.
        index: 목록 안 위치.
        message: 사람이 읽는 설명(패턴 원문은 담지 않는다).
    """

    field: str
    index: int
    message: str


class InvalidSecretRuleError(ValueError):
    """사용자 규칙이 잘못됐다(빈 이름, 위험하거나 잘못된 정규식). `problems`에 상세."""

    def __init__(self, problems: Sequence[RuleProblem]) -> None:
        self.problems = list(problems)
        summary = "; ".join(f"{p.field}[{p.index}]: {p.message}" for p in self.problems)
        super().__init__(f"비밀 규칙이 잘못됐습니다: {summary}")


_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")


def _words(name: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(name)]


def _compact(name: str) -> str:
    return "".join(_words(name))


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


@dataclass(frozen=True, slots=True)
class _Pattern:
    source: str
    compiled: SafePattern
    has_name: bool
    has_secret: bool


def _compile(pattern: str, *, timeout: float, max_chars: int) -> _Pattern:
    compiled = compile_user_regex(pattern, timeout=timeout, max_input_chars=max_chars)
    groups = compiled.group_names
    return _Pattern(pattern, compiled, "name" in groups, "secret" in groups)


def check_extra_rules(
    extra_key_names: Iterable[str] = (), extra_value_patterns: Iterable[str] = ()
) -> list[RuleProblem]:
    """사용자 규칙을 검사한다(저장 전 검사용, 예외 대신 문제 목록).

    키 이름은 글자·숫자 단어가 하나 이상 있어야 한다. 값 패턴은 `ac-safe-regex` 검사(문법·길이·
    중첩 반복 같은 위험 패턴)를 통과해야 한다. `RuleProblem.field`는 `extra_key_names`·
    `extra_value_patterns`(설정 필드 이름)이다.
    """
    return _problems(
        extra_key_names, extra_value_patterns, "extra_key_names", "extra_value_patterns"
    )


def _problems(
    key_names: Iterable[str], value_patterns: Iterable[str], name_field: str, pattern_field: str
) -> list[RuleProblem]:
    problems: list[RuleProblem] = []
    for index, name in enumerate(key_names):
        if not _words(name):
            problems.append(RuleProblem(name_field, index, "글자나 숫자가 있는 이름이어야 합니다"))
    for index, pattern in enumerate(value_patterns):
        try:
            check_user_regex(pattern)
        except UnsafeRegexError as exc:
            problems.append(RuleProblem(pattern_field, index, str(exc)))
    return problems


class SecretRules:
    """비밀 의심 규칙(기본 + 사용자 추가분). 만든 뒤에는 바뀌지 않는다(스레드 안전).

    Args:
        key_names: 비밀 이름 단어(기본 `DEFAULT_KEY_NAMES`).
        value_patterns: 텍스트 안 비밀 모양 정규식(기본 `DEFAULT_VALUE_PATTERNS`).
        name_exceptions: 비밀 단어 뒤에 오면 비밀 이름이 아니게 하는 단어.
        is_reference: 참조 문자열이면 참(의심·가림에서 뺀다). 기본 `secret://…`.
        mask: 가린 자리에 넣을 문자열.
        timeout: 패턴 하나가 조각 하나를 훑는 시간 제한(초).
        max_scan_chars: 패턴 하나가 한 번에 훑는 글자 수(더 길면 겹치는 조각으로 나눈다).

    Raises:
        InvalidSecretRuleError: 키 이름·값 패턴이 잘못됐을 때.
    """

    def __init__(
        self,
        key_names: Iterable[str] = DEFAULT_KEY_NAMES,
        value_patterns: Iterable[str] = DEFAULT_VALUE_PATTERNS,
        *,
        name_exceptions: Iterable[str] = DEFAULT_NAME_EXCEPTIONS,
        is_reference: Callable[[str], bool] = default_is_reference,
        mask: str = REDACTED,
        timeout: float = DEFAULT_SCAN_TIMEOUT_SECONDS,
        max_scan_chars: int = DEFAULT_MAX_SCAN_CHARS,
    ) -> None:
        names = tuple(key_names)
        patterns = tuple(value_patterns)
        problems = _problems(names, patterns, "key_names", "value_patterns")
        if problems:
            raise InvalidSecretRuleError(problems)
        compiled = [_compile(p, timeout=timeout, max_chars=max_scan_chars) for p in patterns]
        self.key_names: tuple[str, ...] = names
        self.value_patterns: tuple[str, ...] = patterns
        self.name_exceptions: frozenset[str] = frozenset(w.lower() for w in name_exceptions)
        self.is_reference = is_reference
        self.mask = mask
        self.timeout = timeout
        self.max_scan_chars = max(_CHUNK_OVERLAP * 2, max_scan_chars)
        self._compact_names = frozenset(_compact(n) for n in names)
        self._patterns = tuple(compiled)

    # ------------------------------------------------------------ 만들기

    def with_extra(
        self, *, key_names: Iterable[str] = (), value_patterns: Iterable[str] = ()
    ) -> SecretRules:
        """이 규칙에 사용자 규칙을 **더한** 새 규칙(줄이는 방법은 없다).

        Raises:
            InvalidSecretRuleError: 추가 규칙이 잘못됐을 때(위치는 추가 목록 기준).
        """
        extra_names = tuple(key_names)
        extra_patterns = tuple(value_patterns)
        problems = check_extra_rules(extra_names, extra_patterns)
        if problems:
            raise InvalidSecretRuleError(problems)
        return SecretRules(
            (*self.key_names, *extra_names),
            (*self.value_patterns, *extra_patterns),
            name_exceptions=self.name_exceptions,
            is_reference=self.is_reference,
            mask=self.mask,
            timeout=self.timeout,
            max_scan_chars=self.max_scan_chars,
        )

    # ------------------------------------------------------------ 이름

    def name_suspected(self, name: str) -> bool:
        """이름(환경 변수·헤더·플래그·쿼리·객체 키)이 비밀을 담을 것처럼 보이면 참.

        이어지는 단어를 붙인 것이 키 이름과 같고, 그 뒤 단어 중에 예외 단어가 없으면 의심한다.
        """
        words = _words(name)
        for start in range(len(words)):
            joined = ""
            for end in range(start, len(words)):
                joined += words[end]
                if joined in self._compact_names and not any(
                    w in self.name_exceptions for w in words[end + 1 :]
                ):
                    return True
        return False

    def _name_plain(self, name: str) -> bool:
        words = _words(name)
        return bool(words) and words[-1] in self.name_exceptions

    # ------------------------------------------------------------ 텍스트

    def _spans(self, text: str) -> tuple[list[tuple[int, int]], bool]:
        """가릴 구간들(이미 가린 자리는 뺀 조각)과 시간 초과 여부.

        텍스트에 가림 문자열이 있으면 그 자리를 값 글자(`_MASK_FILL`)로 바꾼 사본도 함께 훑는다.
        가린 자리를 사이에 둔 비밀(`password=[REDACTED]hunter2`, `sk-…[REDACTED]…`)의 뒤 조각이
        패턴 끝에서 잘려 남지 않게 하려는 것이다(5R.19). 원문 훑기도 그대로 하므로 가린 자리 바로
        뒤에 붙은 토큰(`[REDACTED]ghp_…`)도 놓치지 않는다.
        """
        masks = self._mask_spans(text)
        spans, timed_out = self._scan(text)
        if masks:
            filled = list(text)
            for start, end in masks:
                filled[start:end] = _MASK_FILL * (end - start)
            more, more_timed_out = self._scan("".join(filled))
            spans.extend(more)
            timed_out = timed_out or more_timed_out
        return _outside(spans, masks), timed_out

    def _scan(self, text: str) -> tuple[list[tuple[int, int]], bool]:
        spans: list[tuple[int, int]] = []
        timed_out = False
        for pattern in self._patterns:
            for offset, chunk in self._chunks(text):
                try:
                    matches = pattern.compiled.finditer(chunk, overlapped=True)
                except RegexTimeoutError:
                    _log.warning(
                        "비밀 의심 패턴 검사가 시간 제한을 넘었습니다(패턴 %d자)",
                        len(pattern.source),
                    )
                    timed_out = True
                    continue
                for m in matches:
                    if pattern.has_name:
                        name = m.group("name")
                        if name is None or not self.name_suspected(name):
                            continue
                    span = m.span("secret") if pattern.has_secret else (m.start, m.end)
                    if span is None or span[0] == span[1]:
                        continue
                    if self.is_reference(chunk[span[0] : span[1]]):
                        continue
                    spans.append((offset + span[0], offset + span[1]))
        return spans, timed_out

    def _mask_spans(self, text: str) -> list[tuple[int, int]]:
        """텍스트 안에 이미 있는 `mask` 자리(다시 가리지 않는다 — 가림 멱등)."""
        if not self.mask:
            return []
        found: list[tuple[int, int]] = []
        start = text.find(self.mask)
        while start >= 0:
            found.append((start, start + len(self.mask)))
            start = text.find(self.mask, start + len(self.mask))
        return found

    def _chunks(self, text: str) -> Iterator[tuple[int, str]]:
        size = self.max_scan_chars
        if len(text) <= size:
            yield 0, text
            return
        step = size - _CHUNK_OVERLAP
        for offset in range(0, len(text), step):
            yield offset, text[offset : offset + size]
            if offset + size >= len(text):
                return

    def value_suspected(self, text: str) -> bool:
        """문자열 안에 비밀 모양이 있으면 참(시간 초과도 참 — 안전한 쪽)."""
        if not text or self.is_reference(text):
            return False
        spans, timed_out = self._spans(text)
        return bool(spans) or timed_out

    def redact_suspected(self, text: str) -> str:
        """텍스트 안 비밀 모양 부분을 `mask`로 바꾼 문자열(없으면 그대로).

        패턴 검사가 시간 제한을 넘으면 텍스트 전체를 가린다(안전한 쪽).
        """
        if not text:
            return text
        spans, timed_out = self._spans(text)
        if timed_out:
            return self.mask
        if not spans:
            return text
        # 가린 자리에 붙은 조각은 그 자리와 한 덩어리로 가린다
        # (`password=[REDACTED]hunter2` → `password=[REDACTED]`, 두 번 적용해도 같다).
        masks = self._mask_spans(text)
        glued = [m for m in masks if any(s <= m[1] and m[0] <= e for s, e in spans)]
        merged: list[list[int]] = []
        for start, end in sorted([*spans, *glued]):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        out: list[str] = []
        cursor = 0
        for start, end in merged:
            out.append(text[cursor:start])
            out.append(self.mask)
            cursor = end
        out.append(text[cursor:])
        return "".join(out)

    def redact_value(self, value: Any) -> Any:
        """JSON 값의 문자열 잎마다 `redact_suspected`를 적용한 사본(키·구조·다른 타입은 그대로)."""
        if isinstance(value, str):
            return self.redact_suspected(value)
        if isinstance(value, dict):
            return {k: self.redact_value(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [self.redact_value(v) for v in value]
        return value

    # ------------------------------------------------------------ 구조

    def find_suspected(
        self, value: Any, *, path: str = "", name: str | None = None
    ) -> list[Finding]:
        """JSON 값에서 평문 비밀로 의심되는 잎의 위치를 찾는다.

        - 문자열 잎: 비어 있지 않고 참조가 아니며, 가까운 비밀 키 이름 아래이거나(`key_name`)
          안에 비밀 모양이 있으면(`value_pattern`) 의심한다.
        - 숫자 잎(불리언 제외): 비밀 키 이름 아래면 의심한다(`{"API_KEY": 12345}`).
        - 하위 객체·목록은 가장 가까운 비밀 키 이름을 이어받는다. 단 자기 이름의 마지막 단어가
          예외 단어면(`{"auth": {"mode": "oauth"}}`) 이어받지 않는다.

        Args:
            value: 검사할 JSON 값.
            path: 결과 위치 앞에 붙일 JSON Pointer(예: 문서 안 위치).
            name: `value` 자신의 키 이름(있으면 그 이름부터 판정).
        """
        secret = name is not None and self.name_suspected(name)
        return list(self._walk(value, path, secret))

    def _walk(self, value: Any, pointer: str, secret: bool) -> Iterator[Finding]:
        if isinstance(value, str):
            if not value or self.is_reference(value):
                return
            if secret:
                yield Finding(pointer, FindingReason.KEY_NAME)
                return
            spans, timed_out = self._spans(value)
            if spans:
                yield Finding(pointer, FindingReason.VALUE_PATTERN)
            elif timed_out:
                yield Finding(pointer, FindingReason.TIMEOUT)
        elif isinstance(value, bool) or value is None:
            return
        elif isinstance(value, int | float):
            if secret:
                yield Finding(pointer, FindingReason.KEY_NAME)
        elif isinstance(value, dict):
            for key, item in value.items():
                text = str(key)
                child = self.name_suspected(text) or (secret and not self._name_plain(text))
                yield from self._walk(item, f"{pointer}/{_escape(text)}", child)
        elif isinstance(value, list | tuple):
            flag_value = False
            for index, item in enumerate(value):
                # 인자 목록의 `--token`, `값` 꼴: 비밀 플래그 다음 항목은 비밀 값으로 본다.
                is_flag = isinstance(item, str) and item.startswith("-")
                value_of_flag = flag_value and not is_flag
                yield from self._walk(item, f"{pointer}/{index}", secret or value_of_flag)
                flag_value = self._secret_flag(item)

    def _secret_flag(self, item: Any) -> bool:
        if not isinstance(item, str) or not item.startswith("-") or "=" in item:
            return False
        return self.name_suspected(item)


def _outside(
    spans: Sequence[tuple[int, int]], masks: Sequence[tuple[int, int]]
) -> list[tuple[int, int]]:
    """`spans`에서 `masks`(이미 가린 자리, 정렬·겹침 없음) 부분을 뺀 조각들(빈 조각은 버린다).

    `password=[REDACTED]`를 다시 훑으면 값 패턴이 `[REDACTED`까지만 잡아 `[REDACTED]]`로 늘어나던
    문제를 막는다. 가린 자리 옆에 남은 글자는 그대로 가린다(가린 자리를 섞어 비밀을 숨길 수 없다).
    """
    if not masks:
        return list(spans)
    out: list[tuple[int, int]] = []
    for start, end in spans:
        cursor = start
        for m_start, m_end in masks:
            if m_end <= cursor or m_start >= end:
                continue
            if m_start > cursor:
                out.append((cursor, m_start))
            cursor = max(cursor, m_end)
        if cursor < end:
            out.append((cursor, end))
    return out


@functools.cache
def default_rules() -> SecretRules:
    """기본 규칙(`SecretRules()`)을 한 번만 만들어 돌려준다(불변이라 공유해도 된다)."""
    return SecretRules()
