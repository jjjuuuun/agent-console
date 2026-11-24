"""작업 폴더·허용 디렉터리 풀기: 상대 경로·틀(`{workspace}`)은 기준 폴더(`WORKING_DIRECTORY`)
기준(FU.4)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_console_nodes_core import (
    WORKING_DIRECTORY,
    WORKSPACE_PLACEHOLDER,
    path_placeholders,
    resolve_paths,
    resolve_working_directory,
)

from .test_agent_console_nodes_core_flows import (  # type: ignore[import-not-found]
    agent,
    ans,
    make_stack,
    msg,
    n,
    team,
    you,
)


@pytest.mark.parametrize(
    ("value", "base", "expected"),
    [
        (None, "/w/app", "/w/app"),
        ("", "/w/app", "/w/app"),
        (None, None, None),
        ("", "", None),
        ("sub", "/w/app", os.path.normpath("/w/app/sub")),
        ("a/../b", "/w/app", os.path.normpath("/w/app/b")),
        ("sub", None, "sub"),
        ("/abs", "/w/app", "/abs"),
        ("~/x", "/w/app", "~/x"),
        ("C:\\x", "/w/app", "C:\\x"),
        ("\\\\host\\share", "/w/app", "\\\\host\\share"),
    ],
)
def test_resolve_working_directory(
    value: str | None, base: str | None, expected: str | None
) -> None:
    assert resolve_working_directory(value, base) == expected


def test_path_placeholders_table() -> None:
    assert path_placeholders("/w/app") == {WORKSPACE_PLACEHOLDER: "/w/app"}
    assert path_placeholders(None) == {}
    assert path_placeholders("") == {}


@pytest.mark.parametrize(
    ("values", "base", "expected"),
    [
        (["{workspace}"], "/w/app", [os.path.normpath("/w/app")]),
        (["{workspace}/src"], "/w/app", [os.path.normpath("/w/app/src")]),
        (["{workspace}/../other"], "/w/app", [os.path.normpath("/w/other")]),
        (
            ["docs", "a/../b"],
            "/w/app",
            [os.path.normpath("/w/app/docs"), os.path.normpath("/w/app/b")],
        ),
        (["/abs", "~/x", "C:\\x"], "/w/app", ["/abs", "~/x", "C:\\x"]),
        (["", "  ", " docs "], "/w/app", [os.path.normpath("/w/app/docs")]),
        (["{unknown}/x"], "/w/app", [os.path.normpath("/w/app/{unknown}/x")]),
        (["{workspace}", "docs"], None, ["{workspace}", "docs"]),
        ([], "/w/app", []),
    ],
)
def test_resolve_paths(values: list[str], base: str | None, expected: list[str]) -> None:
    assert resolve_paths(values, base) == expected


async def test_agent_request_limits_directories_are_resolved(tmp_path: Path) -> None:
    """agent 노드는 허용 디렉터리의 틀·상대 경로를 `WORKING_DIRECTORY` 기준으로 풀어 넘긴다
    (요청 `limits`와 `agent.limits` 모두). 절대 경로는 그대로, 명령·네트워크는 건드리지 않는다."""
    base = str(tmp_path / "proj")
    worker = agent(
        "w",
        limits={
            "directories": ["{workspace}/src", "docs", "/abs"],
            "commands": ["git status"],
        },
    )
    stack = make_stack(worker)
    stack.services[WORKING_DIRECTORY] = base
    run = await stack.run(team([you(), n("w", "w")], [msg("m1", "w"), ans("a1", "w")]), "hi")
    assert run.status == "completed", run.error
    req = stack.request_of("w")
    want = [os.path.join(base, "src"), os.path.join(base, "docs"), "/abs"]
    assert req.limits is not None
    assert req.limits.directories == want
    assert req.limits.commands == ["git status"]
    assert req.agent.limits is not None
    assert req.agent.limits.directories == want
    assert req.cwd == base


async def test_agent_request_limits_untouched_without_base() -> None:
    """기준 폴더가 없으면(단독 사용) 값 그대로 — 어떤 기준으로도 추측하지 않는다."""
    worker = agent("w", limits={"directories": ["{workspace}", "docs"]})
    stack = make_stack(worker)
    run = await stack.run(team([you(), n("w", "w")], [msg("m1", "w"), ans("a1", "w")]), "hi")
    assert run.status == "completed", run.error
    req = stack.request_of("w")
    assert req.limits is not None
    assert req.limits.directories == ["{workspace}", "docs"]
