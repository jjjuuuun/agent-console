"""REL.6 복사 적용: 대상에 쓸 id가 종류의 예약어(`DefinitionKind.reserved_ids`)면 이슈."""

from __future__ import annotations

from typing import Any

from agent_console_contracts import CopyApplyItem, KnownCopyActions
from agent_console_projects import (
    CODE_COPY_RESERVED_ID,
    COPY_RESERVED_RENAME,
    COPY_RESERVED_WRITE,
    DEFAULT_COPY_MESSAGES,
    reserved_target_issues,
)

# 종류 이름·예약어는 테스트 데이터일 뿐이다(코드는 종류도 예약어도 모른다).
TPL, NOTE, OPEN = "doc-template", "note", "agent"
WORDS = {TPL: ("variables", "Check"), NOTE: ("inbox",), OPEN: ()}


def _item(kind: str, item_id: str, action: str, new_id: str | None = None) -> dict[str, Any]:
    return {
        "kind": kind,
        "id": item_id,
        "action": action,
        "source_version": "v1",
        **({"new_id": new_id} if new_id is not None else {}),
    }


def test_reserved_new_ids_in_two_kinds_are_rejected_case_insensitively() -> None:
    issues = reserved_target_issues(
        [
            _item(TPL, "a", "rename", "CHECK"),
            _item(TPL, "b", "rename", "fine"),
            _item(NOTE, "n", "rename", "Inbox"),
        ],
        WORDS,
        target_index={(TPL, "CHECK-2"): "x"},
        target_label="결제 폴더",
    )
    assert [(i.code, i.severity, i.path) for i in issues] == [
        (CODE_COPY_RESERVED_ID, "error", "/items/0/new_id"),
        (CODE_COPY_RESERVED_ID, "error", "/items/2/new_id"),
    ]
    assert [i.details for i in issues] == [
        {
            "kind": TPL,
            "id": "a",
            "action": "rename",
            "target_id": "CHECK",
            "new_id": "CHECK",
            "reserved": ["Check", "variables"],
            "suggested_id": "CHECK-3",  # 대상에 -2가 있다
        },
        {
            "kind": NOTE,
            "id": "n",
            "action": "rename",
            "target_id": "Inbox",
            "new_id": "Inbox",
            "reserved": ["inbox"],
            "suggested_id": "Inbox-2",
        },
    ]
    assert "CHECK" in issues[0].message
    assert "CHECK-3" in issues[0].message
    assert "결제" in issues[0].message


def test_list_comes_from_data_not_constants() -> None:
    """같은 말이라도 그 종류 데이터에 없으면 통과하고, 데이터가 없으면 아무것도 보지 않는다."""
    items = [_item(OPEN, "a", "rename", "check"), _item(NOTE, "n", "rename", "variables")]
    assert reserved_target_issues(items, WORDS) == []
    assert reserved_target_issues([_item(TPL, "a", "rename", "check")], None) == []
    assert reserved_target_issues([_item(TPL, "a", "rename", "check")], {}) == []
    custom = reserved_target_issues([_item(OPEN, "a", "rename", "zz")], {OPEN: ("zz",)})
    assert [i.details["new_id"] for i in custom] == ["zz"]


def test_copy_and_overwrite_of_reserved_source_id_are_rejected() -> None:
    """원본 id가 예약어인 항목을 copy·overwrite로 그대로 쓰면 걸리고, reuse·skip은 보지 않는다."""
    items: list[CopyApplyItem | dict[str, Any]] = [
        _item(TPL, "check", KnownCopyActions.COPY),
        _item(TPL, "variables", KnownCopyActions.SKIP),
        {**_item(TPL, "Variables", KnownCopyActions.OVERWRITE), "target_version": "t"},
        {**_item(TPL, "check", KnownCopyActions.REUSE), "target_version": "t"},
        _item(TPL, "normal", KnownCopyActions.COPY),
        CopyApplyItem.model_validate(_item(TPL, "a", KnownCopyActions.RENAME, "fine")),
    ]
    issues = reserved_target_issues(items, WORDS, target_index={(TPL, "Variables"): "t"})
    assert [(i.path, i.details["action"], i.details["target_id"]) for i in issues] == [
        ("/items/0/id", "copy", "check"),
        ("/items/2/id", "overwrite", "Variables"),
    ]
    assert all("new_id" not in (i.details or {}) for i in issues)
    assert [i.details["suggested_id"] for i in issues] == ["check-2", "Variables-2"]
    assert "check-2" in issues[0].message
    assert issues[0].message.startswith(f"{TPL}/check")


def test_suggestions_avoid_each_other_and_other_new_ids() -> None:
    issues = reserved_target_issues(
        [
            _item(TPL, "a", "rename", "check"),
            _item(TPL, "b", "rename", "check-2"),
            _item(TPL, "c", "rename", "Check"),
        ],
        WORDS,
    )
    assert [i.details["suggested_id"] for i in issues] == ["check-3", "Check-4"]


def test_message_is_configurable() -> None:
    assert COPY_RESERVED_RENAME in DEFAULT_COPY_MESSAGES
    issues = reserved_target_issues(
        [_item(TPL, "a", "rename", "variables")],
        WORDS,
        messages={COPY_RESERVED_RENAME: "${item}: ${id} 안 됨, ${suggested} 추천"},
    )
    assert [i.message for i in issues] == [f"{TPL}/a: variables 안 됨, variables-2 추천"]
    assert COPY_RESERVED_WRITE in DEFAULT_COPY_MESSAGES
    issues = reserved_target_issues(
        [_item(TPL, "check", "copy")], WORDS, messages={COPY_RESERVED_WRITE: "${id} → ${suggested}"}
    )
    assert [i.message for i in issues] == ["check → check-2"]
