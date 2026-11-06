"""유효 위키 문법을 한 번 컴파일한 형태(파싱·링크 해석·이름 바꾸기·링크 글 만들기가 함께 쓴다).

사용자 정규식은 모두 `ac-safe-regex`로 컴파일한다(시간·길이 상한). 쓸 수 없는 링크 패턴은
`wiki.link_pattern_invalid`(error)를 내고 그 링크 규칙만 뺀다. 모르는 `kind`·`resolve` 값은
`wiki.unknown_link_kind`(warning)를 내고 그 규칙·값만 건너뛴다. `orphan_ignore`의 틀린 글롭은
`wiki.invalid_glob`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import (
    EffectiveWikiSyntax,
    KnownWikiFrontMatterRoles,
    KnownWikiLinkKinds,
    KnownWikiLintCodes,
    KnownWikiResolvers,
    KnownWikiTitleSources,
    WikiIssue,
    WikiScheme,
)
from agent_console_safe_regex import (
    DEFAULT_TIMEOUT_SECONDS,
    SafePattern,
    UnsafeRegexError,
    compile_user_regex,
)

from ._glob import check_glob

__all__ = [
    "DEFAULT_MAX_INPUT_CHARS",
    "KNOWN_LINK_KINDS",
    "KNOWN_RESOLVERS",
    "KNOWN_TITLE_SOURCES",
    "CompiledLinkRule",
    "CompiledWikiSyntax",
    "compile_syntax",
]

KNOWN_LINK_KINDS: frozenset[str] = frozenset(
    {KnownWikiLinkKinds.PATTERN, KnownWikiLinkKinds.MARKDOWN}
)
"""파서가 다루는 링크 규칙 종류(코드 개념)."""

KNOWN_RESOLVERS: frozenset[str] = frozenset(
    {
        KnownWikiResolvers.PATH,
        KnownWikiResolvers.TITLE,
        KnownWikiResolvers.ALIAS,
        KnownWikiResolvers.RELATIVE_PATH,
    }
)
"""링크 대상 찾기 방법(코드 개념 넷). 순서·사용 여부는 데이터."""

KNOWN_TITLE_SOURCES: frozenset[str] = frozenset(
    {
        KnownWikiTitleSources.FRONT_MATTER,
        KnownWikiTitleSources.FIRST_HEADING,
        KnownWikiTitleSources.FILE_NAME,
    }
)
"""제목 출처(코드 개념 셋). 모르는 값은 건너뛴다."""

DEFAULT_MAX_INPUT_CHARS = 4_000_000
"""링크 패턴이 한 번에 훑는 글자 수 상한(문단 하나 기준이라 넉넉하다)."""


@dataclass(frozen=True, slots=True)
class CompiledLinkRule:
    """컴파일한 링크 규칙 하나.

    Attributes:
        id: 링크 규칙 id(데이터).
        kind: `pattern` 또는 `markdown`.
        pattern: `pattern` 종류의 정규식(`target` 묶음 필수, `label`·`anchor` 선택).
        resolve: 대상 찾는 순서(알려진 값만).
        insert: 링크 넣기 틀(없으면 None).
        groups: 패턴의 이름 묶음(`target`·`label`·`anchor` 등).
    """

    id: str
    kind: str
    pattern: SafePattern | None
    resolve: tuple[str, ...]
    insert: str | None
    groups: frozenset[str] = frozenset()


@dataclass(slots=True)
class CompiledWikiSyntax:
    """컴파일한 유효 위키 문법. `compile_syntax`로 만든다.

    Attributes:
        effective: 원래 유효 문법(+ 컴파일 이슈, `empty`는 쓸 수 있는 링크 규칙 기준).
        links: 쓸 수 있는 링크 규칙(문법 순서).
        delimiter: 머리말 구분 줄(None = 머리말 읽지 않음).
        roles: 머리말 역할(`title`·`tags`·`aliases`) → 머리말 키.
        title_sources: 제목 출처 순서(알려진 값만).
        page_extensions: 페이지 확장자(문법 순서, 첫 것이 새 페이지 확장자).
        case_insensitive: 경로·제목·별칭 비교에서 대소문자 무시.
        schemes: 링크 스킴(접두가 긴 것부터).
        builtin_lint: 기본 점검 이름 → 심각도(None = 끔).
        lint_write_rules: 점검에서 쓰기 규칙 다시 보기.
        orphan_ignore: 고아 점검에서 뺄 경로 글롭(형식이 맞는 것만).
        issues: 컴파일 이슈(`effective.issues`와 같다).
    """

    effective: EffectiveWikiSyntax
    links: tuple[CompiledLinkRule, ...]
    delimiter: str | None
    roles: dict[str, str]
    title_sources: tuple[str, ...]
    page_extensions: tuple[str, ...]
    case_insensitive: bool
    schemes: tuple[WikiScheme, ...]
    builtin_lint: dict[str, str | None]
    lint_write_rules: bool
    orphan_ignore: tuple[str, ...]
    issues: list[WikiIssue] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        """쓸 수 있는 링크 규칙이 없다."""
        return not self.links

    def key(self, value: str) -> str:
        """비교 키(대소문자 무시면 casefold)."""
        return value.casefold() if self.case_insensitive else value

    def rule(self, rule_id: str) -> CompiledLinkRule | None:
        """id로 링크 규칙을 찾는다."""
        for rule in self.links:
            if rule.id == rule_id:
                return rule
        return None

    @property
    def new_page_extension(self) -> str:
        """새 페이지 파일 확장자(첫 페이지 확장자, 없으면 빈 문자열)."""
        return self.page_extensions[0] if self.page_extensions else ""


def _issue(code: str, message: str, *, severity: str, path: str, **details: Any) -> WikiIssue:
    return WikiIssue.model_validate(
        {"severity": severity, "code": code, "message": message, "path": path, "details": details}
    )


def compile_syntax(
    syntax: EffectiveWikiSyntax,
    *,
    regex_timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
) -> CompiledWikiSyntax:
    """유효 문법을 컴파일한다. 잘못된 부분은 이슈로 내고 그 부분만 없는 것으로 본다.

    Args:
        syntax: `merge_syntax`·`effective_syntax` 결과.
        regex_timeout: 링크 패턴 훑기 1회 시간 상한(초).
        max_input_chars: 링크 패턴이 한 번에 훑는 글자 수 상한.

    Returns:
        `CompiledWikiSyntax`. `effective.issues`에 컴파일 이슈를 더하고, 쓸 수 있는 링크 규칙이
        없으면 `effective.empty`가 참이고 `wiki.syntax_missing`이 있다.
    """
    issues: list[WikiIssue] = list(syntax.issues)
    data = syntax.syntax
    rules: list[CompiledLinkRule] = []
    seen: set[str] = set()
    for i, rule in enumerate(data.links or ()):
        where = f"/links/{i}"
        if rule.id in seen:
            issues.append(
                _issue(
                    KnownIssueCodes.WIKI_DUPLICATE_RULE_ID,
                    f"링크 규칙 id '{rule.id}'가 겹쳐 앞의 것만 씁니다.",
                    severity="warning",
                    path=where,
                    id=rule.id,
                )
            )
            continue
        if rule.kind not in KNOWN_LINK_KINDS:
            issues.append(
                _issue(
                    KnownIssueCodes.WIKI_UNKNOWN_LINK_KIND,
                    f"링크 규칙 '{rule.id}'의 찾는 방법 '{rule.kind}'를 몰라 건너뜁니다.",
                    severity="warning",
                    path=f"{where}/kind",
                    value=rule.kind,
                )
            )
            continue
        pattern: SafePattern | None = None
        if rule.kind == KnownWikiLinkKinds.PATTERN:
            try:
                if not rule.pattern:
                    raise UnsafeRegexError("패턴이 비어 있습니다")
                pattern = compile_user_regex(
                    rule.pattern,
                    required_groups=("target",),
                    timeout=regex_timeout,
                    max_input_chars=max_input_chars,
                )
            except UnsafeRegexError as exc:
                issues.append(
                    _issue(
                        KnownIssueCodes.WIKI_LINK_PATTERN_INVALID,
                        f"링크 규칙 '{rule.id}'의 패턴을 쓸 수 없어 이 규칙을 뺍니다: {exc}",
                        severity="error",
                        path=f"{where}/pattern",
                    )
                )
                continue
        resolve: list[str] = []
        for j, value in enumerate(rule.resolve):
            if value in KNOWN_RESOLVERS:
                if value not in resolve:
                    resolve.append(value)
                continue
            issues.append(
                _issue(
                    KnownIssueCodes.WIKI_UNKNOWN_LINK_KIND,
                    f"링크 규칙 '{rule.id}'의 대상 찾기 '{value}'를 몰라 건너뜁니다.",
                    severity="warning",
                    path=f"{where}/resolve/{j}",
                    value=value,
                )
            )
        seen.add(rule.id)
        rules.append(
            CompiledLinkRule(
                id=rule.id,
                kind=rule.kind,
                pattern=pattern,
                resolve=tuple(resolve),
                insert=rule.insert or None,
                groups=pattern.group_names if pattern is not None else frozenset(),
            )
        )

    front = data.front_matter
    delimiter = front.delimiter if front and front.delimiter else None
    roles = {
        role: key
        for role, key in ((front.roles or {}) if front else {}).items()
        if key
        and role
        in (
            KnownWikiFrontMatterRoles.TITLE,
            KnownWikiFrontMatterRoles.TAGS,
            KnownWikiFrontMatterRoles.ALIASES,
        )
    }
    title_sources = tuple(
        dict.fromkeys(s for s in data.title_sources or () if s in KNOWN_TITLE_SOURCES)
    )
    extensions = tuple(dict.fromkeys(e for e in data.page_extensions or () if e))
    schemes = tuple(sorted(data.schemes or (), key=lambda s: len(s.prefix), reverse=True))

    lint = data.lint
    builtin: dict[str, str | None] = {code: None for code in _BUILTIN_LINT}
    if lint and lint.builtin:
        for code, severity in lint.builtin.items():
            if code in builtin:
                builtin[code] = severity
    orphan_ignore: list[str] = []
    for k, pattern_text in enumerate((lint.orphan_ignore if lint else None) or ()):
        problem = check_glob(pattern_text)
        if problem is None:
            orphan_ignore.append(pattern_text)
        else:
            issues.append(
                _issue(
                    KnownIssueCodes.WIKI_INVALID_GLOB,
                    f"고아 점검 제외 경로 모양을 쓸 수 없어 뺍니다: {problem}",
                    severity="error",
                    path=f"/lint/orphan_ignore/{k}",
                )
            )

    empty = not rules
    if empty and not syntax.empty:
        issues.append(
            _issue(
                KnownIssueCodes.WIKI_SYNTAX_MISSING,
                "쓸 수 있는 링크 규칙이 없어 링크·백링크·그래프를 만들지 않습니다.",
                severity="info",
                path="/links",
            )
        )
    effective = syntax.model_copy(update={"issues": issues, "empty": empty})
    return CompiledWikiSyntax(
        effective=effective,
        links=tuple(rules),
        delimiter=delimiter,
        roles=roles,
        title_sources=title_sources,
        page_extensions=extensions,
        case_insensitive=bool(data.case_insensitive),
        schemes=schemes,
        builtin_lint=builtin,
        lint_write_rules=bool(lint.write_rules) if lint and lint.write_rules is not None else False,
        orphan_ignore=tuple(orphan_ignore),
        issues=issues,
    )


_BUILTIN_LINT = (
    KnownWikiLintCodes.BROKEN_LINK,
    KnownWikiLintCodes.ORPHAN,
    KnownWikiLintCodes.DUPLICATE_TITLE,
)
