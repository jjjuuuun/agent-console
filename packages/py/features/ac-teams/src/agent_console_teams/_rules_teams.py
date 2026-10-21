"""팀 규칙: 중첩 팀(design §5R.7·§5R.8 `team` 행).

중첩 팀 노드 = 노드 타입 디스크립터 `binds.kind == TeamConventions.team_kind`인 노드(이름 무관).
자식 팀 구성은 주입받은 조회 함수(`TeamCheckContext.teams`)로 읽는다. 조회 수단이 없으면 자기
참조만 보고, 자식을 읽어야 하는 검사(없음·입구 없음·순환·깊이)는 건너뛴다(실행 시 엔진·노드가
같은 코드로 막는다).

- `team.recursive`: 자기 자신 또는 자식·손자를 따라가다 이미 경로에 있는 팀 구성을 다시 넣는다.
- `team.nesting_exceeded`: 중첩 깊이(이 팀 구성 = 0, 자식 = 1)가 `delegation.max_nesting`을 넘는다.
- `team.team_not_found`: 가리키는 팀 구성(또는 고정한 버전)이 없다.
- `team.child_no_entry`: 자식 팀 구성에 입구가 없다(자식 검증 요약).

이슈 위치: `node_id` = 중첩 팀 노드, `path` = 문서 기준 `/nodes/<i>/config/<binds.field>`.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_console_contracts import Graph
from agent_console_settings import escape_token

from ._check_context import TeamCheckContext
from ._issues import TeamIssueCodes, make_issue
from ._nested import find_team
from ._plan import TeamPlan, team_plan

_C = TeamIssueCodes

__all__ = ["check_nested_teams"]


@dataclass(frozen=True, slots=True)
class _Problem:
    code: str
    path: tuple[str, ...]


class _Children:
    """검증 한 번 동안 자식 팀 구성 조회·해석 결과를 기억한다."""

    def __init__(self, ctx: TeamCheckContext) -> None:
        self.ctx = ctx
        self._graphs: dict[tuple[str, str | None], Graph | None] = {}
        self._plans: dict[tuple[str, str | None], TeamPlan] = {}

    def graph(self, ref: str, version: str | None) -> Graph | None:
        key = (ref, version)
        if key not in self._graphs:
            lookup = self.ctx.teams
            self._graphs[key] = find_team(lookup, ref, version) if lookup is not None else None
        return self._graphs[key]

    def plan(self, ref: str, version: str | None) -> TeamPlan | None:
        key = (ref, version)
        if key not in self._plans:
            graph = self.graph(ref, version)
            if graph is None:
                return None
            parent = self.ctx.plan
            self._plans[key] = team_plan(
                graph,
                node_types=parent.node_types,
                edge_types=parent.edge_types,
                conventions=parent.conventions,
            )
        return self._plans[key]

    def walk(self, ref: str, version: str | None, path: tuple[str, ...]) -> _Problem | None:
        """`path`(루트 … `ref`)부터 자손을 따라가며 첫 순환·깊이 초과를 찾는다."""
        limit = self.ctx.max_nesting_setting
        if limit is not None and len(path) - 1 > limit:
            return _Problem(_C.TEAM_NESTING_EXCEEDED, path)
        plan = self.plan(ref, version)
        if plan is None:
            return None  # 없는 자손은 그 팀 구성의 검증이 알린다
        for nid, child in plan.team_refs.items():
            if child in path:
                return _Problem(_C.TEAM_RECURSIVE, (*path, child))
            found = self.walk(child, plan.team_versions.get(nid), (*path, child))
            if found is not None:
                return found
        return None


def _ref_path(ctx: TeamCheckContext, node_id: str) -> str | None:
    desc = ctx.plan.node_descriptors.get(node_id)
    if desc is None or desc.binds is None:
        return None
    for i, node in enumerate(ctx.plan.graph.nodes):
        if node.id == node_id:
            return f"/nodes/{i}/config/{escape_token(desc.binds.field)}"
    return None


def check_nested_teams(ctx: TeamCheckContext) -> None:
    """중첩 팀 노드마다 자기 참조·순환·깊이·자식 없음·자식 입구 없음(모두 error)."""
    plan = ctx.plan
    if not plan.team_refs:
        return
    children = _Children(ctx)
    root = plan.graph.id
    for nid, ref in plan.team_refs.items():
        version = plan.team_versions.get(nid)
        where = _ref_path(ctx, nid)
        label = ctx.label(nid)
        if ref == root:
            ctx.add(
                make_issue(
                    "error",
                    _C.TEAM_RECURSIVE,
                    f"'{label}' 노드가 이 팀 구성 자신을 넣습니다. 다른 팀 구성을 고르세요.",
                    node_id=nid,
                    path=where,
                    details={"path": [root, ref], "team": ref},
                )
            )
            continue
        if ctx.teams is None:
            continue
        child = children.plan(ref, version)
        if child is None:
            shown = f"{ref}@{version}" if version else ref
            ctx.add(
                make_issue(
                    "error",
                    _C.TEAM_NOT_FOUND,
                    f"'{label}' 노드의 팀 구성 '{shown}'을(를) 찾을 수 없습니다.",
                    node_id=nid,
                    path=where,
                    details={"team": ref, "version": version},
                )
            )
            continue
        if not child.entry_nodes:
            ctx.add(
                make_issue(
                    "error",
                    _C.TEAM_CHILD_NO_ENTRY,
                    f"'{label}' 노드의 팀 구성 '{child.graph.name or ref}'에 입구가 없어 "
                    "실행할 수 없습니다. 그 팀 구성에 입구 연결을 그려 주세요.",
                    node_id=nid,
                    path=where,
                    details={
                        "team": ref,
                        "version": version,
                        "issues": [{"code": _C.NO_ENTRY, "severity": "error"}],
                    },
                )
            )
        problem = children.walk(ref, version, (root, ref))
        if problem is None:
            continue
        chain = " → ".join(problem.path)
        if problem.code == _C.TEAM_RECURSIVE:
            ctx.add(
                make_issue(
                    "error",
                    _C.TEAM_RECURSIVE,
                    f"'{label}' 노드의 팀 구성이 순환합니다({chain}). 순환을 끊으세요.",
                    node_id=nid,
                    path=where,
                    details={"path": list(problem.path), "team": ref},
                )
            )
        else:
            depth = len(problem.path) - 1
            limit = ctx.max_nesting_setting
            ctx.add(
                make_issue(
                    "error",
                    _C.TEAM_NESTING_EXCEEDED,
                    f"'{label}' 노드의 팀 구성 중첩 깊이 {depth}이(가) 한도({limit})를 넘습니다"
                    f"({chain}). 설정 delegation.max_nesting을 늘리거나 중첩을 줄이세요.",
                    node_id=nid,
                    path=where,
                    details={"depth": depth, "limit": limit, "path": list(problem.path)},
                )
            )
