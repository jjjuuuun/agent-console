"""계획(design §6R.1.6): 층(병렬 묶음)·병목·순환·가중치·끝난 의존."""

from __future__ import annotations

from agent_console_contracts.sdd import SpecIndex
from agent_console_sdd import compile_syntax, effective_syntax, merge_syntax, parse_spec, plan
from agent_console_sdd.testing import sample_files, sample_spec

SPEC = sample_spec({"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]})
SYNTAX = compile_syntax(effective_syntax())


def _index(text: str, syntax: object = SYNTAX) -> SpecIndex:
    return parse_spec(SPEC, {"tasks.md": text}, syntax)  # type: ignore[arg-type]


def test_layers_and_critical_path() -> None:
    index = _index(
        "- [x] 1 끝남\n"
        "- [ ] 2 가 [depends: 1]\n"
        "- [ ] 3 나 [depends: 1]\n"
        "- [ ] 4 다 [depends: 2]\n"
        "- [ ] 5 라 [depends: 4, 3]\n"
        "- [ ] 6 마\n"
    )
    result = plan(index, SYNTAX)
    assert result.layers == [["2", "3", "6"], ["4"], ["5"]]
    assert result.ready == ["2", "3", "6"]
    assert result.blocked == ["4", "5"]
    assert result.critical_path == ["2", "4", "5"]
    assert result.cycles == []


def test_cycle_members_and_dependents_are_blocked_not_layered() -> None:
    index = _index(
        "- [ ] a1 가 [depends: a2]\n"
        "- [ ] a2 나 [depends: a1]\n"
        "- [ ] a3 다 [depends: a2]\n"
        "- [ ] a4 라\n"
    )
    result = plan(index, SYNTAX)
    assert result.cycles == [["a1", "a2"]]
    assert result.layers == [["a4"]]
    assert result.ready == ["a4"]
    assert set(result.blocked) == {"a1", "a2", "a3"}
    assert result.critical_path == ["a4"]
    # 파싱도 같은 순환을 이슈로 낸다(같은 계산).
    assert any(i.code == "sdd.dependency_cycle" for i in index.issues)


def test_self_dependency_is_a_cycle() -> None:
    result = plan(_index("- [ ] 9 자기 [depends: 9]\n- [ ] 10 다른\n"), SYNTAX)
    assert result.cycles == [["9"]]
    assert result.layers == [["10"]]


def test_weight_role_changes_bottleneck() -> None:
    text = (
        "- [ ] 1 짧은 사슬 [est: 1]\n"
        "- [ ] 2 이어서 [depends: 1] [est: 1]\n"
        "- [ ] 3 혼자 긴 일 [est: 5]\n"
    )
    default_plan = plan(_index(text), SYNTAX)
    assert default_plan.critical_path == ["1", "2"]  # 가중치 역할이 없으면 1씩
    weighted = merge_syntax(
        ("default", effective_syntax().syntax),
        (
            "spec",
            {"task": {"roles": {"depends": "dependencies", "est": "weight"}}},
        ),
    )
    compiled = compile_syntax(weighted)
    assert plan(_index(text, compiled), compiled).critical_path == ["3"]


def test_all_done_is_empty_and_unknown_dependency_does_not_block() -> None:
    assert plan(_index("- [x] 1 끝\n- [x] 2 끝 [depends: 1]\n"), SYNTAX).layers == []
    result = plan(_index("- [ ] 1 없는 의존 [depends: 99]\n"), SYNTAX)
    assert result.ready == ["1"]


def test_sample_document_plan() -> None:
    index = parse_spec(sample_spec(), sample_files(), SYNTAX)
    result = plan(index, effective_syntax())
    assert result.layers[0] == ["6R.3", "6R.4"]
    assert result.layers[1:] == [["6R.10"], ["6R.11"], ["6R.12"]]
    assert result.critical_path == ["6R.3", "6R.10", "6R.11", "6R.12"]
