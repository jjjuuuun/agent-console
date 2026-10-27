"""5.7R.8(M-4): 조건이 목록 본문에 없는 경로를 보면 경고. 접두는 호출자가 데이터로 준다."""

from __future__ import annotations

from typing import Any

from agent_console_architecture import check_profile_data, profile_issues, unlisted_path_issues
from agent_console_conditions import ConditionOperator
from agent_console_contracts import KnownIssueCodes
from agent_console_contracts.architecture import ArchitectureProfile

Ops = dict[str, ConditionOperator]
CODE = KnownIssueCodes.ARCHITECTURE_CONDITION_PATH_UNLISTED

# 이름은 테스트 데이터일 뿐이다(패키지는 접두 이름을 모른다 — 다른 이름으로도 같아야 한다).
PROFILE: dict[str, Any] = {
    "cells": {
        "a": {"when": {"all": [{"path": "/body/text", "op": "exists"}]}},
        "b": {
            "when": {
                "all": [{"path": "/category", "op": "eq", "value": "x"}],
                "any": [
                    {"path": "/bodyless", "op": "exists"},
                    {"path": "/blob", "op": "exists"},
                ],
            }
        },
        "c": {},
    },
    "edges": [
        {"id": "e", "from": "a", "to": "b", "when": {"any": [{"path": "/body", "op": "exists"}]}},
    ],
    "error_when": {"all": [{"path": "/blob/0/x", "op": "exists"}]},
}


def _profile() -> ArchitectureProfile:
    return ArchitectureProfile.model_validate(PROFILE)


def test_no_prefixes_means_no_warning(operators: Ops) -> None:
    profile = _profile()
    assert unlisted_path_issues(profile, ()) == []
    assert not [i for i in profile_issues(profile, operators=operators) if i.code == CODE]


def test_prefix_match_and_mismatch(operators: Ops) -> None:
    issues = [
        i
        for i in profile_issues(
            profile=_profile(), operators=operators, unlisted_paths=["/body", "/blob/"]
        )
        if i.code == CODE
    ]
    assert [(i.severity, i.path, i.details["prefix"]) for i in issues] == [
        ("warning", "/cells/a/when/all/0/path", "/body"),
        ("warning", "/cells/b/when/any/1/path", "/blob"),
        ("warning", "/edges/0/when/any/0/path", "/body"),
        ("warning", "/error_when/all/0/path", "/blob"),
    ]
    # `/bodyless`는 `/body`로 시작하지만 그 아래가 아니다. `/category`는 접두와 무관하다.
    assert all(i.details["condition_path"] not in {"/bodyless", "/category"} for i in issues)
    assert "목록 본문" in issues[0].message


def test_renamed_prefixes_same_result() -> None:
    """R0: 접두 이름을 바꾸면 그 이름으로만 걸린다(코드에 이름 없음)."""
    profile = _profile()
    assert [i.path for i in unlisted_path_issues(profile, ["/category"])] == [
        "/cells/b/when/all/0/path"
    ]
    assert unlisted_path_issues(profile, ["/nothing"]) == []
    assert unlisted_path_issues(profile, ["", "/"]) == []  # 문서 전체 접두는 무시


def test_check_profile_data_passes_prefixes(operators: Ops) -> None:
    found = check_profile_data(PROFILE, operators=operators, unlisted_paths=["/body"])
    assert sum(i.code == CODE for i in found) == 2
    invalid = check_profile_data({"cells": 3}, operators=operators, unlisted_paths=["/body"])
    assert all(i.code != CODE for i in invalid)
