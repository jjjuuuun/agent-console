"""화면 글자 규칙: 정규식 목록 → 이름 붙은 신호.

규칙은 데이터다(이름 + 정규식). 정규식 컴파일은 주입한다(기본 ``re.compile``). 사용자가 고칠 수
있는 규칙을 받는 쪽은 안전 검사를 거치는 컴파일 함수(예: ``agent-console-secret-rules``의 검사
정규식)를 넘긴다. 이 패키지는 사내 패키지에 의존하지 않는다.

규칙은 **한 줄 안에서** 찾는다(원문 흐름의 ``\\n`` 기준). ``ExpectWatcher``는 조각으로 들어오는
원문 흐름에서 끝난 줄과, 아직 끝나지 않은 마지막 줄을 함께 본다. 끝나지 않은 줄에서 맞은 글자가 줄
끝에 닿아 있으면 (예: 아직 다 오지 않은 URL) 더 들어오거나 ``flush()``할 때까지 미룬다.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

Compiler = Callable[[str], re.Pattern[str]]
"""정규식 문자열 → 컴파일된 패턴. 거부할 때는 ``ValueError``(또는 하위 형식)를 낸다."""

DEFAULT_MAX_PENDING_CHARS = 16_384
"""끝나지 않은 마지막 줄을 기억하는 최대 글자 수(넘으면 앞을 버린다)."""


@dataclass(frozen=True)
class ExpectRule:
    """규칙 하나.

    Attributes:
        name: 신호 이름(예: ``open_url``·``needs_code``). 같은 이름을 여러 규칙이 써도 된다.
        pattern: 정규식 문자열.
    """

    name: str
    pattern: str


@dataclass(frozen=True)
class ExpectMatch:
    """규칙이 맞은 결과.

    Attributes:
        name: 규칙 이름.
        text: 맞은 글자 전체(``group(0)``).
        groups: 이름 붙은 그룹(없으면 빈 dict).
        line: 맞은 줄 전체.
    """

    name: str
    text: str
    groups: Mapping[str, str] = field(default_factory=dict)
    line: str = ""


class ExpectRuleError(ValueError):
    """규칙 정규식을 컴파일하지 못했다(``rule`` = 규칙 이름, 원인은 ``__cause__``)."""

    def __init__(self, rule: str, reason: str) -> None:
        super().__init__(f"규칙 {rule!r}의 정규식이 올바르지 않습니다: {reason}")
        self.rule = rule


class ExpectRules:
    """컴파일된 규칙 목록(불변).

    Args:
        rules: ``ExpectRule`` 목록 또는 ``이름 → 정규식`` 매핑.
        compile: 정규식 컴파일 함수(기본 ``re.compile``).

    Raises:
        ExpectRuleError: 컴파일 실패.

    Example:
        >>> rules = ExpectRules({"url": r"https://\\S+", "code": r"(?i)paste code"})
        >>> [m.name for m in rules.match_line("Paste code here: https://example.com/x")]
        ['url', 'code']
    """

    def __init__(
        self,
        rules: Iterable[ExpectRule] | Mapping[str, str],
        *,
        compile: Compiler = re.compile,
    ) -> None:
        items = (
            [ExpectRule(k, v) for k, v in rules.items()]
            if isinstance(rules, Mapping)
            else list(rules)
        )
        compiled: list[tuple[ExpectRule, re.Pattern[str]]] = []
        for rule in items:
            try:
                compiled.append((rule, compile(rule.pattern)))
            except (ValueError, re.error) as exc:
                raise ExpectRuleError(rule.name, type(exc).__name__) from exc
        self._rules = tuple(compiled)

    @property
    def rules(self) -> tuple[ExpectRule, ...]:
        """규칙(받은 순서)."""
        return tuple(rule for rule, _ in self._rules)

    def match_line(self, line: str) -> list[ExpectMatch]:
        """한 줄에서 맞은 규칙들(규칙 순서, 규칙마다 처음 맞은 것 하나)."""
        return [m for m, _end in self._match_with_end(line)]

    def _match_with_end(self, line: str) -> list[tuple[ExpectMatch, int]]:
        found: list[tuple[ExpectMatch, int]] = []
        for rule, pattern in self._rules:
            hit = pattern.search(line)
            if hit is None:
                continue
            groups = {k: v for k, v in hit.groupdict().items() if v is not None}
            found.append((ExpectMatch(rule.name, hit.group(0), groups, line), hit.end()))
        return found

    def match_text(self, text: str) -> list[ExpectMatch]:
        """여러 줄 글자에서 맞은 규칙들(줄 순서 → 규칙 순서)."""
        out: list[ExpectMatch] = []
        for line in text.split("\n"):
            out.extend(self.match_line(line))
        return out

    def first(self, text: str, name: str) -> ExpectMatch | None:
        """여러 줄 글자에서 ``name`` 규칙이 처음 맞은 것."""
        for found in self.match_text(text):
            if found.name == name:
                return found
        return None


class ExpectWatcher:
    """조각으로 들어오는 원문 흐름에 규칙을 걸어 새로 맞은 것만 돌려준다.

    Args:
        rules: 규칙.
        max_pending_chars: 끝나지 않은 마지막 줄을 기억하는 최대 글자 수.

    Example:
        >>> w = ExpectWatcher(ExpectRules({"url": r"https://\\S+"}))
        >>> w.feed("open https://exa")      # 줄 끝에 닿아 미룬다
        []
        >>> [m.text for m in w.feed("mple.com/a\\n")]
        ['https://example.com/a']
    """

    def __init__(
        self, rules: ExpectRules, *, max_pending_chars: int = DEFAULT_MAX_PENDING_CHARS
    ) -> None:
        self._rules = rules
        self._pending = ""
        self._reported: set[tuple[str, str]] = set()  # 끝나지 않은 줄에서 이미 알린 (이름, 글자)
        self._max_pending = max_pending_chars

    def feed(self, text: str) -> list[ExpectMatch]:
        """새 원문 조각을 받아 새로 맞은 규칙을 돌려준다."""
        if not text:
            return []
        buf = self._pending + text
        *done, rest = buf.split("\n")
        out: list[ExpectMatch] = []
        for line in done:
            for found in self._rules.match_line(line):
                if (found.name, found.text) not in self._reported:
                    out.append(found)
            self._reported.clear()
        if len(rest) > self._max_pending:
            rest = rest[-self._max_pending :]
        self._pending = rest
        out.extend(self._scan_pending(final=False))
        return out

    def flush(self) -> list[ExpectMatch]:
        """끝나지 않은 마지막 줄에서 미뤄 둔 것까지 돌려준다(하위 프로세스가 끝났을 때 등)."""
        return self._scan_pending(final=True)

    def _scan_pending(self, *, final: bool) -> list[ExpectMatch]:
        out: list[ExpectMatch] = []
        line = self._pending
        for found, end in self._rules._match_with_end(line):
            key = (found.name, found.text)
            if key in self._reported:
                continue
            if not final and end >= len(line):
                continue  # 아직 자랄 수 있다
            self._reported.add(key)
            out.append(found)
        return out


__all__ = [
    "DEFAULT_MAX_PENDING_CHARS",
    "Compiler",
    "ExpectMatch",
    "ExpectRule",
    "ExpectRuleError",
    "ExpectRules",
    "ExpectWatcher",
]
