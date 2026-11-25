"""입력 모양 `ScopedDefinition`과 이슈 코드 별칭.

REL.14: 옛 범위 규칙(`visible`·`scope_issues`·`move_plan`·`delete_plan`)은 지웠다.
`ScopedDefinition`은 옛 `project` 필드 정의 정리(`legacy_items` → 복사 계획)의 입력으로 남는다.
"""

from __future__ import annotations

import pytest

import agent_console_projects as projects
from agent_console_contracts import KnownIssueCodes
from agent_console_projects import CODE_REFERENCES_UNAVAILABLE, CODE_UNKNOWN, ScopedDefinition


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


def test_codes_come_from_contract_constants() -> None:
    """이슈 코드는 계약 문서 상수를 그대로 쓴다(다시 정의하지 않음). 옮긴 뒤에도 같은 이름이다."""
    assert CODE_UNKNOWN is KnownIssueCodes.PROJECT_UNKNOWN
    assert CODE_REFERENCES_UNAVAILABLE is KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE


@pytest.mark.parametrize(
    "name",
    [
        "visible",
        "scope_issues",
        "move_plan",
        "delete_plan",
        "UnknownDefinitionError",
        "MOVE_TO_SHARED_SUGGESTION",
        "CODE_SHARED_USES_PROJECT",
        "CODE_CROSS_PROJECT",
        "DEFAULT_MESSAGES",
        "effective_scope",
        "known_project_ids",
    ],
)
def test_old_scope_rules_are_removed(name: str) -> None:
    """0.3.0(깨는 변경): 옛 정의 범위 규칙과 그 상수는 공개 이름에 없다."""
    assert name not in projects.__all__
    assert not hasattr(projects, name)
