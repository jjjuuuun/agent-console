"""검증 경로에 저장 전 정의 검사(``definitions.checks``)의 경고·정보를 붙인다.

저장 전 검사의 error는 저장 경로가 422로 거부하므로 검증 결과에는 경고·정보만 붙인다(기본). 어떤
검사가 있는지(프로젝트 범위 경고 등)는 모른다 — 제공 모듈이 꺼져 있으면 붙일 것이 없을 뿐이다.
FastAPI를 모른다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Sequence

from agent_console_contracts import Graph, Issue, IssueSeverity
from agent_console_store import GRAPH_KIND

from .ports import DefinitionCheck

_log = logging.getLogger("agent_console_link_runs_teams")

DEFAULT_CHECK_SEVERITIES: frozenset[IssueSeverity] = frozenset({"warning", "info"})
"""검증 결과에 붙이는 저장 전 검사 이슈의 심각도(error는 저장 경로가 따로 거부한다)."""


def _key(issue: Issue) -> tuple[str, str | None, str | None, str | None]:
    return (issue.code, issue.node_id, issue.edge_id, issue.path)


def definition_check_issues(
    graph: Graph,
    checks: Sequence[DefinitionCheck],
    *,
    existing: Sequence[Issue] = (),
    kind: str = GRAPH_KIND.name,
    severities: Collection[IssueSeverity] = DEFAULT_CHECK_SEVERITIES,
) -> list[Issue]:
    """팀 구성 문서 하나에 대한 저장 전 검사 이슈(``severities``만, ``existing``과 겹치면 뺀다).

    Args:
        graph: 검증할 팀 구성(저장 경로와 같이 요청에 쓴 키만 문서로 넘긴다).
        checks: 저장 전 검사 목록(``definitions.checks``). 비어 있으면 빈 목록.
        existing: 이미 낸 이슈(엔진·팀 규칙). 같은 코드·대상·path의 이슈는 다시 내지 않는다.
        kind: 정의 종류 이름(기본 팀 구성 종류).
        severities: 붙일 심각도.

    Returns:
        붙일 이슈(검사 순서). 검사 하나가 예외를 내면 기록하고 그 검사만 건너뛴다.
    """
    if not checks:
        return []
    document = graph.model_dump(mode="json", exclude_unset=True)
    seen = {_key(i) for i in existing}
    out: list[Issue] = []
    for check in checks:
        try:
            found = list(check.issues(kind, document))
        except Exception:  # 제공 모듈의 오류 타입을 모른다 — 검증 경로는 계속 응답한다
            _log.exception("저장 전 정의 검사 실패(검증 경로): %s", type(check).__name__)
            continue
        for issue in found:
            if issue.severity not in severities or _key(issue) in seen:
                continue
            seen.add(_key(issue))
            out.append(issue)
    return out


def with_definition_checks(
    graph: Graph,
    issues: Sequence[Issue],
    checks: Callable[[], Sequence[DefinitionCheck]],
) -> list[Issue]:
    """``issues`` 뒤에 저장 전 검사의 경고·정보를 붙인 목록(``definition_check_issues``)."""
    return [*issues, *definition_check_issues(graph, checks(), existing=issues)]


__all__ = ["DEFAULT_CHECK_SEVERITIES", "definition_check_issues", "with_definition_checks"]
