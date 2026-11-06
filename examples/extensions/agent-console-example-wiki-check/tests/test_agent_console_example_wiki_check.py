"""머리말 필수 키 검사 단위 테스트: entry point 선언, 옵션(기본값·덮어쓰기·거부), 판단(키·빈 값·
경로 글롭·동작·심각도·문구), mod-wiki 레지스트리 검사기와 맞는지.

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 판단 대상은
`agent_console_wiki.write_subject`로 만든다(mod-wiki가 쓰기 때 만드는 것과 같은 모양).
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.wiki import WikiAuthor
from agent_console_example_wiki_check import (
    CHECK_ID,
    FrontMatterKeysCheck,
    FrontMatterOptionsError,
    check_options,
    default_options,
    missing_keys,
    parse_options,
)
from agent_console_mod_wiki.plugins import (
    WRITE_CHECKS_GROUP,
    as_write_check_factory,
    make_write_check,
)
from agent_console_wiki import write_subject

ROOT = Path(__file__).resolve().parents[1]


def _subject(path: str, front: dict[str, Any], op: str = "create") -> dict[str, Any]:
    return write_subject(
        op=op,
        author=WikiAuthor(kind="user"),
        page={"path": path, "title": path, "front_matter": front},
    )


def test_entry_point_is_declared_in_the_wiki_check_group() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    eps = data["project"]["entry-points"][WRITE_CHECKS_GROUP]
    assert eps == {CHECK_ID: "agent_console_example_wiki_check:FrontMatterKeysCheck"}


def test_defaults_check_nothing() -> None:
    defaults = default_options()
    assert defaults["keys"] == []
    check = FrontMatterKeysCheck()
    assert check.id == CHECK_ID
    assert check.check(_subject("a", {}), "# a\n") == []


def test_missing_key_is_one_issue_with_options_data() -> None:
    check = FrontMatterKeysCheck({"keys": ["source", "owner"]})
    [issue] = check.check(_subject("notes/a", {"owner": "kim"}), "")
    assert issue.severity == "error"
    assert issue.code == "example.front_matter_missing"
    assert issue.message == "머리말에 필요한 키가 없습니다: source"
    assert issue.rule_id == CHECK_ID
    assert issue.page == "notes/a"
    assert issue.details == {"missing": ["source"]}
    assert check.check(_subject("notes/a", {"owner": "kim", "source": "x"}), "") == []


def test_empty_values_count_as_missing_unless_allowed() -> None:
    assert missing_keys({"a": "", "b": None, "c": [], "d": 0}, ["a", "b", "c", "d"]) == [
        "a",
        "b",
        "c",
    ]
    assert missing_keys({"a": ""}, ["a"], allow_empty=True) == []


def test_paths_ops_severity_code_message_are_options() -> None:
    check = FrontMatterKeysCheck(
        {
            "keys": ["status"],
            "paths": ["decisions/**"],
            "severity": "warning",
            "ops": ["create"],
            "code": "team.status_missing",
            "message": "{missing} 키를 적어 주세요",
        },
        check_id="team.status",
    )
    [issue] = check.check(_subject("decisions/2026/a", {}), "")
    assert (issue.severity, issue.code, issue.message, issue.rule_id) == (
        "warning",
        "team.status_missing",
        "status 키를 적어 주세요",
        "team.status",
    )
    assert check.check(_subject("notes/a", {}), "") == []  # 글롭 밖
    assert check.check(_subject("decisions/a", {}, op="update"), "") == []  # 동작 밖


def test_delete_is_not_checked_by_default() -> None:
    check = FrontMatterKeysCheck({"keys": ["source"]})
    assert check.check(_subject("a", {}, op="delete"), "") == []


@pytest.mark.parametrize(
    ("options", "where"),
    [
        ({"unknown": 1}, "/unknown"),
        ({"severity": "fatal"}, "/severity"),
        ({"keys": [""]}, "/keys"),
        ({"paths": ["/abs"]}, "/paths"),
        ({"paths": ["a\\b"]}, "/paths"),
        ({"code": ""}, "/code"),
    ],
)
def test_bad_options_are_rejected(options: dict[str, Any], where: str) -> None:
    problems = check_options(options)
    assert problems
    assert problems[0][0] == where
    with pytest.raises(FrontMatterOptionsError):
        FrontMatterKeysCheck(options)


def test_keys_are_deduplicated_and_defaults_kept() -> None:
    opts = parse_options({"keys": ["a", "a", "b"]})
    assert opts.keys == ["a", "b"]
    assert opts.paths == ["**"]
    assert check_options(None) == []


def test_mod_wiki_registry_accepts_the_class_as_a_factory() -> None:
    factory = as_write_check_factory(FrontMatterKeysCheck)
    made = make_write_check(factory, {"keys": ["k"]})
    assert made.id == CHECK_ID
    with pytest.raises(FrontMatterOptionsError):
        make_write_check(factory, {"keys": "k"})
