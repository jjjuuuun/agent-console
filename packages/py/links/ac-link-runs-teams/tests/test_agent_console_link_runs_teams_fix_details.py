"""5.7R.38: 해결 버튼 표의 ``{detail_<키>}``·``requires``와 기본 표의 에이전트 설정 버튼."""

from __future__ import annotations

from agent_console_contracts import Issue
from agent_console_link_runs_teams import DEFAULT_ISSUE_FIXES, IssueFixes

CODE = "team.member_field_ignored"


def _issue(**details: str) -> Issue:
    return Issue(severity="info", code=CODE, message="m", node_id="mate", details=details)


def test_default_table_opens_agent_only_when_value_came_from_agent() -> None:
    from_agent = _issue(field="model", value_source="agent", agent="a1", agent_kind="agent")
    [annotated] = DEFAULT_ISSUE_FIXES.attach([from_agent], team_kind="graph", graph_id="g1")
    assert annotated.fix is not None
    [action] = annotated.fix.actions
    assert action.target.model_dump(exclude_none=True) == {"role": "definition:agent", "id": "a1"}
    assert action.focus == "/model"
    from_node = _issue(field="model", value_source="node")
    [plain] = DEFAULT_ISSUE_FIXES.attach([from_node], team_kind="graph", graph_id="g1")
    assert plain.fix is None


def test_requires_skips_action_and_non_string_details_are_ignored() -> None:
    table = IssueFixes.from_data(
        {
            "rules": [
                {
                    "codes": ["x"],
                    "actions": [
                        {
                            "label": "A {detail_n}",
                            "target": {"role": "r"},
                            "requires": ["detail_n"],
                        },
                        {"label": "B", "target": {"role": "r2"}},
                    ],
                }
            ]
        }
    )
    fix = table.fix_for("x", team_kind="graph", graph_id=None, details={"n": 3})
    assert fix is not None
    assert [a.label for a in fix.actions] == ["B"]
    fix = table.fix_for("x", team_kind="graph", graph_id=None, details={"n": "v"})
    assert fix is not None
    assert [a.label for a in fix.actions] == ["A v", "B"]
