"""규칙 검사(`POST /sdd/templates/check`·`/sdd/specs/{id}/check`, 저장 때 경고), design §6R.1.1.

검사 항목: 작업 문법(정규식·작업 줄 모양·표시 문자 중복 — `compile_syntax` 재사용), 관문·프로필 조건
(`ac-conditions` `condition_issues`), 모르는 문서 상태·작업 상태 참조, 입력 틀의 모르는 변수, 공간에
없는
팀 구성(목록을 줄 때만), 자동 진행의 모르는 프로필. 규칙이 계약 모양이 아니어도 422 없이 이슈로
돌려준다.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from agent_console_conditions import ConditionOperator, condition_issues
from agent_console_contracts.constants import ErrorCodes, KnownIssueCodes
from agent_console_contracts.definitions import Issue
from agent_console_contracts.sdd import (
    KnownSyntaxSources,
    SddSettings,
    SpecDocument,
    SpecIssue,
    SpecRules,
    SpecSyntax,
)
from agent_console_text_template import template_variables

from ._compiled import compile_syntax
from ._run_input import FIELD_VARIABLE_PREFIX, run_input_variables
from ._syntax import effective_syntax

__all__ = ["check_rules"]

_ANY_STATE = "*"


def _spec_issue(issue: Issue, **extra: Any) -> SpecIssue:
    return SpecIssue.model_validate({**issue.model_dump(mode="json", exclude_none=True), **extra})


def _issue(
    code: str, message: str, path: str, *, severity: str = "error", **details: Any
) -> SpecIssue:
    return SpecIssue.model_validate(
        {"severity": severity, "code": code, "message": message, "path": path, "details": details}
    )


def _validation_issues(exc: ValidationError, base: str) -> list[SpecIssue]:
    out: list[SpecIssue] = []
    for err in exc.errors(include_input=False, include_url=False):
        loc = "/".join(str(p) for p in err.get("loc", ()))
        out.append(
            _issue(
                ErrorCodes.VALIDATION_FAILED,
                f"형식이 맞지 않습니다: {err.get('msg', '')}",
                f"{base}/{loc}" if loc else base,
            )
        )
    return out


def _as_rules(
    rules: SpecRules | Mapping[str, Any] | None,
) -> tuple[SpecRules | None, list[SpecIssue]]:
    if rules is None or isinstance(rules, SpecRules):
        return rules, []
    try:
        return SpecRules.model_validate(dict(rules)), []
    except ValidationError as exc:
        return None, _validation_issues(exc, "")


def _as_documents(
    documents: Sequence[SpecDocument | Mapping[str, Any]],
) -> tuple[list[SpecDocument], list[SpecIssue]]:
    out: list[SpecDocument] = []
    issues: list[SpecIssue] = []
    for i, doc in enumerate(documents):
        if isinstance(doc, SpecDocument):
            out.append(doc)
            continue
        try:
            out.append(SpecDocument.model_validate(dict(doc)))
        except ValidationError as exc:
            issues.extend(_validation_issues(exc, f"/documents/{i}"))
    return out, issues


def _syntax_issues(
    rules: SpecRules, settings: SddSettings | None, default: SpecSyntax | None
) -> list[SpecIssue]:
    eff = effective_syntax(rules, settings, default=default)
    out: list[SpecIssue] = []
    for issue in compile_syntax(eff).issues:
        inner = issue.path or ""
        source = eff.sources.get(inner, KnownSyntaxSources.SPEC)
        if inner == "/task/statuses" and rules.task_statuses is not None:
            path = "/task_statuses"
        else:
            path = f"/syntax{inner}"
        out.append(
            issue.model_copy(update={"path": path, "details": {**issue.details, "source": source}})
        )
    return out


def check_rules(
    rules: SpecRules | Mapping[str, Any] | None,
    *,
    operators: Mapping[str, ConditionOperator],
    documents: Sequence[SpecDocument | Mapping[str, Any]] = (),
    settings: SddSettings | None = None,
    graphs: Collection[str] | None = None,
    default_syntax: SpecSyntax | None = None,
) -> list[SpecIssue]:
    """스펙·문서 틀 규칙을 검사한다(저장하지 않음, 순수 함수).

    Args:
        rules: 규칙(모델 또는 JSON 객체 — 모양이 틀리면 `validation_failed` 이슈).
        operators: 조건 연산자(앱 레지스트리).
        documents: 문서 목록(입력 틀 `doc_<id>_file` 변수 검사용).
        settings: 사용자 설정 섹션 `sdd`(문법 병합).
        graphs: 그 공간의 팀 구성 id. 주면 없는 프로필 그래프를 `sdd.profile_graph_missing`
            (warning)으로 알린다. None이면 검사하지 않는다.
        default_syntax: 패키지 기본 대신 쓸 기본 문법.

    Returns:
        이슈 목록(`path` = 규칙 기준 JSON Pointer, 값 원문 없음).
    """
    model, issues = _as_rules(rules)
    docs, doc_issues = _as_documents(documents)
    issues.extend(doc_issues)
    if model is None:
        return issues
    issues.extend(_syntax_issues(model, settings, default_syntax))

    states = {s.id for s in model.document_states or ()}
    if model.initial_document_state is not None and model.initial_document_state not in states:
        issues.append(
            _issue(
                KnownIssueCodes.SDD_UNKNOWN_STATE,
                "처음 문서 상태가 문서 상태 목록에 없습니다.",
                "/initial_document_state",
                ref=model.initial_document_state,
            )
        )
    for i, t in enumerate(model.transitions or ()):
        for key, value in (("from", t.from_), ("to", t.to)):
            if value == _ANY_STATE and key == "from":
                continue
            if value not in states:
                issues.append(
                    _issue(
                        KnownIssueCodes.SDD_UNKNOWN_STATE,
                        "전환이 문서 상태 목록에 없는 상태를 가리킵니다.",
                        f"/transitions/{i}/{key}",
                        ref=value,
                    )
                )
    for i, s in enumerate(model.document_states or ()):
        if s.on_edit is not None and s.on_edit.to not in states:
            issues.append(
                _issue(
                    KnownIssueCodes.SDD_UNKNOWN_STATE,
                    "고치면 바꿀 상태가 문서 상태 목록에 없습니다.",
                    f"/document_states/{i}/on_edit/to",
                    ref=s.on_edit.to,
                )
            )

    for i, gate in enumerate(model.gates or ()):
        for issue in condition_issues(gate.require, operators, base_path=f"/gates/{i}/require"):
            issues.append(_spec_issue(issue))

    eff = effective_syntax(model, settings, default=default_syntax)
    task_states = {s.id for s in eff.statuses}
    roles = (eff.syntax.task.roles if eff.syntax.task else None) or {}
    known_vars = {v.name for v in run_input_variables(docs, fields=roles)}
    profile_ids = set()
    for i, profile in enumerate(model.run_profiles or ()):
        profile_ids.add(profile.id)
        base = f"/run_profiles/{i}"
        if profile.when is not None:
            for issue in condition_issues(profile.when, operators, base_path=f"{base}/when"):
                issues.append(_spec_issue(issue))
        for run_status, task_status in profile.status_on.items():
            if task_status not in task_states:
                issues.append(
                    _issue(
                        KnownIssueCodes.SDD_UNKNOWN_STATE,
                        "실행 결과에 따른 작업 상태가 작업 상태 목록에 없습니다.",
                        f"{base}/status_on/{run_status}",
                        ref=task_status,
                    )
                )
        for name in sorted(template_variables(profile.input)):
            if name in known_vars or name.startswith(FIELD_VARIABLE_PREFIX):
                continue
            issues.append(
                _issue(
                    KnownIssueCodes.SDD_UNKNOWN_VARIABLE,
                    f"입력 틀이 모르는 변수 '{name}'을(를) 씁니다. 실행 때 그대로 남습니다.",
                    f"{base}/input",
                    severity="warning",
                    name=name,
                )
            )
        if graphs is not None and profile.graph not in graphs:
            issues.append(
                _issue(
                    KnownIssueCodes.SDD_PROFILE_GRAPH_MISSING,
                    "실행 프로필의 팀 구성이 이 공간에 없습니다.",
                    f"{base}/graph",
                    severity="warning",
                    graph=profile.graph,
                )
            )
    automation = model.automation
    if (
        automation is not None
        and automation.profile is not None
        and automation.profile not in profile_ids
    ):
        issues.append(
            _issue(
                KnownIssueCodes.SDD_UNKNOWN_PROFILE,
                "자동 진행이 없는 실행 프로필을 가리킵니다.",
                "/automation/profile",
                ref=automation.profile,
            )
        )
    return issues
