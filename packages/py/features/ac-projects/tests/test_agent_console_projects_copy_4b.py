"""묶음 4b V1·V3: 복사 계획의 평문 비밀 막힘 미리 알림, 방향 중립 `copy_kind_not_portable` 문구."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from agent_console_projects import (
    CODE_COPY_KIND_NOT_PORTABLE,
    CODE_COPY_SKIP_BREAKS_REFERENCE,
    CODE_SECRET_PLAIN_FOUND,
    COPY_TARGET_LIBRARY,
    COPY_TARGET_PROJECT,
    DEFAULT_TARGET_LABEL,
    DefinitionId,
    SourceDefinition,
    copy_plan,
    copy_target_label,
)

SECRET = "sk" + "-" + "test-PLAINVALUE-1234567890"


@dataclass(frozen=True)
class _Finding:
    path: str
    reason: str


def _plain(kind: str, doc: Mapping[str, Any]) -> Iterable[_Finding]:
    """테스트 판정: 문자열 값이 SECRET이면 그 위치(대상 공간 쓰기 검사 대역)."""
    return [_Finding(f"/{k}", "value_pattern") for k, v in doc.items() if v == SECRET]


def refs(kind: str, doc: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    return [("agent", x) for x in doc.get("uses", [])]


def _docs() -> dict[DefinitionId, SourceDefinition]:
    return {
        ("graph", "team"): SourceDefinition({"id": "team", "uses": ["leaky", "clean"]}, "g1"),
        ("agent", "leaky"): SourceDefinition({"id": "leaky", "prompt": SECRET}, "a1"),
        ("agent", "clean"): SourceDefinition({"id": "clean", "prompt": "hi"}, "a2"),
    }


# ------------------------------------------------------------ V1 평문 비밀 막힘


def test_plain_secret_item_is_blocked_with_issue_and_no_value() -> None:
    plan = copy_plan(
        [("graph", "team")],
        _docs(),
        {},
        references=refs,
        plain_secrets=_plain,
        target_label="프로젝트 \u2018결제\u2019",
    )
    by_id = {i.id: i for i in plan.items}
    leaky = by_id["leaky"]
    assert leaky.blocked is True
    assert leaky.default_action == "skip"
    assert [(i.severity, i.code, i.path) for i in leaky.issues] == [
        ("error", CODE_SECRET_PLAIN_FOUND, "/prompt")
    ]
    assert leaky.issues[0].details == {
        "kind": "agent",
        "id": "leaky",
        "path": "/prompt",
        "reason": "value_pattern",
    }
    assert "프로젝트 \u2018결제\u2019" in leaky.issues[0].message
    # 막히지 않은 항목은 그대로
    assert by_id["team"].blocked is False
    assert by_id["team"].default_action == "copy"
    assert by_id["clean"].blocked is False
    assert by_id["clean"].issues == []
    # 막힌 항목을 빼면 그것을 쓰는 팀이 실행 전에 막힌다는 경고
    assert [w.code for w in plan.warnings] == [CODE_COPY_SKIP_BREAKS_REFERENCE]
    assert plan.warnings[0].details["id"] == "leaky"
    # 값은 응답 어디에도 없다
    assert SECRET not in plan.model_dump_json()


def test_blocked_item_already_in_target_gives_no_skip_warning() -> None:
    plan = copy_plan(
        [("graph", "team")],
        _docs(),
        {("agent", "leaky"): "other"},
        references=refs,
        plain_secrets=_plain,
    )
    assert {i.id: i.blocked for i in plan.items}["leaky"] is True
    assert plan.warnings == []


def test_without_check_nothing_is_blocked() -> None:
    plan = copy_plan([("graph", "team")], _docs(), {}, references=refs)
    assert [i.blocked for i in plan.items] == [False, False, False]
    assert all(i.issues == [] for i in plan.items)


def test_plain_secret_message_can_be_replaced() -> None:
    plan = copy_plan(
        [("agent", "leaky")],
        _docs(),
        {},
        references=None,
        plain_secrets=_plain,
        messages={CODE_SECRET_PLAIN_FOUND: "막힘 ${item} ${path} ${target}"},
    )
    assert plan.items[0].issues[0].message == f"막힘 agent/leaky /prompt {DEFAULT_TARGET_LABEL}"


# ------------------------------------------------------------ V3 방향 중립 문구


def _not_portable(target_label: str, messages: Mapping[str, str] | None = None) -> str:
    plan = copy_plan(
        [("note", "n1")],
        {("note", "n1"): SourceDefinition({"id": "n1"}, "v")},
        {},
        references=None,
        kinds={"agent"},
        target_label=target_label,
        messages=messages,
    )
    found = [w for w in plan.warnings if w.code == CODE_COPY_KIND_NOT_PORTABLE]
    assert len(found) == 1
    assert found[0].details == {"kind": "note", "id": "n1"}  # details 그대로
    return found[0].message


def test_not_portable_message_library_to_project() -> None:
    label = copy_target_label("결제")
    assert (
        _not_portable(label)
        == "note/n1은(는) 프로젝트 \u2018결제\u2019에 둘 수 없는 종류라 뺐습니다."
    )


def test_not_portable_message_project_to_library() -> None:
    label = copy_target_label(None)
    assert _not_portable(label) == "note/n1은(는) 공용 구성에 둘 수 없는 종류라 뺐습니다."


def test_not_portable_default_target_label() -> None:
    plan = copy_plan(
        [("note", "n1")],
        {("note", "n1"): SourceDefinition({"id": "n1"}, "v")},
        {},
        references=None,
        kinds=(),
    )
    assert plan.warnings[0].message == "note/n1은(는) 대상 공간에 둘 수 없는 종류라 뺐습니다."


def test_user_messages_still_override() -> None:
    custom = {CODE_COPY_KIND_NOT_PORTABLE: "${item} 제외"}
    assert _not_portable(copy_target_label("결제"), custom) == "note/n1 제외"
    labels = {COPY_TARGET_LIBRARY: "라이브러리", COPY_TARGET_PROJECT: "${name} 폴더"}
    assert copy_target_label(None, messages=labels) == "라이브러리"
    assert copy_target_label("결제", messages=labels) == "결제 폴더"
