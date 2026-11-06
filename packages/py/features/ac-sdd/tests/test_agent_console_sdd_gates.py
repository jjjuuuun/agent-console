"""관문(design §6R.1.5, §6R.18 Q5·Q12): 맥락, 문서 id 뽑기, 대상 3종 막힘·통과."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_conditions import builtin_operators
from agent_console_contracts.sdd import KnownGateTargets, SpecDefinition, SpecGate, SpecRules
from agent_console_sdd import (
    GateBlockedError,
    compile_syntax,
    effective_syntax,
    evaluate_gates,
    find_task,
    gate_context,
    gate_documents,
    parse_spec,
    require_gates,
)
from agent_console_sdd.testing import memory_repository

OPERATORS = {op.descriptor.id: op for op in builtin_operators()}


def _gate(applies_to: list[str], require: dict[str, Any], gid: str = "g") -> SpecGate:
    return SpecGate.model_validate(
        {"id": gid, "applies_to": applies_to, "require": require, "message": "막힘"}
    )


DESIGN_APPROVED = {"all": [{"path": "/documents/design/state", "op": "eq", "value": "approved"}]}

RULES: dict[str, Any] = {
    "document_states": [{"id": "draft"}, {"id": "review"}, {"id": "approved"}],
    "initial_document_state": "draft",
    "transitions": [
        {"from": "draft", "to": "review", "by": ["human", "run"]},
        {"from": "review", "to": "approved", "by": ["human"]},
        {"from": "*", "to": "draft", "by": ["human"]},
    ],
}


def _spec(rules: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "test-spec",
        "id": "s",
        "name": "스펙",
        "documents": [
            {"id": "design", "title": "설계", "file": "design.md", "state": "draft"},
            {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
        ],
        "rules": rules,
        "content": {"file": "design.md"},
    }


def test_gate_documents_nested_and_escaped() -> None:
    gate = _gate(
        ["run"],
        {
            "all": [{"path": "/documents/design/state", "op": "eq", "value": "approved"}],
            "any": [
                {"path": "/documents/a~1b/state", "op": "exists"},
                {"path": "/task/status", "op": "eq", "value": "todo"},
                {"path": "/documents/design/title", "op": "exists"},
            ],
            # 모르는 키 안의 중첩 조건도 본다(데이터 모델이 보존하는 키).
            "extra": {"all": [{"path": "/documents/req/state", "op": "exists"}]},
        },
    )
    assert gate_documents(gate) == ["design", "a/b", "req"]


def test_context_shape() -> None:
    spec = SpecDefinition.model_validate(_spec({}))
    syntax = compile_syntax(effective_syntax())
    index = parse_spec(spec, {"tasks.md": "## 단계 1\n- [ ] 1 a [owner: be]\n"}, syntax)
    task = find_task(index, "1")
    ctx = gate_context(spec, index, task=task, change={"from": "todo", "to": "done"})
    assert ctx["spec"] == {"id": "s", "name": "스펙"}
    assert ctx["documents"]["design"]["state"] == "draft"
    assert ctx["task"]["fields"] == {"owner": "be"}
    assert ctx["task"]["ready"] is True
    assert ctx["stage"] == {"id": "단계 1", "title": "단계 1", "done": 0, "total": 1}
    assert ctx["change"] == {"from": "todo", "to": "done"}


def test_run_gate_blocks_and_passes() -> None:
    rules = SpecRules.model_validate({"gates": [_gate(["run"], DESIGN_APPROVED).model_dump()]})
    spec = SpecDefinition.model_validate(_spec({}))
    blocks = evaluate_gates(rules, KnownGateTargets.RUN, gate_context(spec), operators=OPERATORS)
    assert [b.gate.id for b in blocks] == ["g"]
    assert blocks[0].details.document_ids == ["design"]
    assert blocks[0].issue().code == "sdd.gate_blocked"
    with pytest.raises(GateBlockedError) as err:
        require_gates(rules, KnownGateTargets.RUN, gate_context(spec), operators=OPERATORS)
    assert err.value.details == {"gate_id": "g", "message": "막힘", "document_ids": ["design"]}
    # 다른 대상에는 걸리지 않는다.
    assert evaluate_gates(rules, "task_status", gate_context(spec), operators=OPERATORS) == []

    approved = _spec({})
    approved["documents"][0]["state"] = "approved"
    ok = gate_context(SpecDefinition.model_validate(approved))
    assert evaluate_gates(rules, KnownGateTargets.RUN, ok, operators=OPERATORS) == []


def test_unknown_operator_blocks_safely() -> None:
    rules = SpecRules.model_validate(
        {"gates": [_gate(["run"], {"all": [{"path": "/spec/id", "op": "fuzzy"}]}).model_dump()]}
    )
    spec = SpecDefinition.model_validate(_spec({}))
    assert evaluate_gates(rules, "run", gate_context(spec), operators=OPERATORS) != []


def _repo_with(rules: dict[str, Any], tasks: str = "- [ ] 1 작업\n") -> Any:
    repo = memory_repository(operators=OPERATORS)
    store = repo.store
    created = store.create("test-spec", _spec(rules))
    store.write_files(
        "test-spec",
        "s",
        {"design.md": b"# design\n", "tasks.md": tasks.encode()},
        expected_version=created.version_hash,
    )
    return repo


def test_task_status_gate_blocks_and_passes() -> None:
    gate = _gate(["task_status"], DESIGN_APPROVED, "need-design")
    repo = _repo_with({**RULES, "gates": [gate.model_dump(by_alias=True)]})
    task = find_task(repo.load("s").index, "1")
    assert task is not None
    with pytest.raises(GateBlockedError) as err:
        repo.patch_task("s", "1", expected_line_hash=task.line_hash, status="done")
    assert err.value.details["gate_id"] == "need-design"
    assert repo.read_document("s", "tasks").text == "- [ ] 1 작업\n"
    # 필드만 바꾸는 것은 작업 상태 관문을 지나지 않는다.
    repo.patch_task("s", "1", expected_line_hash=task.line_hash, fields={"owner": "be"})

    repo.change_document_state("s", "design", "review", by="human")
    repo.change_document_state("s", "design", "approved", by="human")
    task = find_task(repo.load("s").index, "1")
    assert task is not None
    result = repo.patch_task("s", "1", expected_line_hash=task.line_hash, status="done")
    assert result.task.status == "done"


def test_document_state_gate_blocks_and_passes() -> None:
    # 작업 1이 끝나야 설계를 승인할 수 있다(맥락 change로 전환 대상을 본다).
    gate = _gate(
        ["document_state"],
        {
            "any": [
                {"path": "/change/to", "op": "ne", "value": "approved"},
                {"path": "/change/document", "op": "eq", "value": "tasks"},
                {"path": "/documents/tasks/state", "op": "eq", "value": "approved"},
            ]
        },
        "tasks-first",
    )
    rules = {**RULES, "gates": [gate.model_dump(by_alias=True)]}
    repo = _repo_with(rules)
    repo.change_document_state("s", "design", "review", by="human")  # to != approved → 통과
    with pytest.raises(GateBlockedError) as err:
        repo.change_document_state("s", "design", "approved", by="human")
    assert err.value.details["document_ids"] == ["tasks"]
    assert repo.get("s").spec.documents[0].state == "review"

    repo.change_document_state("s", "tasks", "review", by="human")
    repo.change_document_state("s", "tasks", "approved", by="human")
    repo.change_document_state("s", "design", "approved", by="human")
    assert repo.get("s").spec.documents[0].state == "approved"
