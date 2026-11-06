"""JUnit 검증 출처 단위 테스트: entry point 선언, 옵션 검사(폴더 밖 패턴·위험 정규식 거부),
JUnit 읽기, `SpecFiles` 위 글롭, 요구 id 찾기, 요구·작업별 모으기.

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 파일은 메모리 `SpecFiles`(ac-sdd testing)와
임시 폴더 `LocalSpecFiles`로 준다.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest

from agent_console_contracts.sdd import ParsedRequirement, ParsedTask, SpecIndex
from agent_console_example_sdd_junit import (
    SOURCE_ID,
    JUnitError,
    JUnitOptionsError,
    check_file_pattern,
    check_options,
    collect_results,
    default_options,
    find_files,
    find_requirement_ids,
    parse_junit,
    parse_options,
)
from agent_console_mod_sdd.plugins import VERIFICATION_SOURCES_GROUP
from agent_console_sdd import LocalSpecFiles
from agent_console_sdd.testing import MemorySpecFiles

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def junit(*cases: str, timestamp: str = "2026-11-01T10:00:00") -> str:
    body = "".join(cases)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<testsuites><testsuite name="s" timestamp="{timestamp}">{body}</testsuite></testsuites>'
    )


def case(name: str, classname: str = "tests.test_x", outcome: str = "") -> str:
    inner = {"failed": "<failure message='x'/>", "error": "<error/>", "skipped": "<skipped/>"}
    return f'<testcase classname="{classname}" name="{name}">{inner.get(outcome, "")}</testcase>'


def index(*req_ids: str, tasks: tuple[str, ...] = ()) -> SpecIndex:
    return SpecIndex(
        requirements=[
            ParsedRequirement(id=r, document="req", line=i + 1) for i, r in enumerate(req_ids)
        ],
        tasks=[
            ParsedTask(key=k, status="todo", document="tasks", line=i + 1, line_hash="h")
            for i, k in enumerate(tasks)
        ],
    )


# ---------------------------------------------------------------- 등록·옵션


def test_entry_point_declared_in_mod_sdd_group() -> None:
    meta = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    eps = meta["project"]["entry-points"][VERIFICATION_SOURCES_GROUP]
    assert eps == {SOURCE_ID: "agent_console_example_sdd_junit:JUnitVerificationSource"}


def test_defaults_are_package_data_and_overridable() -> None:
    assert default_options()["paths"] == []
    assert parse_options(None).paths == []
    opts = parse_options({"paths": ["./reports/*.xml"], "label": "CI"})
    assert opts.paths == ["reports/*.xml"]
    assert opts.label == "CI"
    assert opts.result_map["failed"] == "fail"  # 기본값은 키마다 남는다


@pytest.mark.parametrize(
    "pattern",
    [
        "../outside.xml",
        "reports/../../x.xml",
        "/etc/junit.xml",
        "~/junit.xml",
        "C:/junit.xml",
        "reports\\junit.xml",
        "reports//x.xml",
        "reports/**",
        "a**/x.xml",
        "",
    ],
)
def test_patterns_outside_the_project_are_rejected(pattern: str) -> None:
    with pytest.raises(ValueError, match=r"."):
        check_file_pattern(pattern)
    problems = check_options({"paths": ["ok.xml", pattern]})
    assert [where for where, _ in problems] == ["/paths/1"]


@pytest.mark.parametrize("pattern", ["junit.xml", "reports/*.xml", "**/TEST-*.xml", "a/[ab]?.xml"])
def test_patterns_inside_the_project_pass(pattern: str) -> None:
    assert check_file_pattern(pattern) == pattern


def test_unsafe_regex_and_unknown_keys_are_rejected() -> None:
    with pytest.raises(JUnitOptionsError) as err:
        parse_options({"requirement_pattern": "(a+)+", "task_pattern": "(", "nope": 1})
    wheres = sorted(where for where, _ in err.value.problems)
    assert wheres == ["/nope", "/requirement_pattern", "/task_pattern"]


# ---------------------------------------------------------------- JUnit 읽기


def test_parse_junit_outcomes_nested_suites_and_timestamp() -> None:
    xml = (
        '<testsuite name="root" timestamp="2026-11-01T10:00:00+00:00">'
        + case("a")
        + case("b", outcome="failed")
        + '<testsuite name="inner" timestamp="2026-11-02T00:00:00Z">'
        + case("c", outcome="error")
        + case("d", outcome="skipped")
        + "</testsuite></testsuite>"
    )
    cases = parse_junit(xml.encode())
    assert [(c.attributes["name"], c.outcome) for c in cases] == [
        ("a", "passed"),
        ("b", "failed"),
        ("c", "error"),
        ("d", "skipped"),
    ]
    assert cases[0].at is not None
    assert cases[2].at is not None
    assert cases[2].at > cases[0].at
    assert len(parse_junit(xml.encode(), limit=2)) == 2


@pytest.mark.parametrize(
    "data",
    [
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><testsuites/>',
        b"<testsuites><testcase",
        b"<html/>",
    ],
)
def test_parse_junit_rejects_dtd_broken_and_foreign_xml(data: bytes) -> None:
    with pytest.raises(JUnitError):
        parse_junit(data)


# ---------------------------------------------------------------- 찾기


def test_find_files_glob_recursive_skips_links_and_hidden() -> None:
    files = MemorySpecFiles(
        {
            "junit.xml": "x",
            "reports/a.xml": "x",
            "reports/deep/b.xml": "x",
            "reports/deep/b.txt": "x",
            "reports/.cache/c.xml": "x",
            "other/d.xml": "x",
        },
        links=["reports/linked"],
    )
    found = find_files(files, ["reports/**/*.xml", "junit.xml", "missing.xml"])
    assert found.paths == ["junit.xml", "reports/a.xml", "reports/deep/b.xml"]
    assert found.truncated is False
    limited = find_files(files, ["**/*.xml"], max_files=2)
    assert len(limited.paths) == 2
    assert limited.truncated is True
    with pytest.raises(ValueError, match=r"."):
        find_files(files, ["../x.xml"])


def test_find_files_does_not_follow_links_out_of_the_folder(tmp_path: Path) -> None:
    project, outside = tmp_path / "project", tmp_path / "outside"
    (project / "reports").mkdir(parents=True)
    outside.mkdir()
    (outside / "secret.xml").write_text(junit(case("R1 leak")), encoding="utf-8")
    (project / "reports" / "ok.xml").write_text(junit(case("R1 ok")), encoding="utf-8")
    try:
        os.symlink(outside, project / "reports" / "out", target_is_directory=True)
        os.symlink(outside / "secret.xml", project / "reports" / "secret.xml")
    except OSError:
        pytest.skip("이 환경에서는 심볼릭 링크를 만들 수 없다")
    files = LocalSpecFiles(project)
    found = find_files(files, ["reports/**/*.xml", "reports/out/secret.xml"])
    assert found.paths == ["reports/ok.xml"]


# ---------------------------------------------------------------- 요구 id·모으기


def test_find_requirement_ids_by_pattern_or_known_ids() -> None:
    known = ["R1", "R1.2", "R10"]
    assert find_requirement_ids("test_R1_login", pattern=None, known=known) == ["R1"]
    assert find_requirement_ids("R1.2 then R10", pattern=None, known=known) == ["R1.2", "R10"]
    assert find_requirement_ids("XR1 R1x", pattern=None, known=known) == []
    pattern = parse_options({"requirement_pattern": r"req-(?P<id>[A-Z]+\d+)"}).requirement_regex()
    assert find_requirement_ids("req-AB1 req-C2 req-AB1", pattern=pattern, known=[]) == [
        "AB1",
        "C2",
    ]


def test_collect_results_groups_by_requirement_and_task() -> None:
    files = MemorySpecFiles(
        {
            "reports/unit.xml": junit(
                case("test_R1_ok"),
                case("test_R1_broken", outcome="failed"),
                case("test_R2_ok"),
                case("test_unrelated"),
            ),
            "reports/e2e.xml": junit(
                case("task 1.1 R2", outcome="skipped"), timestamp="2026-11-03T00:00:00"
            ),
            "reports/broken.xml": "<testsuites>",
        }
    )
    report = collect_results(
        files,
        index("R1", "R2", tasks=("1.1",)),
        {"paths": ["reports/*.xml"], "task_pattern": r"task (?P<task>\d+\.\d+)"},
    )
    assert report.skipped == [("reports/broken.xml", "invalid_junit")]
    by_req = {r.requirement_ids[0]: r for r in report.results if r.requirement_ids}
    assert by_req["R1"].status == "fail"
    assert by_req["R1"].ref.path == "reports/unit.xml"
    assert by_req["R1"].detail == "fail 1, pass 1"
    assert by_req["R1"].source == SOURCE_ID
    assert by_req["R2"].status == "skipped"  # 기본 우선순위 fail > skipped > pass
    assert by_req["R2"].at is not None
    assert by_req["R1"].at is not None
    assert by_req["R2"].at > by_req["R1"].at
    [task] = [r for r in report.results if r.task_key]
    assert (task.task_key, task.status, task.requirement_ids) == ("1.1", "skipped", [])


def test_collect_results_result_names_are_data() -> None:
    files = MemorySpecFiles({"j.xml": junit(case("R1", outcome="failed"), case("R1"))})
    opts = {
        "paths": ["j.xml"],
        "result_map": {"failed": "red", "passed": "green"},
        "status_priority": ["green", "red"],
        "label": "",
        "match_fields": ["name"],
    }
    [result] = collect_results(files, index("R1"), opts, source_id="ci").results
    assert (result.source, result.status, result.label) == ("ci", "green", "2")


def test_collect_results_without_paths_reads_nothing() -> None:
    files = MemorySpecFiles({"junit.xml": junit(case("R1"))})
    assert collect_results(files, index("R1"), {}).results == []


def test_collect_results_limits() -> None:
    files = MemorySpecFiles({"a.xml": junit(case("R1"), case("R1")), "b.xml": junit(case("R2"))})
    report = collect_results(files, index("R1", "R2"), {"paths": ["*.xml"], "max_testcases": 1})
    assert report.truncated is True
    assert [r.requirement_ids for r in report.results] == [["R1"]]
    big = collect_results(files, index("R1"), {"paths": ["*.xml"], "max_file_bytes": 10})
    assert big.skipped == [("a.xml", "too_large"), ("b.xml", "too_large")]
