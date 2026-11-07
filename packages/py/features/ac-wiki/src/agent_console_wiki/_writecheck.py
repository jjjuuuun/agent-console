"""쓰기 판단(design §7R.1.1): 쓰기 규칙 `check_write`, 비밀 검사 `WikiSecretPolicy`, 쓰기 검사 보탬
X50 `WikiWriteCheck`.

쓰기 규칙 하나의 판단(위에서부터 모두 평가, `reject`가 하나라도 맞으면 거부):

1. `applies_to`(페이지 경로 글롭, 비면 모든 페이지)에 판단 대상 `/page/path`가 맞아야 건다.
2. `when`(비거나 없으면 모든 쓰기)이 참이어야 건다.
3. 검사 항목이 있으면(`require`·`deny_patterns`) 그것이 어긋날 때(`require` 거짓, 금지 패턴에 맞는
   줄 있음)만 맞는다. 검사 항목이 없으면 1·2가 참인 것만으로 맞는다(예: 에이전트 지우기 거부).
4. 맞으면 `action`: `reject` → 거부(`wiki.rule_rejected`), `warn` → 경고(`wiki.rule_warning`).
   모르는 값은 warn으로 읽고 `wiki.unknown_action`을 함께 낸다.

지우기(`/change/op` = `delete`)는 새 본문이 없으므로 `require`·`deny_patterns`를 보지 않는다(검사
항목이 있는 규칙은 지우기에 걸지 않는다). 금지 패턴은 맞은 줄 번호만 싣는다(값 원문 없음).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from agent_console_conditions import CompiledConditions, ConditionOperator, compile_conditions
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import (
    KnownWikiAuthorKinds,
    KnownWikiChangeOps,
    KnownWikiWriteActions,
    WikiIssue,
    WikiRuleResult,
    WikiSettings,
    WikiWriteRule,
)
from agent_console_safe_regex import (
    DEFAULT_TIMEOUT_SECONDS,
    RegexTimeoutError,
    SafePattern,
    UnsafeRegexError,
    compile_user_regex,
)
from agent_console_secret_rules import SecretRules, default_rules

from ._glob import glob_match
from ._ruleset import EffectiveWikiRules, Sourced, default_operator_map
from ._text import line_of, line_starts

__all__ = [
    "CompiledWriteRules",
    "SecretRulesScanner",
    "SecretScan",
    "WikiSecretPolicy",
    "WikiSecretScanner",
    "WikiWriteCheck",
    "WriteDecision",
    "check_write",
    "compile_write_rules",
    "run_write_checks",
]

_MAX_PATTERN_INPUT = 4_000_000


@dataclass(frozen=True, slots=True)
class _CompiledRule:
    rule_id: str
    rule: WikiWriteRule
    action: str
    known_action: bool
    when: CompiledConditions | None
    require: CompiledConditions | None
    patterns: tuple[SafePattern, ...]


@dataclass(slots=True)
class CompiledWriteRules:
    """한 번 컴파일한 쓰기 규칙(`compile_write_rules`). 점검이 페이지마다 다시 쓸 때 빠르다.

    Attributes:
        rules: 컴파일한 규칙(순서 유지).
        case_insensitive: `applies_to` 비교의 대소문자 무시(문법 값).
        issues: 컴파일 이슈(쓸 수 없는 금지 패턴 `wiki.invalid_pattern` — 그 패턴만 뺌).
    """

    rules: tuple[_CompiledRule, ...]
    case_insensitive: bool = False
    issues: list[WikiIssue] = field(default_factory=list)

    @property
    def needs_content(self) -> bool:
        """본문을 읽는 규칙(금지 패턴)이 있다."""
        return any(r.patterns for r in self.rules)


@dataclass(slots=True)
class WriteDecision:
    """쓰기 판단 결과.

    Attributes:
        results: 맞은 규칙마다 결과(규칙 순서).
        issues: 이슈(거부 error·경고 warning·모르는 동작 warning).
        rejected: 거부할 쓰기다.
    """

    results: list[WikiRuleResult] = field(default_factory=list)
    issues: list[WikiIssue] = field(default_factory=list)
    rejected: bool = False

    @property
    def rejections(self) -> list[WikiIssue]:
        """거부 이슈(`severity=error`)."""
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[WikiIssue]:
        """거부가 아닌 이슈."""
        return [i for i in self.issues if i.severity != "error"]

    def extend(self, other: WriteDecision) -> None:
        """다른 판단을 뒤에 붙인다."""
        self.results.extend(other.results)
        self.issues.extend(other.issues)
        self.rejected = self.rejected or other.rejected


def compile_write_rules(
    rules: EffectiveWikiRules | Sequence[Sourced[WikiWriteRule]],
    *,
    operators: Mapping[str, ConditionOperator] | None = None,
    case_insensitive: bool = False,
    regex_timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> CompiledWriteRules:
    """쓰기 규칙을 컴파일한다(조건·금지 패턴 한 번만).

    Args:
        rules: 합친 규칙 또는 (규칙 id, 쓰기 규칙) 목록.
        operators: 조건 연산자(기본 `default_operator_map()`).
        case_insensitive: `applies_to` 대소문자 무시(문법 `case_insensitive`).
        regex_timeout: 금지 패턴 1회 시간 상한(초).
    """
    ops = operators if operators is not None else default_operator_map()
    items = rules.write_rules if isinstance(rules, EffectiveWikiRules) else list(rules)
    compiled: list[_CompiledRule] = []
    issues: list[WikiIssue] = []
    for sourced in items:
        rule = sourced.item
        patterns: list[SafePattern] = []
        for j, text in enumerate(rule.deny_patterns):
            try:
                patterns.append(
                    compile_user_regex(
                        text, timeout=regex_timeout, max_input_chars=_MAX_PATTERN_INPUT
                    )
                )
            except UnsafeRegexError as exc:
                issues.append(
                    WikiIssue(
                        severity="error",
                        code=KnownIssueCodes.WIKI_INVALID_PATTERN,
                        message=f"쓰기 규칙 '{rule.id}'의 금지 패턴을 쓸 수 없어 뺍니다: {exc}",
                        path=f"/write_rules/{rule.id}/deny_patterns/{j}",
                        rule_id=rule.id,
                    )
                )
        known = rule.action in (KnownWikiWriteActions.REJECT, KnownWikiWriteActions.WARN)
        empty_when = rule.when is None or (not rule.when.all and not rule.when.any)
        compiled.append(
            _CompiledRule(
                rule_id=sourced.rule_id,
                rule=rule,
                action=rule.action if known else KnownWikiWriteActions.WARN,
                known_action=known,
                when=None
                if empty_when or rule.when is None
                else compile_conditions(rule.when, ops),
                require=compile_conditions(rule.require, ops) if rule.require is not None else None,
                patterns=tuple(patterns),
            )
        )
    return CompiledWriteRules(tuple(compiled), case_insensitive=case_insensitive, issues=issues)


def _deny_lines(patterns: Sequence[SafePattern], content: str) -> list[int] | None:
    """맞은 줄 번호(1부터, 정렬). 시간 상한을 넘으면 None(안전한 쪽 — 맞은 것으로 본다)."""
    if not patterns:
        return []
    starts: list[int] | None = None
    lines: set[int] = set()
    for pattern in patterns:
        try:
            found = pattern.finditer(content)
        except RegexTimeoutError:
            return None
        if found and starts is None:
            starts = line_starts(content)
        for match in found:
            assert starts is not None
            lines.add(line_of(starts, match.start))
    return sorted(lines)


def check_write(
    rules: CompiledWriteRules | EffectiveWikiRules,
    subject: Mapping[str, Any],
    *,
    content: str = "",
    operators: Mapping[str, ConditionOperator] | None = None,
    case_insensitive: bool = False,
    rule_violation: bool = False,
) -> WriteDecision:
    """쓰기 규칙으로 쓰기 하나를 판단한다(모듈 설명의 규칙).

    Args:
        rules: 컴파일한 쓰기 규칙(또는 합친 규칙 — 부를 때마다 컴파일).
        subject: 판단 대상(`write_subject`).
        content: 새 본문(금지 패턴이 본다).
        operators: `rules`가 합친 규칙일 때 쓸 조건 연산자.
        case_insensitive: `rules`가 합친 규칙일 때 `applies_to` 대소문자 무시.
        rule_violation: 점검의 사후 검사로 부른다(이슈 코드 `wiki.rule_violation`).

    Returns:
        `WriteDecision`. 이슈에는 `rule_id`·`page`·첫 줄 `line`·`details{rule, message, lines,
        action}`가 있다(값 원문 없음).
    """
    compiled = (
        rules
        if isinstance(rules, CompiledWriteRules)
        else compile_write_rules(rules, operators=operators, case_insensitive=case_insensitive)
    )
    decision = WriteDecision()
    change = subject.get("change") or {}
    page = subject.get("page") or {}
    path = str(page.get("path") or "")
    deleting = change.get("op") == KnownWikiChangeOps.DELETE
    for item in compiled.rules:
        rule = item.rule
        if rule.applies_to and not any(
            glob_match(g, path, case_insensitive=compiled.case_insensitive) for g in rule.applies_to
        ):
            continue
        if item.when is not None and not item.when(subject):
            continue
        has_checks = item.require is not None or bool(rule.deny_patterns)
        lines: list[int] = []
        if has_checks:
            if deleting:
                continue
            violated = False
            if item.require is not None and not item.require(subject):
                violated = True
            found = _deny_lines(item.patterns, content)
            if found is None:
                violated = True
            elif found:
                violated = True
                lines = found
            if not violated:
                continue
        reject = item.action == KnownWikiWriteActions.REJECT
        if rule_violation:
            code = KnownIssueCodes.WIKI_RULE_VIOLATION
        elif reject:
            code = KnownIssueCodes.WIKI_RULE_REJECTED
        else:
            code = KnownIssueCodes.WIKI_RULE_WARNING
        decision.results.append(
            WikiRuleResult(rule_id=rule.id, action=item.action, message=rule.message, lines=lines)
        )
        decision.issues.append(
            WikiIssue(
                severity="error" if reject else "warning",
                code=code,
                message=rule.message or f"쓰기 규칙 '{rule.id}'에 걸렸습니다.",
                page=path or None,
                line=lines[0] if lines else None,
                rule_id=rule.id,
                details={
                    "rule": item.rule_id,
                    "message": rule.message,
                    "lines": lines,
                    "action": item.action,
                },
            )
        )
        if not item.known_action:
            decision.issues.append(
                WikiIssue(
                    severity="warning",
                    code=KnownIssueCodes.WIKI_UNKNOWN_ACTION,
                    message=(
                        f"쓰기 규칙 '{rule.id}'의 동작 '{rule.action}'을 몰라 경고로 읽었습니다."
                    ),
                    page=path or None,
                    rule_id=rule.id,
                    details={"value": rule.action},
                )
            )
        if reject:
            decision.rejected = True
    return decision


# ---------------------------------------------------------------- 비밀 검사


@dataclass(frozen=True, slots=True)
class SecretScan:
    """비밀 의심 검사 결과(값 없음).

    Attributes:
        found: 의심 값이 있다.
        lines: 의심 줄 번호(1부터). 여러 줄에 걸친 값(PEM 등)은 못 정할 수 있다(빈 목록).
    """

    found: bool
    lines: tuple[int, ...] = ()


@runtime_checkable
class WikiSecretScanner(Protocol):
    """페이지 본문 비밀 의심 판정기(주입). 값을 돌려주지 않는다."""

    def scan(self, text: str) -> SecretScan:
        """본문을 훑는다."""
        ...

    def redact(self, text: str) -> str:
        """의심 부분을 가린 글."""
        ...


@dataclass(frozen=True, slots=True)
class SecretRulesScanner:
    """`ac-secret-rules` 규칙으로 판정한다(사용자 규칙은 `SecretRules.with_extra`)."""

    rules: SecretRules = field(default_factory=default_rules)

    def scan(self, text: str) -> SecretScan:
        if not text or not self.rules.value_suspected(text):
            return SecretScan(False)
        lines = tuple(
            n for n, line in enumerate(text.splitlines(), 1) if self.rules.value_suspected(line)
        )
        return SecretScan(True, lines)

    def redact(self, text: str) -> str:
        return self.rules.redact_suspected(text)


def _default_modes() -> dict[str, str]:
    return dict(WikiSettings().secret_scan)


@dataclass(frozen=True, slots=True)
class WikiSecretPolicy:
    """쓴 주체 종류별 비밀 검사 방식(사용자 설정 `wiki.secret_scan`).

    Attributes:
        modes: 쓴 주체 종류 → `off`·`warn`·`reject`. 없는 종류는 `user` 값, 그것도 없으면 `off`.
            기본값은 계약 `WikiSettings` 기본값(코드에 따로 두지 않는다).
        scanner: 판정기.
    """

    modes: Mapping[str, str] = field(default_factory=_default_modes)
    scanner: WikiSecretScanner = field(default_factory=SecretRulesScanner)

    def mode(self, author_kind: str) -> str:
        """그 쓴 주체 종류의 방식."""
        return self.modes.get(author_kind, self.modes.get(KnownWikiAuthorKinds.USER, "off"))

    def check(self, text: str, author_kind: str, *, page: str | None = None) -> WriteDecision:
        """본문 비밀 검사. reject → error `wiki.secret_rejected`(rejected), warn → warning
        `wiki.secret_suspect`. 줄 번호만 싣는다."""
        mode = self.mode(author_kind)
        decision = WriteDecision()
        if mode not in ("warn", "reject"):
            return decision
        result = self.scanner.scan(text)
        if not result.found:
            return decision
        reject = mode == "reject"
        decision.issues.append(
            WikiIssue(
                severity="error" if reject else "warning",
                code=KnownIssueCodes.WIKI_SECRET_REJECTED
                if reject
                else KnownIssueCodes.WIKI_SECRET_SUSPECT,
                message="비밀로 보이는 값이 있습니다. 비밀은 위키에 쓰지 마세요.",
                page=page,
                line=result.lines[0] if result.lines else None,
                details={"lines": list(result.lines)},
            )
        )
        decision.rejected = reject
        return decision

    def redact(self, text: str) -> str:
        """조각·도구 결과용 가림."""
        return self.scanner.redact(text)


# ---------------------------------------------------------------- X50


@runtime_checkable
class WikiWriteCheck(Protocol):
    """위키 쓰기 검사 보탬. 쓰기 규칙·비밀 검사 뒤에 차례로 부른다.

    `check`가 돌려준 이슈 중 `severity=error`는 거부(`wiki.rule_rejected`와 같이 다룸), 나머지는
    경고로 쓰기와 함께 보인다. 이슈 `rule_id`가 비면 검사 `id`를 넣는다. 예외를 던지면 그 검사만
    건너뛰고 경고 이슈를 남긴다.
    """

    @property
    def id(self) -> str:
        """검사 id(설정 `wiki.write_checks[].id`)."""
        ...

    def check(self, subject: Mapping[str, Any], text: str) -> Sequence[WikiIssue]:
        """판단 대상(`write_subject`)과 새 본문(지우기는 빈 문자열)을 본다."""
        ...


def run_write_checks(
    checks: Sequence[WikiWriteCheck], subject: Mapping[str, Any], text: str
) -> WriteDecision:
    """X50 검사들을 차례로 부른다(모듈 문서 `WikiWriteCheck`의 규칙)."""
    decision = WriteDecision()
    page = (subject.get("page") or {}).get("path")
    for check in checks:
        check_id = str(getattr(check, "id", "") or type(check).__name__)
        try:
            found = list(check.check(subject, text))
        except Exception as exc:  # 확장 하나의 오류가 쓰기 전체를 막지 않게
            decision.issues.append(
                WikiIssue(
                    severity="warning",
                    code=KnownIssueCodes.WIKI_RULE_WARNING,
                    message=f"쓰기 검사 '{check_id}'가 실패해 건너뛰었습니다: {type(exc).__name__}",
                    page=page,
                    rule_id=check_id,
                )
            )
            continue
        for issue in found:
            update: dict[str, Any] = {}
            if not issue.rule_id:
                update["rule_id"] = check_id
            if issue.page is None and page:
                update["page"] = page
            fixed = issue.model_copy(update=update) if update else issue
            decision.issues.append(fixed)
            if fixed.severity == "error":
                decision.rejected = True
                decision.results.append(
                    WikiRuleResult(
                        rule_id=fixed.rule_id or check_id,
                        action=KnownWikiWriteActions.REJECT,
                        message=fixed.message,
                        lines=[fixed.line] if fixed.line else [],
                    )
                )
    return decision
