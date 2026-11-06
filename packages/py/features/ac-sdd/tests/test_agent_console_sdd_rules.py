"""규칙 검사(`check_rules`)와 실행 입력 틀(변수 표·치환, §6R.18 Q9)."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_conditions import builtin_operators
from agent_console_contracts.sdd import RunProfile, SpecDocument
from agent_console_sdd import (
    SpecPathError,
    check_rules,
    compile_syntax,
    effective_syntax,
    find_task,
    parse_spec,
    render_run_input,
    run_input_values,
    run_input_variables,
)
from agent_console_sdd.testing import sample_spec

OPERATORS = {op.descriptor.id: op for op in builtin_operators()}
DOCS = [
    SpecDocument(id="design", title="설계", file="design.md"),
    SpecDocument(id="tasks-v2", title="작업", file="tasks.md", roles=["tasks"]),
]


def _codes(issues: list[Any]) -> list[tuple[str, str | None]]:
    return [(i.code, i.path) for i in issues]


def test_clean_rules_have_no_issues() -> None:
    rules = {
        "document_states": [{"id": "draft"}, {"id": "approved"}],
        "initial_document_state": "draft",
        "transitions": [{"from": "*", "to": "approved", "by": ["human"]}],
        "gates": [
            {
                "id": "g",
                "applies_to": ["run"],
                "require": {"all": [{"path": "/documents/design/state", "op": "eq", "value": "x"}]},
            }
        ],
        "run_profiles": [
            {
                "id": "impl",
                "title": "구현",
                "graph": "team",
                "input": {"request": "{task_id} {doc_tasks_v2_file} {task_field_owner}"},
                "status_on": {"succeeded": "done"},
            }
        ],
        "automation": {"profile": "impl"},
    }
    assert check_rules(rules, operators=OPERATORS, documents=DOCS, graphs=["team"]) == []


def test_rule_problems_are_reported() -> None:
    rules = {
        "syntax": {"task": {"id_pattern": "(unclosed"}},
        "task_statuses": [
            {"id": "a", "marker": " "},
            {"id": "b", "marker": " "},
        ],
        "document_states": [{"id": "draft", "on_edit": {"to": "gone"}}],
        "initial_document_state": "nope",
        "transitions": [{"from": "x", "to": "draft", "by": ["human"]}],
        "gates": [
            {"id": "g", "applies_to": ["run"], "require": {"all": [{"path": "/a", "op": "zz"}]}}
        ],
        "run_profiles": [
            {
                "id": "p",
                "title": "프로필",
                "graph": "missing-team",
                "when": {"any": [{"path": "/n", "op": "gt", "value": "3"}]},
                "input": {"request": "{task_id} {mystery}"},
                "status_on": {"failed": "ghost"},
            }
        ],
        "automation": {"profile": "other"},
    }
    issues = check_rules(rules, operators=OPERATORS, documents=DOCS, graphs=["team"])
    codes = _codes(issues)
    assert ("sdd.invalid_pattern", "/syntax/task/id_pattern") in codes
    assert ("sdd.duplicate_status_marker", "/task_statuses") in codes
    assert ("sdd.unknown_state", "/initial_document_state") in codes
    assert ("sdd.unknown_state", "/transitions/0/from") in codes
    assert ("sdd.unknown_state", "/document_states/0/on_edit/to") in codes
    assert ("condition.unknown_operator", "/gates/0/require/all/0/op") in codes
    assert ("condition.invalid_value", "/run_profiles/0/when/any/0/value") in codes
    assert ("sdd.unknown_state", "/run_profiles/0/status_on/failed") in codes
    assert ("sdd.unknown_variable", "/run_profiles/0/input") in codes
    assert ("sdd.profile_graph_missing", "/run_profiles/0/graph") in codes
    assert ("sdd.unknown_profile", "/automation/profile") in codes
    syntax_issue = next(i for i in issues if i.code == "sdd.invalid_pattern")
    assert syntax_issue.details["source"] == "spec"
    unknown_var = next(i for i in issues if i.code == "sdd.unknown_variable")
    assert unknown_var.details == {"name": "mystery"}


def test_broken_rules_become_issues_not_exceptions() -> None:
    issues = check_rules({"transitions": "not-a-list"}, operators=OPERATORS)
    assert issues
    assert all(i.code == "validation_failed" for i in issues)
    assert issues[0].path == "/transitions"
    bad_docs = check_rules({}, operators=OPERATORS, documents=[{"id": "x"}])
    assert bad_docs
    assert (bad_docs[0].path or "").startswith("/documents/0")


def test_variables_table_is_shared_by_spec_and_template() -> None:
    names = [v.name for v in run_input_variables(DOCS, fields=["owner", "re-view"])]
    assert names[:3] == ["task_id", "task_key", "task_title"]
    assert "spec_dir" in names
    assert "task_field_owner" in names
    assert "task_field_re_view" in names
    assert names[-2:] == ["doc_design_file", "doc_tasks_v2_file"]


def test_render_run_input() -> None:
    spec = sample_spec()
    syntax = compile_syntax(effective_syntax())
    text = "## 1단계\n- [ ] 2.3 화면 만들기 [owner: fe] [req: R1, R2] [depends: —]\n  - 본문 줄\n"
    index = parse_spec(spec, {"tasks.md": text, "requirements.md": "", "design.md": ""}, syntax)
    task = find_task(index, "2.3")
    assert task is not None
    profile = RunProfile.model_validate(
        {
            "id": "impl",
            "title": "구현",
            "graph": "team",
            "input": {
                "request": "작업 {task_id} {task_title}\n{task_body}\n담당: {task_field_owner}",
                "refs": ["{spec_dir}/{doc_design_file}", "{task_requirements}", "{unknown}"],
                "n": 3,
            },
        }
    )
    out = render_run_input(profile, task, spec, spec_dir=".agent-console/specs/sample")
    assert out["request"] == f"작업 2.3 화면 만들기\n{task.body}\n담당: fe"
    assert "본문 줄" in task.body
    assert out["refs"] == [".agent-console/specs/sample/design.md", "R1, R2", "{unknown}"]
    assert out["n"] == 3
    values = run_input_values(task, spec, spec_dir="specs/sample")
    assert values["stage_id"] == "1단계"
    assert values["spec_id"] == "sample"
    for bad in ("/abs/path", "C:/x", "a/../../b", "\\\\server\\share"):
        with pytest.raises(SpecPathError):
            render_run_input(profile, task, spec, spec_dir=bad)
