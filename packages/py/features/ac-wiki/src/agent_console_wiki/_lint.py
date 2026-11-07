"""위키 점검(design §7R.1.1·§7R.18 Q18): 기본 점검 + 점검 규칙 + 쓰기 규칙 다시 보기.

- 기본 점검 셋(코드 개념, 켜기·심각도는 문법 데이터 `lint.builtin`): `broken_link`(끊긴 링크마다, 줄
  번호), `orphan`(고아 페이지), `duplicate_title`(같은 제목 페이지마다). 이슈 코드는 `wiki.<이름>`.
- 점검 규칙(`lint_rules`): 점검 판단 대상(`lint_subject`)에 `when`이 참인 페이지마다
  `wiki.lint_rule`.
- 쓰기 규칙 다시 보기(문법 `lint.write_rules`, 패키지 기본 켜짐): 모든 페이지에 쓰기 규칙을 돌린다 —
  판단 대상 `change.op=update`, 쓴 주체 = 그 페이지 마지막 기록의 쓴 주체(없으면 `external`),
  `before=null`. 걸리면 `wiki.rule_violation`(reject → error, warn → warning, 줄 번호). 앱 밖에서
  고친 파일의 규칙 위반이 여기서 보인다.
- 부분 실패(0.14.2): 페이지 하나의 점검이 예외로 끝나면 그 페이지만 건너뛰고(`skipped`,
  `wiki.lint_failed`) 나머지는 그대로 낸다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

from agent_console_conditions import ConditionOperator, compile_conditions
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.definitions import IssueSeverity
from agent_console_contracts.wiki import (
    KnownWikiAuthorKinds,
    KnownWikiChangeOps,
    KnownWikiLintChecks,
    KnownWikiLintCodes,
    WikiAuthor,
    WikiIssue,
    WikiLintReport,
)

from ._index import WikiIndex
from ._parse import ParsedPage
from ._ruleset import EffectiveWikiRules, default_operator_map
from ._subjects import lint_subject, write_subject
from ._writecheck import CompiledWriteRules, check_write, compile_write_rules

__all__ = ["PageTimes", "lint"]

_DAY = 86_400.0


@dataclass(frozen=True, slots=True)
class PageTimes:
    """점검 판단 대상의 시간·쓴 주체(기록 요약이나 파일 시각에서 호출자가 채운다).

    Attributes:
        created_at: 첫 기록 시각(모르면 None → `age_days` null).
        updated_at: 마지막 변경 시각(모르면 None → `idle_days` null).
        updated_by: 마지막으로 쓴 쪽(모르면 None).
    """

    created_at: float | None = None
    updated_at: float | None = None
    updated_by: WikiAuthor | None = None


def _days(now: float, at: float | None) -> float | None:
    return None if at is None else max(0.0, (now - at) / _DAY)


def lint(
    index: WikiIndex,
    rules: EffectiveWikiRules | None = None,
    *,
    now: float,
    times: Mapping[str, PageTimes] | None = None,
    read: Callable[[str], str | None] | None = None,
    operators: Mapping[str, ConditionOperator] | None = None,
    write_rules: CompiledWriteRules | None = None,
) -> WikiLintReport:
    """위키 하나를 점검한다(서버 없이 쓰는 순수 함수).

    Args:
        index: 링크 색인.
        rules: 합친 규칙(점검 규칙·쓰기 규칙). None이면 기본 점검만.
        now: 지금 시각(유닉스 초, `age_days`·`idle_days`·`generated_at`).
        times: 페이지 경로 → 시간·쓴 주체.
        read: 페이지 경로 → 본문(쓰기 규칙 금지 패턴을 다시 볼 때). None이면 금지 패턴은 보지
        않는다. operators: 조건 연산자(기본 `default_operator_map()`).
        write_rules: 미리 컴파일한 쓰기 규칙(None이면 `rules`에서 컴파일).

    Returns:
        `WikiLintReport`(이슈는 페이지 경로 순 → 기본 점검 → 점검 규칙 → 쓰기 규칙, `counts` =
        심각도별 수, `enabled_checks` = 켜진 기본 점검 → `lint_rules` → `write_rules`). 페이지
        하나를 점검하다 예외가 나면(본문 읽기 실패 등) 그 페이지 이슈는 버리고 `wiki.lint_failed`
        하나를 남긴 뒤 다음 페이지로 간다(`skipped`·`partial`).
    """
    syntax = index.syntax
    ops = operators if operators is not None else default_operator_map()
    times = times or {}
    builtin = syntax.builtin_lint
    issues: list[WikiIssue] = []

    broken = cast(IssueSeverity | None, builtin.get(KnownWikiLintCodes.BROKEN_LINK))
    orphan = cast(IssueSeverity | None, builtin.get(KnownWikiLintCodes.ORPHAN))
    dup = cast(IssueSeverity | None, builtin.get(KnownWikiLintCodes.DUPLICATE_TITLE))
    dup_groups: dict[str, list[str]] = {}
    if dup:
        for group in index.duplicate_titles:
            for path in group:
                dup_groups[path] = group

    lint_rules = [
        (sourced, compile_conditions(sourced.item.when, ops))
        for sourced in (rules.lint_rules if rules is not None else [])
    ]
    compiled_write = write_rules
    if compiled_write is None and rules is not None and syntax.lint_write_rules:
        compiled_write = compile_write_rules(
            rules, operators=ops, case_insensitive=syntax.case_insensitive
        )
    if not syntax.lint_write_rules:
        compiled_write = None
    external = WikiAuthor(kind=KnownWikiAuthorKinds.EXTERNAL)

    def check_page(path: str, page: ParsedPage) -> list[WikiIssue]:
        found: list[WikiIssue] = []
        if broken:
            for item in index.links.get(path, ()):
                if not item.broken:
                    continue
                found.append(
                    WikiIssue(
                        severity=broken,
                        code=f"wiki.{KnownWikiLintCodes.BROKEN_LINK}",
                        message=f"없는 페이지를 가리킵니다: {item.link.target}",
                        page=path,
                        line=item.link.line,
                        details={
                            "target": item.link.target,
                            "suggested_path": item.suggested_path,
                        },
                    )
                )
        if orphan and path in index.orphans:
            found.append(
                WikiIssue(
                    severity=orphan,
                    code=f"wiki.{KnownWikiLintCodes.ORPHAN}",
                    message="이 페이지를 가리키는 링크가 없습니다.",
                    page=path,
                )
            )
        if dup and path in dup_groups:
            group = dup_groups[path]
            found.append(
                WikiIssue(
                    severity=dup,
                    code=f"wiki.{KnownWikiLintCodes.DUPLICATE_TITLE}",
                    message=f"같은 제목의 페이지가 있습니다: {page.title}",
                    page=path,
                    details={"title": page.title, "pages": [p for p in group if p != path]},
                )
            )
        if not lint_rules and compiled_write is None:
            return found
        facts = index.facts(path)
        info = times.get(path, PageTimes())
        if lint_rules:
            subject = lint_subject(
                facts,
                backlinks=len(index.incoming.get(path, {})),
                age_days=_days(now, info.created_at),
                idle_days=_days(now, info.updated_at),
                updated_by_kind=info.updated_by.kind if info.updated_by else None,
            )
            for sourced, holds in lint_rules:
                if holds(subject):
                    rule = sourced.item
                    found.append(
                        WikiIssue(
                            severity=rule.severity,
                            code=KnownIssueCodes.WIKI_LINT_RULE,
                            message=rule.message or f"점검 규칙 '{rule.id}'에 걸렸습니다.",
                            page=path,
                            rule_id=rule.id,
                            details={"rule": sourced.rule_id},
                        )
                    )
        if compiled_write is not None and compiled_write.rules:
            content = ""
            if compiled_write.needs_content and read is not None:
                content = read(path) or ""
            subject = write_subject(
                op=KnownWikiChangeOps.UPDATE,
                author=info.updated_by or external,
                page=facts,
                before=None,
            )
            decision = check_write(compiled_write, subject, content=content, rule_violation=True)
            found.extend(
                i for i in decision.issues if i.code == KnownIssueCodes.WIKI_RULE_VIOLATION
            )
        return found

    skipped: list[str] = []
    for path, page in index.pages.items():
        try:
            issues.extend(check_page(path, page))
        except Exception as exc:  # 한 페이지 실패가 점검 전체를 막지 않는다
            # 그 페이지에서 모은 이슈는 버린다(반쯤 본 결과를 섞지 않는다). 사유는 예외 종류 이름만
            # 남긴다(메시지에 경로·값 원문이 섞일 수 있다).
            skipped.append(path)
            issues.append(
                WikiIssue(
                    severity="warning",
                    code=KnownIssueCodes.WIKI_LINT_FAILED,
                    message="이 페이지를 점검하지 못했습니다.",
                    page=path,
                    details={"reason": type(exc).__name__},
                )
            )

    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    enabled = [name for name, severity in builtin.items() if severity]
    if lint_rules:
        enabled.append(KnownWikiLintChecks.LINT_RULES)
    if compiled_write is not None and compiled_write.rules:
        enabled.append(KnownWikiLintChecks.WRITE_RULES)
    return WikiLintReport(
        issues=issues,
        pages=len(index.pages),
        generated_at=now,
        counts=counts,
        partial=bool(skipped),
        skipped=skipped,
        enabled_checks=enabled,
    )
