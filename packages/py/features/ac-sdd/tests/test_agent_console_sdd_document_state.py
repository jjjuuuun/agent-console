"""문서 상태 생략 = 목록의 첫 번째(6R.33, design §6R.12 뒤 "문서 상태 생략").

유효 상태 = 적힌 `state` → `initial_document_state` → `document_states[0].id` → 없음. 전환 검사·
`on_edit`·관문 맥락·요약 상태·틀에서 만들기가 모두 같은 함수(`effective_document_state`)를 쓴다.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_conditions import builtin_operators
from agent_console_contracts.sdd import SpecDefinition, SpecRules
from agent_console_sdd import (
    GateBlockedError,
    TransitionDeniedError,
    effective_document_state,
    gate_context,
    instantiate,
)
from agent_console_sdd.testing import TEST_SPEC_KIND, TEST_TEMPLATE_KIND, memory_repository

OPERATORS = {op.descriptor.id: op for op in builtin_operators()}

# `initial_document_state` 없이 목록만 둔 규칙(첫 번째 = draft).
RULES: dict[str, Any] = {
    "document_states": [
        {"id": "draft", "label": "초안", "tone": "neutral", "on_edit": {"to": "edited"}},
        {"id": "edited", "label": "고침"},
        {"id": "approved", "label": "승인됨"},
    ],
    "transitions": [
        {"from": "draft", "to": "approved", "by": ["human"]},
        {"from": "edited", "to": "approved", "by": ["human"]},
    ],
}


def _spec(rules: dict[str, Any] | None) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "kind": TEST_SPEC_KIND,
        "id": "s",
        "name": "스펙",
        # 두 문서 모두 상태를 적지 않았다(생략).
        "documents": [
            {"id": "design", "title": "설계", "file": "design.md"},
            {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
        ],
        "content": {"file": "design.md"},
    }
    if rules is not None:
        doc["rules"] = rules
    return doc


def _repo(rules: dict[str, Any] | None) -> Any:
    repo = memory_repository(clock=lambda: 1000.0, operators=OPERATORS)
    created = repo.store.create(TEST_SPEC_KIND, _spec(rules))
    repo.store.write_files(
        TEST_SPEC_KIND,
        "s",
        {"design.md": b"# design\n", "tasks.md": b"- [ ] 1 a\n"},
        expected_version=created.version_hash,
    )
    return repo


def _rules(data: dict[str, Any]) -> SpecRules:
    return SpecRules.model_validate(data)


def test_effective_state_order() -> None:
    listed = _rules(RULES)
    assert effective_document_state(listed) == "draft"  # 생략 → 목록 첫 번째
    assert effective_document_state(listed, None) == "draft"
    assert effective_document_state(listed, "") == "draft"  # 빈 값도 생략
    assert effective_document_state(listed, "approved") == "approved"  # 적힌 값 우선
    with_initial = _rules({**RULES, "initial_document_state": "edited"})
    assert effective_document_state(with_initial) == "edited"  # 처음 문서 상태가 목록보다 앞
    assert effective_document_state(with_initial, "approved") == "approved"
    # 목록이 비면 상태 없음.
    assert effective_document_state(_rules({})) is None
    assert effective_document_state(_rules({"document_states": []})) is None
    assert effective_document_state(None) is None
    assert effective_document_state(None, "x") == "x"


def test_omitted_state_transition_from_first_state() -> None:
    repo = _repo(RULES)
    stored = repo.change_document_state("s", "design", "approved", by="human")
    doc = stored.spec.documents[0]
    assert doc.state == "approved"
    assert doc.state_changed is not None
    assert doc.state_changed.by == "human"
    # 첫 상태에서 가는 전환이 없으면 거부 — `from`이 첫 상태로 보고된다.
    with pytest.raises(TransitionDeniedError) as denied:
        repo.change_document_state("s", "tasks", "edited", by="human")
    assert denied.value.details["from"] == "draft"


def test_omitted_state_on_edit_uses_first_state() -> None:
    repo = _repo(RULES)
    stored, _ = repo.write_document("s", "design", "바뀐 본문\n")
    assert stored.spec.documents[0].state == "edited"  # draft의 on_edit
    assert stored.spec.documents[0].state_changed.by == "human"
    assert stored.spec.documents[1].state is None  # 다른 문서는 그대로(생략)


def test_gate_context_sees_first_state() -> None:
    spec = SpecDefinition.model_validate(_spec(RULES))
    ctx = gate_context(spec)
    assert ctx["documents"]["design"]["state"] == "draft"
    assert ctx["documents"]["tasks"]["state"] == "draft"
    # 관문 조건 `/documents/<id>/state`가 생략값을 본다(전환 관문으로 확인).
    gate = {
        "id": "need-draft-tasks",
        "applies_to": ["document_state"],
        "require": {"all": [{"path": "/documents/tasks/state", "op": "eq", "value": "draft"}]},
        "message": "작업 문서가 초안이어야 함",
    }
    repo = _repo({**RULES, "gates": [gate]})
    repo.change_document_state("s", "design", "approved", by="human")  # 통과
    blocked = {
        **gate,
        "require": {"all": [{"path": "/documents/tasks/state", "op": "eq", "value": "approved"}]},
    }
    other = _repo({**RULES, "gates": [blocked]})
    with pytest.raises(GateBlockedError):
        other.change_document_state("s", "design", "approved", by="human")


def test_summary_state_label_uses_first_state() -> None:
    repo = _repo(RULES)
    [summary] = repo.summaries()
    assert [(d.state, d.state_label, d.tone) for d in summary.documents] == [
        ("draft", "초안", "neutral"),
        ("draft", "초안", "neutral"),
    ]


def test_instantiate_uses_first_state_without_initial() -> None:
    template = {k: v for k, v in _spec(RULES).items() if k != "kind"}
    template["kind"] = TEST_TEMPLATE_KIND
    draft = instantiate(template, {}, kind=TEST_SPEC_KIND, id="n", name="새")
    assert [d.state for d in draft.spec().documents] == ["draft", "draft"]
    initial = dict(template, rules={**RULES, "initial_document_state": "edited"})
    again = instantiate(initial, {}, kind=TEST_SPEC_KIND, id="n", name="새")
    assert [d.state for d in again.spec().documents] == ["edited", "edited"]
    # 목록이 없으면 상태 없음(틀 없이 만든 빈 스펙과 같다).
    bare = instantiate(dict(template, rules={}), {}, kind=TEST_SPEC_KIND, id="n", name="새")
    assert all(d.state is None for d in bare.spec().documents)


def test_empty_list_keeps_no_state() -> None:
    leftover = {"transitions": [{"from": "*", "to": "approved", "by": ["human"]}]}
    repo = _repo(leftover)
    assert gate_context(repo.get("s").spec)["documents"]["design"]["state"] is None
    [summary] = repo.summaries()
    assert all(d.state is None and d.state_label is None for d in summary.documents)
    with pytest.raises(TransitionDeniedError) as denied:
        repo.change_document_state("s", "design", "approved", by="human")
    assert denied.value.details["from"] is None
    stored, _ = repo.write_document("s", "design", "x\n")
    assert all(d.state is None for d in stored.spec.documents)
