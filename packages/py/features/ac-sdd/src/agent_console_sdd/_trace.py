"""추적 표: 요구 → 작업 → 실행(연결) → 검증 결과와 빈 곳, design §6R.1.6.

순수 함수다. 연결(`TaskLink`)과 검증 결과(`VerificationResult`)는 호출자가 연동(X43)·검증 출처(X42)
에서 한 번에 모아 넘긴다(작업 수만큼 질의하지 않는다).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from typing import Any

from agent_console_contracts import Usage
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.sdd import (
    EffectiveSyntax,
    KnownDocumentRoles,
    KnownTaskLinkKinds,
    KnownTraceGaps,
    SpecIndex,
    TaskLink,
    TraceMatrix,
    TraceOrphans,
    TraceRow,
    TraceUnknownRef,
    TraceVerification,
    VerificationResult,
)

from ._compiled import CompiledSyntax, compile_syntax

__all__ = ["DEFAULT_FAILED_RESULTS", "DEFAULT_RUN_LINK_KINDS", "sum_totals", "trace"]

DEFAULT_RUN_LINK_KINDS: tuple[str, ...] = (KnownTaskLinkKinds.RUN,)
"""`runs` 열과 `no_run` 빈 곳에 세는 연결 종류(기본 = 실행). 인자로 바꾼다."""

DEFAULT_FAILED_RESULTS: tuple[str, ...] = ("fail", "failed")
"""`verification_failed` 빈 곳으로 볼 검증 결과 값(기본). 검증 결과 값은 사용자 데이터
(`VerificationConfig.result_map`)이므로 인자로 바꾼다."""

_PASS_THROUGH_ISSUES = frozenset(
    {
        KnownIssueCodes.SDD_SYNTAX_MISSING,
        KnownIssueCodes.SDD_PARSE_TIMEOUT,
        KnownIssueCodes.SDD_TOO_MANY_TASKS,
    }
)


def _at(value: float | None) -> float:
    return value if value is not None else float("-inf")


def sum_totals(usages: Iterable[Usage | None]) -> Usage | None:
    """사용량 합(알려진 키와 백엔드가 더한 숫자 키 모두). 모두 None이면 None."""
    total: dict[str, Any] = {}
    seen = False
    for usage in usages:
        if usage is None:
            continue
        seen = True
        for key, value in usage.model_dump(exclude_none=True).items():
            if isinstance(value, bool) or not isinstance(value, int | float):
                continue
            total[key] = total.get(key, 0) + value
    return Usage.model_validate(total) if seen else None


def trace(
    index: SpecIndex,
    links: Sequence[TaskLink],
    results: Sequence[VerificationResult],
    *,
    syntax: EffectiveSyntax | CompiledSyntax,
    max_runs: int = 5,
    run_kinds: Collection[str] = DEFAULT_RUN_LINK_KINDS,
    failed_results: Collection[str] = DEFAULT_FAILED_RESULTS,
) -> TraceMatrix:
    """추적 표를 만든다.

    Args:
        index: `parse_spec` 결과.
        links: 작업 연결(작업 키 `task_key`가 있는 것만 본다). 여러 연동의 것을 섞어도 된다.
        results: 검증 결과(요구 id 또는 작업 키로 행에 붙는다).
        syntax: 같은 파싱의 유효 문법(작업이 끝났는지 판단).
        max_runs: 행마다 보일 최근 연결 수(토큰 합은 전부로 센다).
        run_kinds: 실행으로 셀 연결 종류.
        failed_results: 실패로 볼 검증 결과 값.

    Returns:
        `TraceMatrix`. 행 = 요구 문서 순서. 빈 곳 코드(`KnownTraceGaps`):
        `no_task`(작업 없음) · `no_run`(작업은 있는데 실행 없음) · `not_verified`(검증 결과 없음) ·
        `verification_failed`(마지막 검증이 실패) · `task_not_done`(끝나지 않은 작업이 있음).
        `orphans`: 요구가 없는 작업, 요구 문서에 없는 요구 참조(요구 문서가 있을 때만), 지금 문서에
        없는 작업 키를 가리키는 연결(작업 id가 바뀐 경우 등, K6R-4).
    """
    compiled = syntax if isinstance(syntax, CompiledSyntax) else compile_syntax(syntax)
    done = compiled.done_ids
    task_keys = {t.key for t in index.tasks}
    req_ids = {r.id for r in index.requirements}
    has_req_doc = any(
        d.exists and KnownDocumentRoles.REQUIREMENTS in d.roles for d in index.documents
    )

    tasks_by_req: dict[str, list[str]] = {}
    orphans = TraceOrphans()
    for t in index.tasks:
        if not t.requirements:
            orphans.tasks_without_requirements.append(t.key)
        for rid in t.requirements:
            tasks_by_req.setdefault(rid, []).append(t.key)
            if has_req_doc and rid not in req_ids:
                orphans.unknown_requirement_refs.append(
                    TraceUnknownRef(task_key=t.key, requirement_id=rid)
                )
    status_of = {t.key: t.status for t in index.tasks}

    runs_by_task: dict[str, list[TaskLink]] = {}
    for link in links:
        if link.task_key is None:
            continue
        if link.task_key not in task_keys:
            orphans.unknown_task_links.append(link)
            continue
        if link.kind in run_kinds:
            runs_by_task.setdefault(link.task_key, []).append(link)

    results_by_req: dict[str, list[VerificationResult]] = {}
    results_by_task: dict[str, list[VerificationResult]] = {}
    for result in results:
        for rid in result.requirement_ids:
            results_by_req.setdefault(rid, []).append(result)
        if result.task_key is not None:
            results_by_task.setdefault(result.task_key, []).append(result)

    rows: list[TraceRow] = []
    for req in index.requirements:
        keys = tasks_by_req.get(req.id, [])
        row_links = [link for k in keys for link in runs_by_task.get(k, ())]
        row_links.sort(key=lambda link: _at(link.at), reverse=True)
        seen: set[int] = set()
        row_results: list[VerificationResult] = []
        for r in [
            *results_by_req.get(req.id, ()),
            *(x for k in keys for x in results_by_task.get(k, ())),
        ]:
            if id(r) not in seen:
                seen.add(id(r))
                row_results.append(r)
        row_results.sort(key=lambda r: _at(r.at), reverse=True)
        latest = row_results[0] if row_results else None

        gaps: list[str] = []
        if not keys:
            gaps.append(KnownTraceGaps.NO_TASK)
        elif not row_links:
            gaps.append(KnownTraceGaps.NO_RUN)
        if latest is None:
            gaps.append(KnownTraceGaps.NOT_VERIFIED)
        elif latest.status in failed_results:
            gaps.append(KnownTraceGaps.VERIFICATION_FAILED)
        if any(status_of[k] not in done for k in keys):
            gaps.append(KnownTraceGaps.TASK_NOT_DONE)

        rows.append(
            TraceRow(
                id=req.id,
                title=req.title,
                document=req.document,
                line=req.line,
                tasks=list(keys),
                runs=row_links[: max(0, max_runs)],
                totals=sum_totals(link.totals for link in row_links),
                verification=(
                    TraceVerification(status=latest.status, at=latest.at, source=latest.source)
                    if latest is not None
                    else None
                ),
                results=row_results,
                gaps=gaps,
            )
        )
    issues = [i for i in index.issues if i.code in _PASS_THROUGH_ISSUES]
    return TraceMatrix(rows=rows, orphans=orphans, issues=issues)
