"""작업 문법 데이터·병합(design §6R.1.3, 6R.10)."""

from __future__ import annotations

from agent_console_contracts.sdd import (
    DocumentStateSpec,
    KnownSyntaxSources,
    SddSettings,
    SpecRules,
    SpecSyntax,
    TaskStatusSpec,
)
from agent_console_sdd import (
    compile_syntax,
    document_state_infos,
    effective_syntax,
    load_default_syntax,
    merge_syntax,
    status_infos,
)

D, S, P = KnownSyntaxSources.DEFAULT, KnownSyntaxSources.SETTINGS, KnownSyntaxSources.SPEC


def test_default_syntax_is_data_with_labels() -> None:
    syntax = load_default_syntax()
    assert syntax.task is not None
    assert syntax.task.statuses
    assert all(s.label for s in syntax.task.statuses)  # (Q1) 기본 데이터는 label을 쓴다
    assert syntax.task.roles == {
        "depends": "dependencies",
        "req": "requirements",
        "owner": "assignee",
    }
    assert compile_syntax(effective_syntax()).issues == []
    # 새 객체를 돌려준다(호출자가 고쳐도 다음 호출에 영향 없음).
    syntax.task.statuses.clear()
    fresh = load_default_syntax()
    assert fresh.task is not None
    assert fresh.task.statuses


def test_merge_none_inherits_and_sources() -> None:
    eff = effective_syntax(
        SpecRules.model_validate({"syntax": {"task": {"range_separator": ".."}}}),
        SddSettings.model_validate({"syntax": {"task": {"list_separator": ";"}}}),
    )
    task = eff.syntax.task
    assert task is not None
    assert task.range_separator == ".."
    assert task.list_separator == ";"
    assert task.id_pattern  # 상속
    assert eff.sources["/task/range_separator"] == P
    assert eff.sources["/task/list_separator"] == S
    assert eff.sources["/task/id_pattern"] == D
    assert eff.sources["/stage/heading_levels"] == D
    assert not eff.empty


def test_lists_and_roles_replace_whole() -> None:
    eff = merge_syntax(
        (D, load_default_syntax()),
        (P, SpecSyntax.model_validate({"task": {"roles": {"after": "dependencies"}}})),
    )
    assert eff.syntax.task is not None
    assert eff.syntax.task.roles == {"after": "dependencies"}  # 매핑은 통째로 바꿈
    eff2 = merge_syntax(
        (D, load_default_syntax()),
        (P, {"requirement": {"patterns": []}}),  # 빈 목록 = 이 층에서는 없음
    )
    assert eff2.syntax.requirement is not None
    assert eff2.syntax.requirement.patterns == []
    assert eff2.sources["/requirement/patterns"] == P


def test_rules_task_statuses_win_and_labels_filled() -> None:
    rules = SpecRules.model_validate(
        {
            "syntax": {"task": {"statuses": [{"id": "a", "marker": "a"}]}},
            "task_statuses": [
                {"id": "todo", "marker": " "},
                {"id": "doing", "label": "진행 중", "marker": "~"},
                {"id": "done", "label": "", "marker": ["x", "X"], "done": True},
            ],
        }
    )
    eff = effective_syntax(rules)
    assert [s.id for s in eff.statuses] == ["todo", "doing", "done"]
    assert [s.label for s in eff.statuses] == ["todo", "진행 중", "done"]  # 없으면 id
    assert eff.statuses[2].markers == ["x", "X"]
    assert eff.sources["/task/statuses"] == P


def test_default_off_leaves_empty_syntax() -> None:
    eff = effective_syntax(settings=SddSettings(include_default_syntax=False))
    assert eff.empty
    assert eff.statuses == []
    assert D not in eff.sources.values()


def test_unknown_keys_are_kept() -> None:
    eff = merge_syntax((S, {"task": {"list_item": "bullet", "statuses": [], "x_custom": 1}}))
    dumped = eff.syntax.model_dump()
    assert dumped["task"]["x_custom"] == 1
    assert eff.empty  # 상태가 없으면 작업을 읽을 수 없다


def test_state_infos_fill_labels() -> None:
    infos = document_state_infos(
        [
            DocumentStateSpec.model_validate({"id": "draft"}),
            DocumentStateSpec.model_validate({"id": "ok", "label": "승인됨", "tone": "success"}),
            DocumentStateSpec.model_validate({"id": "draft", "label": "중복"}),
        ]
    )
    assert [(i.id, i.label, i.tone) for i in infos] == [
        ("draft", "draft", None),
        ("ok", "승인됨", "success"),
    ]
    assert status_infos([TaskStatusSpec(id="t", marker="t")])[0].label == "t"
    assert document_state_infos(None) == []


def test_compile_reports_bad_patterns_and_duplicate_markers() -> None:
    eff = merge_syntax(
        (
            P,
            {
                "task": {
                    "list_item": "table",
                    "statuses": [
                        {"id": "a", "marker": "x"},
                        {"id": "b", "marker": "x"},
                    ],
                    "id_pattern": "(a+)+",
                    "field_pattern": r"\[(?P<k>\w+)\]",
                },
                "requirement": {"patterns": ["(", r"(?P<id>R\d+)"]},
            },
        )
    )
    compiled = compile_syntax(eff)
    codes = sorted((i.code, i.path) for i in compiled.issues)
    assert codes == [
        ("sdd.duplicate_status_marker", "/task/statuses"),
        ("sdd.invalid_pattern", "/requirement/patterns/0"),
        ("sdd.invalid_pattern", "/task/field_pattern"),
        ("sdd.invalid_pattern", "/task/id_pattern"),
        ("sdd.invalid_pattern", "/task/list_item"),
    ]
    assert compiled.empty  # 모르는 작업 줄 모양 → 작업 없음
    assert len(compiled.requirement_patterns) == 1
    assert compiled.marker_to_status == {"x": "a"}
