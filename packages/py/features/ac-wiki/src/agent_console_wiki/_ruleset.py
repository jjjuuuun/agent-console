"""위키 규칙 합치기·검사(design §7R.1.1·§7R.1.2·§7R.18 Q5).

- `merge_rules(rule_ids, documents)`: 위키의 `rules` 순서대로 규칙 문서를 합친다. 지침 본문은
  순서대로 이어 붙이고(각 앞에 규칙 이름 머리 줄 — 틀은 패키지 데이터 `data/rules_text.yaml`),
  쓰기·점검 규칙· 페이지 틀은 이어 붙인다(같은 id는 앞의 것 + `wiki.duplicate_rule_id`). 문법은 규칙
  순서대로 층이 된다(`syntax_layers` → `effective_syntax(rules=)`). 공간에 없는 규칙은
  `wiki.rules_missing`(그 규칙만 빠짐).
- `check_rules(document, files=, operators=)`: 규칙 문서 하나를 저장 전에 검사한다.
- `load_wiki_rules(store, rule_ids, kind=)`: 정의 저장소(`ac-store` `DefinitionStore`)에서 규칙
  문서와 본문 파일을 읽는다(새 저장소를 두지 않는다 — SDD `SpecRepository`와 같은 길).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAML

from agent_console_conditions import ConditionOperator, builtin_operators, condition_issues
from agent_console_contracts import ConditionSpec
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import (
    WIKI_TEMPLATE_BUILTIN_VARIABLES,
    KnownWikiRuleEntryKinds,
    KnownWikiWriteActions,
    WikiIssue,
    WikiLintRule,
    WikiPageTemplate,
    WikiPageTemplateInfo,
    WikiRuleEntry,
    WikiRuleRef,
    WikiRulesDefinition,
    WikiRulesSummary,
    WikiSyntax,
    WikiTemplateVariable,
    WikiWriteRule,
)
from agent_console_safe_regex import UnsafeRegexError, check_user_regex
from agent_console_store import DefinitionStore, NotFound
from agent_console_text_template import render_template, template_variables

from ._compiled import compile_syntax
from ._glob import check_glob
from ._syntax import merge_syntax

__all__ = [
    "RULES_TEXT_RESOURCE",
    "EffectiveWikiRules",
    "RulesDocument",
    "Sourced",
    "check_rules",
    "default_operator_map",
    "load_wiki_rules",
    "merge_rules",
    "rules_text",
]

RULES_TEXT_RESOURCE = "data/rules_text.yaml"
"""패키지 기본 문구(지침 머리 줄 틀 등)의 패키지 안 위치."""

_SYNTAX_CODES = frozenset(
    {
        KnownIssueCodes.WIKI_LINK_PATTERN_INVALID,
        KnownIssueCodes.WIKI_UNKNOWN_LINK_KIND,
        KnownIssueCodes.WIKI_INVALID_GLOB,
        KnownIssueCodes.WIKI_DUPLICATE_RULE_ID,
    }
)


@cache
def _rules_text() -> Mapping[str, Any]:
    text = (resources.files("agent_console_wiki") / RULES_TEXT_RESOURCE).read_text(encoding="utf-8")
    data = YAML(typ="safe").load(text)
    return data if isinstance(data, dict) else {}


def default_operator_map() -> dict[str, ConditionOperator]:
    """기본 조건 연산자(`ac-conditions` 기본 10개, entry point 없이) id → 연산자. 서버 조립은
    설정으로 끄고 더한 연산자 레지스트리를 넘긴다."""
    return {op.descriptor.id: op for op in builtin_operators()}


def rules_text(key: str) -> str:
    """패키지 기본 문구 하나(`data/rules_text.yaml`). 없으면 빈 문자열."""
    value = _rules_text().get(key)
    return value if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class RulesDocument:
    """위키 규칙 문서 하나와 본문 파일.

    Attributes:
        id: 규칙 id.
        definition: 규칙 정의.
        files: 본문 폴더 파일(상대 경로 → 글 또는 UTF-8 바이트). 지침·페이지 틀 본문.
    """

    id: str
    definition: WikiRulesDefinition
    files: Mapping[str, str | bytes] = field(default_factory=dict)

    def text(self, file: str) -> str | None:
        """본문 파일 하나(없으면 None)."""
        value = self.files.get(file)
        if value is None:
            return None
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


@dataclass(frozen=True, slots=True)
class Sourced[T]:
    """합친 항목 하나와 그것을 준 규칙 id."""

    rule_id: str
    item: T


@dataclass(slots=True)
class EffectiveWikiRules:
    """위키가 쓰는 규칙을 합친 결과(`merge_rules`).

    Attributes:
        refs: 위키의 규칙 순서 그대로(없는 규칙은 `missing`).
        instructions: 합친 지침 본문(규칙 이름 머리 줄 포함, 없으면 빈 문자열).
        write_rules: 합친 쓰기 규칙(규칙 순서 → 규칙 안 순서).
        lint_rules: 합친 점검 규칙.
        templates: 합친 페이지 틀.
        template_contents: 틀 id → 틀 본문(파일이 없으면 None).
        syntax_layers: (규칙 id, 그 규칙 문법) — `effective_syntax(rules=)`에 그대로.
        entries: 합친 항목 목록(쓰기 → 점검 → 틀).
        issues: 합치기 이슈(`wiki.rules_missing`·`wiki.duplicate_rule_id`·`wiki.template_missing`).
    """

    refs: list[WikiRuleRef] = field(default_factory=list)
    instructions: str = ""
    write_rules: list[Sourced[WikiWriteRule]] = field(default_factory=list)
    lint_rules: list[Sourced[WikiLintRule]] = field(default_factory=list)
    templates: list[Sourced[WikiPageTemplate]] = field(default_factory=list)
    template_contents: dict[str, str | None] = field(default_factory=dict)
    syntax_layers: list[tuple[str, WikiSyntax | None]] = field(default_factory=list)
    entries: list[WikiRuleEntry] = field(default_factory=list)
    issues: list[WikiIssue] = field(default_factory=list)

    def summary(self) -> WikiRulesSummary:
        """계약 요약(`WikiView.rules`)."""
        return WikiRulesSummary(
            rules=list(self.refs),
            instructions=self.instructions,
            write_rules=len(self.write_rules),
            lint_rules=len(self.lint_rules),
            page_templates=len(self.templates),
            entries=list(self.entries),
        )

    def template(self, template_id: str) -> Sourced[WikiPageTemplate] | None:
        """id로 페이지 틀을 찾는다."""
        return next((t for t in self.templates if t.item.id == template_id), None)

    def template_infos(self) -> list[WikiPageTemplateInfo]:
        """`GET …/templates` 항목들(변수 = 선언 + 틀이 쓰는 이름, 앱이 채우는 이름은 builtin)."""
        out: list[WikiPageTemplateInfo] = []
        for sourced in self.templates:
            tpl = sourced.item
            content = self.template_contents.get(tpl.id) or ""
            out.append(
                WikiPageTemplateInfo(
                    id=tpl.id,
                    title=tpl.title,
                    file=tpl.file,
                    path=tpl.path,
                    variables=template_variable_infos(tpl, content),
                    rule_id=sourced.rule_id,
                    content=content,
                )
            )
        return out


def template_variable_infos(template: WikiPageTemplate, content: str) -> list[WikiTemplateVariable]:
    """틀 변수 목록: 선언한 것(순서대로) + 틀 본문·경로 틀이 쓰는 이름(이름 순). 앱이 채우는
    이름(`WIKI_TEMPLATE_BUILTIN_VARIABLES`)은 `builtin=True`."""
    builtin = set(WIKI_TEMPLATE_BUILTIN_VARIABLES)
    out: list[WikiTemplateVariable] = []
    seen: set[str] = set()
    for var in template.variables:
        if var.name in seen:
            continue
        seen.add(var.name)
        out.append(var.model_copy(update={"builtin": var.name in builtin}))
    used = template_variables([content, template.path or ""])
    for name in sorted(used - seen):
        out.append(WikiTemplateVariable(name=name, builtin=name in builtin))
    return out


def _issue(code: str, message: str, *, severity: str, **kw: Any) -> WikiIssue:
    return WikiIssue.model_validate({"severity": severity, "code": code, "message": message, **kw})


def merge_rules(
    rule_ids: Sequence[str],
    documents: Mapping[str, RulesDocument] | Sequence[RulesDocument],
    *,
    header: str | None = None,
    separator: str | None = None,
) -> EffectiveWikiRules:
    """위키의 규칙 목록을 순서대로 합친다(서버 없이 쓰는 순수 함수).

    Args:
        rule_ids: 위키 정의의 `rules`(순서대로, 겹친 id는 한 번만).
        documents: 공간에 있는 규칙 문서(id → 문서, 또는 목록).
        header: 지침 머리 줄 틀(`{name}`·`{id}`). None = 패키지 데이터 `instructions_header`.
        separator: 지침 사이 구분. None = 패키지 데이터 `instructions_separator`.

    Returns:
        `EffectiveWikiRules`.
    """
    docs = (
        dict(documents)
        if isinstance(documents, Mapping)
        else {document.id: document for document in documents}
    )
    head = rules_text("instructions_header") if header is None else header
    sep = rules_text("instructions_separator") if separator is None else separator
    out = EffectiveWikiRules()
    parts: list[str] = []
    seen_rules: set[str] = set()
    seen: dict[str, dict[str, str]] = {
        KnownWikiRuleEntryKinds.WRITE: {},
        KnownWikiRuleEntryKinds.LINT: {},
        KnownWikiRuleEntryKinds.TEMPLATE: {},
    }

    def taken(kind: str, item_id: str, rule_id: str, where: str) -> bool:
        first = seen[kind].get(item_id)
        if first is None:
            seen[kind][item_id] = rule_id
            return False
        out.issues.append(
            _issue(
                KnownIssueCodes.WIKI_DUPLICATE_RULE_ID,
                f"'{item_id}'가 규칙 '{first}'에 이미 있어 '{rule_id}'의 것은 뺍니다.",
                severity="warning",
                path=where,
                rule_id=item_id,
                details={"kind": kind, "id": item_id, "kept": first, "dropped": rule_id},
            )
        )
        return True

    for rule_id in rule_ids:
        if rule_id in seen_rules:
            continue
        seen_rules.add(rule_id)
        document = docs.get(rule_id)
        if document is None:
            out.refs.append(WikiRuleRef(id=rule_id, missing=True))
            out.issues.append(
                _issue(
                    KnownIssueCodes.WIKI_RULES_MISSING,
                    f"위키 규칙 '{rule_id}'가 이 공간에 없어 빼고 씁니다.",
                    severity="warning",
                    path="/rules",
                    details={"id": rule_id},
                )
            )
            continue
        rules = document.definition
        out.refs.append(WikiRuleRef(id=rule_id, name=rules.name))
        if rules.instructions is not None:
            text = document.text(rules.instructions.file)
            if text is None:
                out.issues.append(
                    _issue(
                        KnownIssueCodes.WIKI_TEMPLATE_MISSING,
                        f"규칙 '{rule_id}'의 지침 본문 파일이 없습니다.",
                        severity="warning",
                        path="/instructions/file",
                        details={"rule": rule_id, "file": rules.instructions.file},
                    )
                )
            elif text.strip():
                title = render_template(head, {"name": rules.name, "id": rule_id}) if head else ""
                parts.append(f"{title}\n\n{text.strip()}" if title else text.strip())
        for i, rule in enumerate(rules.write_rules):
            if taken(KnownWikiRuleEntryKinds.WRITE, rule.id, rule_id, f"/write_rules/{i}/id"):
                continue
            out.write_rules.append(Sourced(rule_id, rule))
            out.entries.append(
                WikiRuleEntry(
                    kind=KnownWikiRuleEntryKinds.WRITE,
                    id=rule.id,
                    rule_id=rule_id,
                    label=rule.message,
                    action=rule.action,
                    applies_to=list(rule.applies_to),
                )
            )
        for i, lint_rule in enumerate(rules.lint_rules):
            if taken(KnownWikiRuleEntryKinds.LINT, lint_rule.id, rule_id, f"/lint_rules/{i}/id"):
                continue
            out.lint_rules.append(Sourced(rule_id, lint_rule))
            out.entries.append(
                WikiRuleEntry(
                    kind=KnownWikiRuleEntryKinds.LINT,
                    id=lint_rule.id,
                    rule_id=rule_id,
                    label=lint_rule.message,
                    severity=lint_rule.severity,
                )
            )
        for i, tpl in enumerate(rules.page_templates):
            if taken(KnownWikiRuleEntryKinds.TEMPLATE, tpl.id, rule_id, f"/page_templates/{i}/id"):
                continue
            out.templates.append(Sourced(rule_id, tpl))
            content = document.text(tpl.file)
            out.template_contents[tpl.id] = content
            if content is None:
                out.issues.append(
                    _issue(
                        KnownIssueCodes.WIKI_TEMPLATE_MISSING,
                        f"규칙 '{rule_id}'의 페이지 틀 '{tpl.id}' 파일이 없습니다.",
                        severity="warning",
                        path=f"/page_templates/{i}/file",
                        details={"rule": rule_id, "id": tpl.id, "file": tpl.file},
                    )
                )
            out.entries.append(
                WikiRuleEntry(
                    kind=KnownWikiRuleEntryKinds.TEMPLATE,
                    id=tpl.id,
                    rule_id=rule_id,
                    label=tpl.title or tpl.id,
                    path=tpl.path or None,
                    title=tpl.title or None,
                )
            )
        out.syntax_layers.append((rule_id, rules.syntax))
    out.instructions = sep.join(parts)
    return out


def _empty_condition(spec: ConditionSpec | None) -> bool:
    return spec is None or (not spec.all and not spec.any)


def _condition_issues(
    spec: ConditionSpec,
    operators: Mapping[str, ConditionOperator],
    where: str,
    rule_id: str,
) -> list[WikiIssue]:
    return [
        WikiIssue.model_validate({**issue.model_dump(), "rule_id": rule_id})
        for issue in condition_issues(spec, operators, base_path=where)
    ]


def check_rules(
    document: WikiRulesDefinition | Mapping[str, Any],
    *,
    files: Collection[str] | None = None,
    operators: Mapping[str, ConditionOperator] | None = None,
) -> list[WikiIssue]:
    """위키 규칙 문서 하나를 저장 전에 검사한다(design §7R.1.1 "규칙 검사").

    Args:
        document: 규칙 문서(모델 또는 dict — 계약 모양이 아니면 `validation_failed` 이슈 하나).
        files: 본문 폴더의 파일 목록. None이면 파일 존재는 보지 않는다.
        operators: 조건 연산자(기본 `builtin_operators()`).

    Returns:
        이슈 목록. 정규식 오류 `wiki.invalid_pattern`(error), 글롭 `wiki.invalid_glob`(error), 같은
        id `wiki.duplicate_rule_id`(warning), 조건 `condition.*`, 모르는 동작 `wiki.unknown_action`
        (warning — warn으로 읽음), 늘 거부 `wiki.always_rejects`(error — 모든 쓰기를 막음), 페이지
        틀 파일 없음 `wiki.template_missing`(error), 경로 틀의 모르는 변수 `wiki.unknown_variable`
        (warning), 문법 패턴·글롭 오류(문법 층 하나만 컴파일해 본 것).
    """
    if not isinstance(document, WikiRulesDefinition):
        try:
            document = WikiRulesDefinition.model_validate(dict(document))
        except ValidationError as exc:
            return [
                _issue(
                    "validation_failed",
                    f"위키 규칙 모양이 아닙니다: {exc.error_count()}곳",
                    severity="error",
                    path="",
                )
            ]
    ops = operators if operators is not None else default_operator_map()
    issues: list[WikiIssue] = []

    def dup(items: Sequence[Any], base: str) -> None:
        seen: set[str] = set()
        for i, item in enumerate(items):
            if item.id in seen:
                issues.append(
                    _issue(
                        KnownIssueCodes.WIKI_DUPLICATE_RULE_ID,
                        f"id '{item.id}'가 겹칩니다. 앞의 것만 씁니다.",
                        severity="warning",
                        path=f"{base}/{i}/id",
                        rule_id=item.id,
                    )
                )
            seen.add(item.id)

    dup(document.write_rules, "/write_rules")
    dup(document.lint_rules, "/lint_rules")
    dup(document.page_templates, "/page_templates")

    for i, rule in enumerate(document.write_rules):
        base = f"/write_rules/{i}"
        for j, glob in enumerate(rule.applies_to):
            problem = check_glob(glob)
            if problem is not None:
                issues.append(
                    _issue(
                        KnownIssueCodes.WIKI_INVALID_GLOB,
                        f"경로 모양을 쓸 수 없습니다: {problem}",
                        severity="error",
                        path=f"{base}/applies_to/{j}",
                        rule_id=rule.id,
                    )
                )
        for j, pattern in enumerate(rule.deny_patterns):
            try:
                check_user_regex(pattern)
            except UnsafeRegexError as exc:
                issues.append(
                    _issue(
                        KnownIssueCodes.WIKI_INVALID_PATTERN,
                        f"금지 패턴을 쓸 수 없습니다: {exc}",
                        severity="error",
                        path=f"{base}/deny_patterns/{j}",
                        rule_id=rule.id,
                    )
                )
        if rule.when is not None and not _empty_condition(rule.when):
            issues.extend(_condition_issues(rule.when, ops, f"{base}/when", rule.id))
        if rule.require is not None:
            issues.extend(_condition_issues(rule.require, ops, f"{base}/require", rule.id))
        known = rule.action in (KnownWikiWriteActions.REJECT, KnownWikiWriteActions.WARN)
        if not known:
            issues.append(
                _issue(
                    KnownIssueCodes.WIKI_UNKNOWN_ACTION,
                    f"동작 '{rule.action}'을 몰라 경고(warn)로 읽습니다.",
                    severity="warning",
                    path=f"{base}/action",
                    rule_id=rule.id,
                    details={"value": rule.action},
                )
            )
        everywhere = not rule.applies_to or "**" in rule.applies_to
        if (
            rule.action == KnownWikiWriteActions.REJECT
            and everywhere
            and _empty_condition(rule.when)
            and rule.require is None
            and not rule.deny_patterns
        ):
            issues.append(
                _issue(
                    KnownIssueCodes.WIKI_ALWAYS_REJECTS,
                    "조건이 없어 모든 쓰기를 거부합니다. '걸 쓰기' 조건을 적으세요.",
                    severity="error",
                    path=f"{base}/when",
                    rule_id=rule.id,
                )
            )

    for i, lint_rule in enumerate(document.lint_rules):
        issues.extend(_condition_issues(lint_rule.when, ops, f"/lint_rules/{i}/when", lint_rule.id))

    available = set(files) if files is not None else None
    if (
        available is not None
        and document.instructions is not None
        and document.instructions.file not in available
    ):
        issues.append(
            _issue(
                KnownIssueCodes.WIKI_TEMPLATE_MISSING,
                "지침 본문 파일이 본문 폴더에 없습니다.",
                severity="error",
                path="/instructions/file",
                details={"file": document.instructions.file},
            )
        )
    builtin = set(WIKI_TEMPLATE_BUILTIN_VARIABLES)
    for i, tpl in enumerate(document.page_templates):
        base = f"/page_templates/{i}"
        if available is not None and tpl.file not in available:
            issues.append(
                _issue(
                    KnownIssueCodes.WIKI_TEMPLATE_MISSING,
                    f"페이지 틀 '{tpl.id}'의 파일이 본문 폴더에 없습니다.",
                    severity="error",
                    path=f"{base}/file",
                    rule_id=tpl.id,
                    details={"file": tpl.file},
                )
            )
        declared = builtin | {v.name for v in tpl.variables}
        for name in sorted(template_variables(tpl.path or "") - declared):
            issues.append(
                _issue(
                    KnownIssueCodes.WIKI_UNKNOWN_VARIABLE,
                    f"경로 틀의 '{{{name}}}'는 앱이 채우지 않고 변수에도 없습니다.",
                    severity="warning",
                    path=f"{base}/path",
                    rule_id=tpl.id,
                    details={"name": name},
                )
            )

    if document.syntax is not None:
        compiled = compile_syntax(merge_syntax(("rules", document.syntax)))
        issues.extend(
            issue.model_copy(update={"path": f"/syntax{issue.path or ''}"})
            for issue in compiled.issues
            if issue.code in _SYNTAX_CODES
        )
    return issues


def load_wiki_rules(
    store: DefinitionStore,
    rule_ids: Sequence[str],
    *,
    kind: str,
) -> list[RulesDocument]:
    """정의 저장소에서 규칙 문서와 본문 파일을 읽는다(없는 id·깨진 문서는 건너뛴다 — `merge_rules`가
    `wiki.rules_missing`을 낸다).

    Args:
        store: 그 공간의 정의 저장소.
        rule_ids: 읽을 규칙 id(위키의 `rules`).
        kind: 위키 규칙 정의 종류 이름(설치자 데이터).
    """
    out: list[RulesDocument] = []
    for rule_id in dict.fromkeys(rule_ids):
        try:
            stored = store.get(kind, rule_id)
            definition = WikiRulesDefinition.model_validate(stored.document)
        except (NotFound, ValidationError):
            continue
        files: dict[str, bytes] = {}
        try:
            listed = store.list_files(kind, rule_id)
        except NotFound:
            listed = []
        for entry in listed:
            try:
                files[entry.path] = store.read_file(kind, rule_id, entry.path)
            except NotFound:
                continue
        out.append(RulesDocument(id=rule_id, definition=definition, files=files))
    return out
