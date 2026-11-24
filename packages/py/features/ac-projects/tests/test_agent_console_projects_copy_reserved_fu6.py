"""FU.6 복사 계획: 종류의 예약어 id(`DefinitionKind.reserved_ids`)로 들어오는 항목에 새 id 제안."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agent_console_contracts import Issue, KnownCopyActions, KnownCopyTargetStates
from agent_console_projects import CODE_COPY_RESERVED_ID, SourceDefinition, copy_plan

# 종류 이름·예약어는 테스트 데이터일 뿐이다(코드는 종류도 예약어도 모른다).
KIND, OTHER = "doc-template", "agent"
WORDS = {KIND: ("variables", "Check")}


def _docs(*keys: tuple[str, str]) -> dict[tuple[str, str], SourceDefinition]:
    return {k: SourceDefinition({"id": k[1], "name": k[1]}, f"v-{k[1]}") for k in keys}


def _reserved(plan_warnings: Sequence[Issue]) -> list[dict[str, Any]]:
    return [dict(w.details or {}) for w in plan_warnings if w.code == CODE_COPY_RESERVED_ID]


def test_absent_reserved_id_defaults_to_rename_with_suggestion() -> None:
    docs = _docs((KIND, "check"), (KIND, "normal"))
    plan = copy_plan(
        [(KIND, "check"), (KIND, "normal")],
        docs,
        {(KIND, "check-2"): "x"},
        references=None,
        reserved_ids=WORDS,
    )
    by_id = {i.id: i for i in plan.items}
    assert by_id["check"].default_action == KnownCopyActions.RENAME
    assert by_id["normal"].default_action == KnownCopyActions.COPY
    found = _reserved(plan.warnings)
    assert found == [
        {
            "kind": KIND,
            "id": "check",
            "reserved": ["Check", "variables"],
            "suggested_id": "check-3",
        }
    ]
    message = next(w.message for w in plan.warnings if w.code == CODE_COPY_RESERVED_ID)
    assert "check-3" in message
    assert "doc-template/check" in message


def test_case_insensitive_and_suggestions_do_not_collide() -> None:
    docs = _docs((KIND, "Variables"), (KIND, "variables"))
    plan = copy_plan(
        [(KIND, "Variables"), (KIND, "variables")], docs, {}, references=None, reserved_ids=WORDS
    )
    suggested = [d["suggested_id"] for d in _reserved(plan.warnings)]
    assert suggested == ["Variables-2", "variables-3"]


def test_different_target_keeps_user_choice_and_identical_is_quiet() -> None:
    docs = _docs((KIND, "check"), (KIND, "variables"))
    target = {(KIND, "check"): "other", (KIND, "variables"): "v-variables"}
    plan = copy_plan(
        [(KIND, "check"), (KIND, "variables")], docs, target, references=None, reserved_ids=WORDS
    )
    by_id = {i.id: i for i in plan.items}
    assert by_id["check"].target_state == KnownCopyTargetStates.DIFFERENT
    assert by_id["check"].default_action is None
    assert by_id["variables"].target_state == KnownCopyTargetStates.IDENTICAL
    assert by_id["variables"].default_action == KnownCopyActions.REUSE
    assert [d["id"] for d in _reserved(plan.warnings)] == ["check"]


def test_other_kinds_and_no_reserved_data_are_unchanged() -> None:
    docs = _docs((OTHER, "check"), (KIND, "check"))
    plain = copy_plan([(OTHER, "check"), (KIND, "check")], docs, {}, references=None)
    assert _reserved(plain.warnings) == []
    assert all(i.default_action == KnownCopyActions.COPY for i in plain.items)
    scoped = copy_plan(
        [(OTHER, "check")], docs, {}, references=None, reserved_ids={**WORDS, OTHER: ()}
    )
    assert _reserved(scoped.warnings) == []


def test_messages_are_data() -> None:
    docs = _docs((KIND, "check"))
    plan = copy_plan(
        [(KIND, "check")],
        docs,
        {},
        references=None,
        reserved_ids=WORDS,
        messages={CODE_COPY_RESERVED_ID: "예약어 ${id} → ${suggested}"},
    )
    assert [w.message for w in plan.warnings if w.code == CODE_COPY_RESERVED_ID] == [
        "예약어 check → check-2"
    ]
