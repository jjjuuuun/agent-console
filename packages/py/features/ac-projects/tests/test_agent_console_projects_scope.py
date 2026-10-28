"""범위 규칙: visible·scope_issues·move_plan·delete_plan (design §UX-P.2, 수용 기준 R15.1·R15.2)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pytest

from agent_console_contracts import KnownIssueCodes, KnownSuggestionIds, Project
from agent_console_projects import (
    CODE_REFERENCES_UNAVAILABLE,
    MOVE_TO_SHARED_SUGGESTION,
    ScopedDefinition,
    UnknownDefinitionError,
    delete_plan,
    move_plan,
    scope_issues,
    visible,
)

# 종류 이름은 일부러 기본 종류(graph·agent·resource)와 다르게 둔다.
# 패키지가 종류 이름을 모름을 확인한다.
TEAM, MEMBER, NOTE = "flow", "persona", "playbook"


def refs(kind: str, doc: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    """테스트용 참조 추출: 문서 `uses`의 "종류/id" 문자열."""
    for item in doc.get("uses", []):
        k, _, i = item.partition("/")
        yield (k, i)


def d(kind: str, id: str, project: str | None = None, *uses: str) -> ScopedDefinition:
    doc: dict[str, Any] = {"id": id, "name": id.upper(), "uses": list(uses)}
    if project is not None:
        doc["project"] = project
    return ScopedDefinition.from_document(kind, doc)


# ---------------------------------------------------------------- visible


@pytest.mark.parametrize(
    ("scope", "selected", "expected"),
    [
        (None, None, True),
        (None, "p", True),
        ("p", "p", True),
        ("q", "p", False),
        ("q", None, True),
    ],
)
def test_visible_shared_plus_current(
    scope: str | None, selected: str | None, expected: bool
) -> None:
    assert visible(scope, selected) is expected


def test_visible_unknown_project_counts_as_shared_when_known_given() -> None:
    assert visible("gone", "p") is False
    assert visible("gone", "p", known={"p"}) is True


# ---------------------------------------------------------------- ScopedDefinition


def test_from_summary_uses_extra_project_presence() -> None:
    summary = {"kind": "anything", "id": "x", "name": "X", "extra": {"project": "p", "type": "t"}}
    assert ScopedDefinition.from_summary(summary).project == "p"
    assert ScopedDefinition.from_summary({**summary, "extra": {"type": "t"}}).project is None

    class Obj:
        kind, id, name, extra = "k", "y", "", {"project": "q"}

    s = ScopedDefinition.from_summary(Obj())
    assert (s.kind, s.id, s.project, s.label) == ("k", "y", "q", "y")


def test_from_summary_reads_top_level_project_for_rest_summary() -> None:
    assert ScopedDefinition.from_summary({"kind": "g", "id": "a", "project": "p"}).project == "p"


def test_from_document_requires_id() -> None:
    with pytest.raises(ValueError, match="id"):
        ScopedDefinition.from_document("k", {"name": "no id"})


def test_empty_project_string_is_shared() -> None:
    assert ScopedDefinition.from_document("k", {"id": "a", "project": ""}).project is None


# ---------------------------------------------------------------- scope_issues


def test_shared_using_project_definition_warns_with_move_suggestion() -> None:
    team = d(TEAM, "t1", None, f"{MEMBER}/m1")
    member = d(MEMBER, "m1", "p")
    issues = scope_issues([team, member], ["p"], references=refs)
    assert len(issues) == 1
    issue = issues[0]
    assert issue.code == KnownIssueCodes.PROJECT_SHARED_USES_PROJECT
    assert issue.severity == "warning"
    assert issue.details["kind"] == MEMBER
    assert issue.details["id"] == "m1"
    assert issue.details["project"] == "p"
    assert issue.details["source"] == {"kind": TEAM, "id": "t1", "project": None}
    assert issue.details["move"] == {"kind": MEMBER, "id": "m1", "to": None}
    assert [s.id for s in issue.suggestions] == [MOVE_TO_SHARED_SUGGESTION]
    assert "M1" in issue.suggestions[0].label
    assert "T1" in issue.message


def test_cross_project_warns() -> None:
    team = d(TEAM, "t1", "p", f"{MEMBER}/m1", f"{NOTE}/n1")
    issues = scope_issues(
        [team, d(MEMBER, "m1", "q"), d(NOTE, "n1", "p")],
        [Project(id="p", name="P", folder=None), {"id": "q"}],
        references=refs,
    )
    assert [(i.code, i.details["id"]) for i in issues] == [
        (KnownIssueCodes.PROJECT_CROSS_PROJECT, "m1")
    ]


def test_allowed_references_produce_no_issue() -> None:
    defs = [
        d(TEAM, "t1", "p", f"{MEMBER}/shared", f"{MEMBER}/mine"),
        d(MEMBER, "shared"),
        d(MEMBER, "mine", "p"),
        d(TEAM, "t2", None, f"{MEMBER}/shared"),
    ]
    assert scope_issues(defs, ["p"], references=refs) == []


def test_unknown_project_is_info_and_treated_as_shared() -> None:
    team = d(TEAM, "t1", None, f"{MEMBER}/m1")
    member = d(MEMBER, "m1", "gone")
    issues = scope_issues([team, member], ["p"], references=refs)
    assert [(i.code, i.severity, i.path, i.details["id"]) for i in issues] == [
        (KnownIssueCodes.PROJECT_UNKNOWN, "info", "/project", "m1")
    ]
    # 존재를 따지지 않으면(projects=None) 값 그대로 본다.
    issues = scope_issues([team, member], None, references=refs)
    assert [i.code for i in issues] == [KnownIssueCodes.PROJECT_SHARED_USES_PROJECT]


def test_missing_references_injection_reports_unavailable() -> None:
    issues = scope_issues(
        [d(TEAM, "t1", None, f"{MEMBER}/m1"), d(MEMBER, "m1", "p")], ["p"], references=None
    )
    assert [(i.code, i.severity) for i in issues] == [(CODE_REFERENCES_UNAVAILABLE, "info")]


def test_duplicate_self_and_missing_references_are_ignored() -> None:
    team = d(TEAM, "t1", None, f"{MEMBER}/m1", f"{MEMBER}/m1", f"{TEAM}/t1", f"{MEMBER}/nope")
    issues = scope_issues([team, d(MEMBER, "m1", "p")], ["p"], references=refs)
    assert len(issues) == 1


def test_definition_without_document_has_no_outgoing_references() -> None:
    team = ScopedDefinition(kind=TEAM, id="t1")
    assert scope_issues([team, d(MEMBER, "m1", "p")], ["p"], references=refs) == []


def test_messages_can_be_overridden() -> None:
    code = KnownIssueCodes.PROJECT_SHARED_USES_PROJECT
    issues = scope_issues(
        [d(TEAM, "t1", None, f"{MEMBER}/m1"), d(MEMBER, "m1", "p")],
        ["p"],
        references=refs,
        messages={code: "${source_id} -> ${ref_id}@${ref_project}"},
    )
    assert issues[0].message == "t1 -> m1@p"


# ---------------------------------------------------------------- move_plan


def test_move_project_to_shared_includes_reference_closure() -> None:
    defs = [
        d(TEAM, "t1", "p", f"{MEMBER}/m1", f"{MEMBER}/s1"),
        d(MEMBER, "m1", "p", f"{NOTE}/n1"),
        d(NOTE, "n1", "p"),
        d(NOTE, "n2", "p"),  # 참조되지 않음 → 함께 옮기지 않음
        d(MEMBER, "s1"),  # 이미 공용
    ]
    plan = move_plan((TEAM, "t1"), None, defs, references=refs, projects=["p"])
    assert plan.target.kind == TEAM
    assert plan.to is None
    assert [(m.kind, m.id, m.from_, m.to, m.required) for m in plan.moves] == [
        (TEAM, "t1", "p", None, True),
        (MEMBER, "m1", "p", None, False),
        (NOTE, "n1", "p", None, False),
    ]
    assert plan.warnings == []


def test_move_to_shared_warns_about_other_project_dependencies() -> None:
    defs = [d(TEAM, "t1", "p", f"{MEMBER}/q1"), d(MEMBER, "q1", "q")]
    plan = move_plan((TEAM, "t1"), None, defs, references=refs, projects=["p", "q"])
    assert [m.id for m in plan.moves] == ["t1"]
    assert [(w.code, w.details["id"]) for w in plan.warnings] == [
        (KnownIssueCodes.PROJECT_SHARED_USES_PROJECT, "q1")
    ]


def test_move_shared_to_project_warns_about_users() -> None:
    defs = [
        d(MEMBER, "m1"),
        d(TEAM, "shared_team", None, f"{MEMBER}/m1"),
        d(TEAM, "q_team", "q", f"{MEMBER}/m1"),
        d(TEAM, "p_team", "p", f"{MEMBER}/m1"),
        d(TEAM, "unrelated", None, f"{MEMBER}/other"),
        d(MEMBER, "other", "q"),  # 기존 위반: 옮기기와 무관하니 경고에 넣지 않음
    ]
    plan = move_plan(d(MEMBER, "m1"), "p", defs, references=refs, projects=["p", "q"])
    assert [(m.id, m.from_, m.to, m.required) for m in plan.moves] == [("m1", None, "p", True)]
    assert [(w.code, w.details["source"]["id"]) for w in plan.warnings] == [
        (KnownIssueCodes.PROJECT_SHARED_USES_PROJECT, "shared_team"),
        (KnownIssueCodes.PROJECT_CROSS_PROJECT, "q_team"),
    ]


def test_move_to_unknown_project_reports_unknown() -> None:
    plan = move_plan((MEMBER, "m1"), "nope", [d(MEMBER, "m1")], references=refs, projects=["p"])
    assert [w.code for w in plan.warnings] == [KnownIssueCodes.PROJECT_UNKNOWN]


def test_move_to_same_scope_is_empty() -> None:
    plan = move_plan((MEMBER, "m1"), "p", [d(MEMBER, "m1", "p")], references=refs)
    assert plan.moves == []
    assert plan.warnings == []


def test_move_without_references_moves_only_target_with_info() -> None:
    defs = [d(TEAM, "t1", "p", f"{MEMBER}/m1"), d(MEMBER, "m1", "p")]
    plan = move_plan((TEAM, "t1"), None, defs, references=None)
    assert [m.id for m in plan.moves] == ["t1"]
    assert [w.code for w in plan.warnings] == [CODE_REFERENCES_UNAVAILABLE]


def test_move_unknown_definition_raises() -> None:
    with pytest.raises(UnknownDefinitionError):
        move_plan((MEMBER, "nope"), None, [], references=refs)


def test_move_plan_serializes_with_from_alias() -> None:
    plan = move_plan((MEMBER, "m1"), None, [d(MEMBER, "m1", "p")], references=refs)
    dumped = plan.model_dump(mode="json", by_alias=True)
    assert dumped["moves"][0]["from"] == "p"
    assert dumped["moves"][0]["to"] is None


def test_closure_handles_cycles() -> None:
    defs = [d(MEMBER, "a", "p", f"{MEMBER}/b"), d(MEMBER, "b", "p", f"{MEMBER}/a")]
    plan = move_plan((MEMBER, "a"), None, defs, references=refs)
    assert [m.id for m in plan.moves] == ["a", "b"]


# ---------------------------------------------------------------- delete_plan


def test_delete_plan_lists_project_definitions() -> None:
    defs = [d(MEMBER, "m1", "p"), d(MEMBER, "m2"), d(NOTE, "n1", "p"), d(NOTE, "n2", "q")]
    plan = delete_plan("p", defs)
    assert plan.project_id == "p"
    assert plan.default_mode == "move_to_shared"
    assert [(k.kind, k.id, k.name) for k in plan.definitions] == [
        (MEMBER, "m1", "M1"),
        (NOTE, "n1", "N1"),
    ]


def test_codes_come_from_contract_constants() -> None:
    """이슈 코드·제안 id는 계약 문서 상수를 그대로 쓴다(다시 정의하지 않음, 5.2R.3 후속)."""
    assert CODE_REFERENCES_UNAVAILABLE is KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE
    assert MOVE_TO_SHARED_SUGGESTION is KnownSuggestionIds.PROJECT_MOVE_TO_SHARED
