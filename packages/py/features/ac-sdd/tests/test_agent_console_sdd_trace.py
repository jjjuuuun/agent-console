"""추적 표(design §6R.1.6): 빈 곳 5종, 고아, 최근 실행·토큰 합, 검증 결과 붙이기."""

from __future__ import annotations

from agent_console_contracts import Usage
from agent_console_contracts.sdd import KnownTraceGaps, TaskLink, VerificationResult
from agent_console_sdd import compile_syntax, effective_syntax, parse_spec, sum_totals, trace
from agent_console_sdd.testing import sample_spec

SYNTAX = compile_syntax(effective_syntax())
SPEC = sample_spec(
    {"id": "req", "title": "요구", "file": "req.md", "roles": ["requirements"]},
    {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
)
REQS = (
    "# 요구\n\n**R1** 하나\n\n**R2** 둘\n\n**R3** 셋\n\n**R4** 넷\n\n**R5** 다섯\n\n**R6** 여섯\n"
)
TASKS = (
    "- [x] 1 R2 작업 [req: R2]\n"
    "- [x] 2 R3 작업 [req: R3]\n"
    "- [x] 3 R4 작업 [req: R4]\n"
    "- [ ] 4 R5 작업 [req: R5]\n"
    "- [x] 5 R6 작업 [req: R6]\n"
    "- [ ] 6 요구 없음\n"
    "- [ ] 7 모르는 요구 [req: R9]\n"
)


def _link(task: str, ref: str, at: float, *, kind: str = "run", tokens: int = 0) -> TaskLink:
    return TaskLink(
        integration="runs",
        kind=kind,
        ref=ref,
        task_key=task,
        status="succeeded",
        at=at,
        totals=Usage(input_tokens=tokens) if tokens else None,
    )


def _result(
    status: str, at: float, *, req: str | None = None, task: str | None = None
) -> VerificationResult:
    return VerificationResult(
        source="runs",
        status=status,
        requirement_ids=[req] if req else [],
        task_key=task,
        at=at,
    )


def test_five_gaps_and_orphans() -> None:
    index = parse_spec(SPEC, {"req.md": REQS, "tasks.md": TASKS}, SYNTAX)
    links = [
        _link("2", "r-2a", 10, tokens=5),
        _link("2", "r-2b", 20, tokens=7),
        _link("3", "r-3", 10),
        _link("4", "r-4", 10),
        _link("5", "r-5", 10),
        _link("5", "issue-1", 30, kind="issue"),  # 실행이 아닌 연결은 runs에 세지 않는다
        _link("gone", "r-old", 5),  # 지금 문서에 없는 작업 키
    ]
    results = [
        _result("fail", 30, req="R3"),
        _result("pass", 20, req="R3"),  # 마지막(시각 기준)은 fail
        _result("pass", 15, task="3"),  # 작업 키로 붙는다
        _result("pass", 15, req="R5"),
        _result("pass", 15, req="R6"),
    ]
    matrix = trace(index, links, results, syntax=SYNTAX, max_runs=1)
    gaps = {row.id: row.gaps for row in matrix.rows}
    assert gaps["R1"] == [KnownTraceGaps.NO_TASK, KnownTraceGaps.NOT_VERIFIED]
    assert gaps["R2"] == [KnownTraceGaps.NO_RUN, KnownTraceGaps.NOT_VERIFIED]
    assert gaps["R3"] == [KnownTraceGaps.VERIFICATION_FAILED]
    assert gaps["R4"] == []
    assert gaps["R5"] == [KnownTraceGaps.TASK_NOT_DONE]
    assert gaps["R6"] == []
    found = {g for row in matrix.rows for g in row.gaps}
    assert found == {
        KnownTraceGaps.NO_TASK,
        KnownTraceGaps.NO_RUN,
        KnownTraceGaps.NOT_VERIFIED,
        KnownTraceGaps.VERIFICATION_FAILED,
        KnownTraceGaps.TASK_NOT_DONE,
    }

    r3 = next(row for row in matrix.rows if row.id == "R3")
    assert r3.tasks == ["2"]
    assert [link.ref for link in r3.runs] == ["r-2b"]  # 최근 1개
    assert r3.totals is not None
    assert r3.totals.input_tokens == 12
    assert r3.verification is not None
    assert r3.verification.status == "fail"
    r6 = next(row for row in matrix.rows if row.id == "R6")
    assert [link.ref for link in r6.runs] == ["r-5"]

    assert matrix.orphans.tasks_without_requirements == ["6"]
    assert [(u.task_key, u.requirement_id) for u in matrix.orphans.unknown_requirement_refs] == [
        ("7", "R9")
    ]
    assert [link.ref for link in matrix.orphans.unknown_task_links] == ["r-old"]


def test_failed_results_are_data() -> None:
    index = parse_spec(
        SPEC, {"req.md": "**R1** 하나\n", "tasks.md": "- [x] 1 a [req: R1]\n"}, SYNTAX
    )
    results = [_result("red", 1, req="R1")]
    default = trace(index, [_link("1", "r", 1)], results, syntax=SYNTAX)
    assert default.rows[0].gaps == []
    custom = trace(index, [_link("1", "r", 1)], results, syntax=SYNTAX, failed_results={"red"})
    assert custom.rows[0].gaps == [KnownTraceGaps.VERIFICATION_FAILED]


def test_no_requirement_document_means_no_unknown_refs() -> None:
    spec = sample_spec({"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]})
    index = parse_spec(spec, {"tasks.md": "- [ ] 1 a [req: R1]\n"}, SYNTAX)
    matrix = trace(index, [], [], syntax=SYNTAX)
    assert matrix.rows == []
    assert matrix.orphans.unknown_requirement_refs == []


def test_sum_totals_keeps_extra_numeric_keys() -> None:
    a = Usage.model_validate({"input_tokens": 1, "cost_usd": 0.5, "thinking_tokens": 3})
    b = Usage.model_validate({"input_tokens": 2})
    total = sum_totals([a, None, b])
    assert total is not None
    assert total.input_tokens == 3
    assert total.cost_usd == 0.5
    assert total.model_dump()["thinking_tokens"] == 3
    assert sum_totals([None]) is None
