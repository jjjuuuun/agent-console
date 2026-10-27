"""프로필 검사: 모르는 연산자·없는 칸을 가리키는 연결·중복 id·id 글자 규칙·drill 필터 이름 등."""

from __future__ import annotations

from typing import Any

from agent_console_architecture import check_profile_data, profile_issues
from agent_console_conditions import ConditionOperator
from agent_console_contracts.architecture import ArchitectureProfile, KnownArchitectureIssueCodes

Ops = dict[str, ConditionOperator]
Codes = KnownArchitectureIssueCodes


def _codes(issues: list[Any]) -> list[tuple[str, str | None]]:
    return [(i.code, i.path) for i in issues]


def test_demo_profile_is_clean(demo_profile: ArchitectureProfile, operators: Ops) -> None:
    assert profile_issues(demo_profile, operators=operators, filters={"thread", "scope"}) == []


def test_each_problem(operators: Ops) -> None:
    profile = ArchitectureProfile.model_validate(
        {
            "zones": [
                {"id": "z", "x": 0, "y": 0, "w": 1, "h": 1},
                {"id": "z", "x": 0, "y": 0, "w": 1, "h": 1},
            ],
            "cells": {
                "ok": {
                    "zone": "nozone",
                    "metrics": ["count", "weird"],
                    "when": {"all": [{"path": "/category", "op": "fuzzy", "value": 1}]},
                    "drill": {"filter": "nofilter"},
                },
                "bad id": {},
            },
            "edges": [
                {"id": "e1", "from": "ok", "to": "ghost", "kind": "maybe"},
                {"id": "e1", "from": "ok", "to": "ok", "metrics": ["nope"]},
                {
                    "id": "x:y",
                    "from": "ok",
                    "to": "ok",
                    "when": {"all": [{"path": "/n", "op": "gt", "value": "3"}]},
                },
            ],
            "coverage": {"k": {"cells": ["ghost"], "partial": {"ghost2": "이유"}}},
            "error_when": {"any": [{"path": "/status", "op": "fuzzy"}]},
        }
    )
    found = _codes(
        profile_issues(profile, operators=operators, filters=["thread"], profile_id="bad/id")
    )
    assert found == [
        (Codes.BAD_ID, ""),
        (Codes.DUPLICATE_ID, "/zones/1/id"),
        (Codes.UNKNOWN_ZONE, "/cells/ok/zone"),
        (Codes.UNKNOWN_METRIC, "/cells/ok/metrics/1"),
        (Codes.UNKNOWN_DRILL_FILTER, "/cells/ok/drill/filter"),
        ("condition.unknown_operator", "/cells/ok/when/all/0/op"),
        (Codes.BAD_ID, "/cells/bad id"),
        (Codes.UNKNOWN_CELL, "/edges/0/to"),
        (Codes.UNKNOWN_EDGE_KIND, "/edges/0/kind"),
        (Codes.DUPLICATE_ID, "/edges/1/id"),
        (Codes.UNKNOWN_METRIC, "/edges/1/metrics/0"),
        (Codes.BAD_ID, "/edges/2/id"),
        ("condition.invalid_value", "/edges/2/when/all/0/value"),
        (Codes.UNKNOWN_CELL, "/coverage/k/cells/0"),
        (Codes.UNKNOWN_CELL, "/coverage/k/partial/ghost2"),
        ("condition.unknown_operator", "/error_when/any/0/op"),
    ]


def test_drill_filter_not_checked_without_list(operators: Ops) -> None:
    profile = ArchitectureProfile.model_validate({"cells": {"a": {"drill": {"filter": "x"}}}})
    assert profile_issues(profile, operators=operators) == []


def test_check_profile_data_reports_shape_errors(operators: Ops) -> None:
    issues = check_profile_data(
        {"cells": {"a": {"x": "left"}}, "edges": [{"id": "e"}]},
        operators=operators,
        profile_id="ok-id",
    )
    assert [i.code for i in issues] == [Codes.INVALID]
    errors = issues[0].details["errors"]
    assert isinstance(errors, list)
    paths = {e["path"] for e in errors}
    assert "/cells/a/x" in paths
    assert "/edges/0/from" in paths
    assert check_profile_data({"cells": {}}, operators=operators, profile_id="bad id")[0].code == (
        Codes.BAD_ID
    )
    assert check_profile_data({}, operators=operators) == []
