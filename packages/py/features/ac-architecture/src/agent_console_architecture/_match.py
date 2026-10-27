"""이벤트 하나 → 맞은 칸·연결·묶음(순수 판정).

칸·연결은 프로필의 조건(`ConditionSpec`)으로만 판정한다. 시간상 이웃은 보지 않는다(R8.6):
연결은 그 전달을 기록한 이벤트 하나가 조건에 맞을 때만 센다. 칸·연결·범주·도구 이름은 이 모듈에
없고 전부 프로필 데이터에서 온다.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from typing import Any

from agent_console_conditions import (
    MISSING,
    CompiledConditions,
    ConditionOperator,
    compile_conditions,
    compile_pointer,
)
from agent_console_contracts.architecture import (
    ArchitectureEdge,
    ArchitectureGroupRef,
    ArchitectureMembership,
    ArchitectureProfile,
    KnownArchitectureEdgeKinds,
)
from agent_console_contracts.logs import LogEvent


def event_subject(event: LogEvent) -> dict[str, Any]:
    """조건이 볼 판단 대상(이벤트 JSON, 키는 계약 별칭 — `from` 등)."""
    return event.model_dump(mode="json", by_alias=True)


def _group_value(value: Any) -> str | None:
    """묶음 값. 값이 없거나 null·빈 문자열이면 None("(이름 없음)" 묶음).

    문자열은 그대로, 다른 값은 JSON 글(키 정렬)로 바꾼다. 선택 필터 `arch_group`의 빈 문자열은
    None 묶음과 같다.
    """
    if value is MISSING or value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def is_observed_kind(kind: str) -> bool:
    """프로필 연결 종류가 기록된 전달을 세는 종류인지. 모르는 종류는 구조 연결로 다룬다."""
    return kind == KnownArchitectureEdgeKinds.OBSERVED


@dataclass(frozen=True, slots=True)
class EventMatch:
    """이벤트 하나의 판정 결과.

    Attributes:
        cells: 맞은 칸 id(프로필 선언 순서).
        edges: 맞은 관측 연결 id(선언 순서).
        groups: 맞은 칸 중 묶을 값이 있는 칸 → 묶음 값(None = 값 없음).
        error: 오류 조건(`error_when`)에 맞거나 오류 범주인지.
    """

    cells: tuple[str, ...]
    edges: tuple[str, ...]
    groups: Mapping[str, str | None]
    error: bool

    @property
    def unassigned(self) -> bool:
        """어느 칸에도 맞지 않음."""
        return not self.cells


class ProfileMatcher:
    """프로필 하나로 이벤트를 판정하는 순수 판정기(입력이 같으면 결과가 같다 — 캐시해도 된다).

    만들 때 칸·연결·`error_when` 조건을 한 번 컴파일한다(`ac-conditions` `compile_conditions`:
    경로 해석·연산자 찾기·기대 값 묶기). 판정은 근거 없이 참·거짓만 낸다. 연산자는 만들 때의
    `operators`로 정해진다(등록이 바뀌면 새로 만든다 — 연동 모듈의 프로필 키가 연산자 동일성을
    본다).

    Args:
        profile: 프로필.
        operators: 조건 연산자 id → 연산자(X22, 보통 `default_operators()[0]`).
        error_categories: 오류로 볼 범주 id(분류 체계에서 오류로 표시한 범주, 호출자가 넘긴다).
    """

    def __init__(
        self,
        profile: ArchitectureProfile,
        operators: Mapping[str, ConditionOperator],
        *,
        error_categories: Collection[str] = frozenset(),
    ) -> None:
        self.profile = profile
        self.operators = operators
        self.error_categories = frozenset(error_categories)
        self._cells: list[tuple[str, CompiledConditions, Callable[[Any], Any] | None]] = [
            (
                cid,
                compile_conditions(cell.when, operators),
                compile_pointer(cell.group_by) if cell.group_by is not None else None,
            )
            for cid, cell in profile.cells.items()
            if cell.when is not None
        ]
        # 같은 id의 연결이 여럿이면 처음 것만 쓴다(프로필 검사가 중복 id를 알린다).
        first: dict[str, ArchitectureEdge] = {}
        for edge in profile.edges:
            first.setdefault(edge.id, edge)
        self._edges = [
            (eid, compile_conditions(edge.when, operators))
            for eid, edge in first.items()
            if edge.when is not None and is_observed_kind(edge.kind)
        ]
        self._error_when = (
            compile_conditions(profile.error_when, operators)
            if profile.error_when is not None
            else None
        )
        # 판정은 컴파일한 함수를 바로 부른다(이벤트마다 수십 번 — 메서드 호출 한 단계를 줄인다)
        self._cell_checks = tuple((cid, c.predicate, g) for cid, c, g in self._cells)
        self._edge_checks = tuple((eid, c.predicate) for eid, c in self._edges)
        self._error_check = self._error_when.predicate if self._error_when is not None else None

    def match_subject(self, subject: Mapping[str, Any]) -> EventMatch:
        """이미 만든 판단 대상(`event_subject`)으로 판정한다."""
        hit = [(cid, group_of) for cid, holds, group_of in self._cell_checks if holds(subject)]
        groups = {cid: _group_value(of(subject)) for cid, of in hit if of is not None}
        edges = tuple(eid for eid, holds in self._edge_checks if holds(subject))
        error = subject.get("category") in self.error_categories
        if not error and self._error_check is not None:
            error = self._error_check(subject)
        return EventMatch(
            cells=tuple(cid for cid, _ in hit), edges=edges, groups=groups, error=error
        )

    def match(self, event: LogEvent) -> EventMatch:
        """이벤트 하나를 판정한다."""
        return self.match_subject(event_subject(event))


def event_membership(
    event: LogEvent,
    profile: ArchitectureProfile,
    *,
    profile_id: str,
    operators: Mapping[str, ConditionOperator],
) -> ArchitectureMembership:
    """이벤트 하나가 맞은 칸·연결·묶음(표에서 고른 이벤트 강조용).

    Args:
        event: 로그 이벤트.
        profile: 프로필.
        profile_id: 프로필 id(결과에 싣는다).
        operators: 조건 연산자.

    Returns:
        `ArchitectureMembership`. `unassigned`는 프로필이 분류 안 됨을 셀 때만 참일 수 있다.
    """
    found = ProfileMatcher(profile, operators).match(event)
    return ArchitectureMembership(
        profile=profile_id,
        uid=event.uid,
        cells=list(found.cells),
        edges=list(found.edges),
        groups=[ArchitectureGroupRef(cell=cid, key=key) for cid, key in found.groups.items()],
        unassigned=bool(profile.unassigned and found.unassigned),
    )
