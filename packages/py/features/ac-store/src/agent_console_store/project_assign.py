"""기록의 프로젝트 넣기·개수 집계 — 저장소 종류와 무관한 순수 로직과 저장소 포트.

실행(Run)·대화처럼 `project_id`(불투명 문자열)를 가진 기록 저장소가 `ProjectAssignStore`를 구현하면
`count_projects`·`assign_project`가 계약(`ProjectCounts`·`AssignProjectResult`)대로 동작한다.
기록이 어디에 저장되는지(앱 DB, 프로젝트 DB, 메모리)는 모른다. 프로젝트가 무엇인지도 모른다.

규칙(design §PI.8, K33-9 — 사용자가 누를 때만 고쳐 쓴다):
- `from_null`: `project_id`가 null인 기록만 넣는다. 이미 다른 프로젝트인 기록은 건드리지 않는다.
- `ids`: 명시한 기록은 지금 프로젝트가 무엇이든 옮긴다. 이미 그 프로젝트면 변화 없음
  (건너뛴 것으로 세지 않는다).
- 실행 중인 Run(`busy`)이 있는 실행 트리는 넣지 않고 `busy`로 건너뛴다
  (실행기가 나중에 저장하면 덮어쓴다).
- 루트 Run을 넣으면 그 자손도 함께 넣는다(`ids`는 자손 전부, `from_null`은 null인 자손만).
  자식 Run 하나만 `ids`로 주면 그 Run만 옮긴다.

>>> from agent_console_contracts import AssignProjectRequest
>>> class Rows:
...     def __init__(self): self.rows = {"a": None, "b": "x"}
...     def project_id_counts(self):
...         out = {}
...         for p in self.rows.values(): out[p] = out.get(p, 0) + 1
...         return out
...     def candidates(self, ids):
...         return [AssignCandidate(i, p) for i, p in self.rows.items()
...                 if (p is None if ids is None else i in ids)]
...     def set_project(self, ids, project_id):
...         for i in ids: self.rows[i] = project_id
...         return len(ids)
>>> store = Rows()
>>> count_projects(store).no_project
1
>>> assign_project(store, AssignProjectRequest(to="p", from_null=True)).assigned
1
>>> store.rows
{'a': 'p', 'b': 'x'}
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from agent_console_contracts import (
    AssignProjectRequest,
    AssignProjectResult,
    AssignProjectSkip,
    ProjectCounts,
)

SKIP_NOT_FOUND = "not_found"
SKIP_PARENT_ELSEWHERE = "parent_elsewhere"
SKIP_BUSY = "busy"


@dataclass(frozen=True)
class AssignCandidate:
    """넣기 대상 후보 한 건.

    Attributes:
        id: 기록 id.
        project_id: 지금 프로젝트(null = 없음).
        root_id: 이 기록이 속한 루트 기록 id(루트 자신·계층이 없는 기록은 None).
        busy: 지금 실행 중이라 실행기가 나중에 덮어쓸 수 있는 기록. 넣지 않고 `busy`로 건너뛴다
            (그 기록이 속한 루트도 함께 건너뛴다 — 한 실행 트리는 같은 프로젝트에 있어야 한다).
    """

    id: str
    project_id: str | None
    root_id: str | None = None
    busy: bool = False


class ProjectAssignStore(Protocol):
    """`project_id`를 가진 기록 저장소가 구현하는 포트(Run 저장소·대화 저장소 등)."""

    def project_id_counts(self) -> Mapping[str | None, int]:
        """project_id별 기록 수(null 키 = 프로젝트 없음). 계층이 있으면 루트만 센다."""
        ...

    def candidates(self, ids: Collection[str] | None) -> list[AssignCandidate]:
        """`ids`가 None이면 project_id가 null인 모든 기록, 아니면 그 id의 기록과 그 자손들.

        없는 id는 돌려주지 않는다.
        """
        ...

    def set_project(self, ids: Collection[str], project_id: str) -> int:
        """그 기록들의 project_id를 바꾸고 바뀐 수를 돌려준다(한 트랜잭션)."""
        ...


@dataclass(frozen=True)
class AssignPlan:
    """넣기 계획: 바꿀 id와 건너뛴 기록."""

    assign_ids: list[str]
    skipped: list[AssignProjectSkip] = field(default_factory=list)


def to_project_counts(counts: Mapping[str | None, int]) -> ProjectCounts:
    """project_id별 개수를 `ProjectCounts`로 바꾼다(0건 키는 뺀다)."""
    no_project = counts.get(None, 0)
    by_project = {k: v for k, v in counts.items() if k is not None and v > 0}
    return ProjectCounts(
        total=no_project + sum(by_project.values()), no_project=no_project, by_project=by_project
    )


def plan_assignment(request: AssignProjectRequest, candidates: list[AssignCandidate]) -> AssignPlan:
    """요청과 후보로 넣기 계획을 만든다(순수 함수, 저장소를 만지지 않는다)."""
    to = request.to
    by_id = {c.id: c for c in candidates}
    children: dict[str, list[AssignCandidate]] = {}
    for c in candidates:
        if c.root_id is not None:
            children.setdefault(c.root_id, []).append(c)
    skipped: list[AssignProjectSkip] = []
    chosen: dict[str, None] = {}  # 순서를 지키는 집합

    if request.ids is not None:
        for rid in dict.fromkeys(request.ids):
            row = by_id.get(rid)
            if row is None:
                skipped.append(AssignProjectSkip(id=rid, reason=SKIP_NOT_FOUND))
                continue
            subtree = [row, *children.get(rid, ())]
            if any(c.busy for c in subtree):
                skipped.append(
                    AssignProjectSkip(id=rid, reason=SKIP_BUSY, project_id=row.project_id)
                )
                continue
            for c in subtree:  # 루트면 자손도
                if c.project_id != to:
                    chosen[c.id] = None
        return AssignPlan(list(chosen), skipped)

    # from_null: 후보는 모두 project_id가 null이다. 루트(또는 계층 없음)를 고르고 그 자손을 따른다.
    roots = {c.id for c in candidates if c.root_id is None}
    busy_roots = {c.id if c.root_id is None else c.root_id for c in candidates if c.busy}
    for c in candidates:
        if c.project_id is not None:
            continue
        if (c.id if c.root_id is None else c.root_id) in busy_roots:
            if c.root_id is None:
                skipped.append(AssignProjectSkip(id=c.id, reason=SKIP_BUSY))
        elif c.root_id is None or c.root_id in roots:
            chosen[c.id] = None
        else:  # 루트가 이미 프로젝트에 있다 — 자손만 따로 옮기지 않는다
            skipped.append(AssignProjectSkip(id=c.id, reason=SKIP_PARENT_ELSEWHERE))
    return AssignPlan(list(chosen), skipped)


def count_projects(store: ProjectAssignStore) -> ProjectCounts:
    """저장소의 기록 개수(전체·프로젝트 없음·프로젝트별)."""
    return to_project_counts(store.project_id_counts())


def assign_project(store: ProjectAssignStore, request: AssignProjectRequest) -> AssignProjectResult:
    """요청대로 기록을 프로젝트에 넣는다. 넣은 수와 건너뛴 기록을 돌려준다."""
    candidates = store.candidates(None if request.ids is None else request.ids)
    plan = plan_assignment(request, candidates)
    assigned = store.set_project(plan.assign_ids, request.to) if plan.assign_ids else 0
    return AssignProjectResult(assigned=assigned, skipped=plan.skipped)
