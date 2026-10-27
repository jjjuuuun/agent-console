"""이벤트 하나 → 맞은 칸·연결·묶음(순수 판정).

칸·연결은 프로필의 조건(`ConditionSpec`)으로만 판정한다. 시간상 이웃은 보지 않는다(R8.6):
연결은 그 전달을 기록한 이벤트 하나가 조건에 맞을 때만 센다. 칸·연결·범주·도구 이름은 이 모듈에
없고 전부 프로필 데이터에서 온다.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from agent_console_conditions import (
    MISSING,
    ConditionOperator,
    evaluate_conditions,
    resolve_pointer,
)
from agent_console_contracts import ConditionSpec
from agent_console_contracts.architecture import (
    ArchitectureEdge,
    ArchitectureGroupRef,
    ArchitectureMembership,
    ArchitectureProfile,
    KnownArchitectureEdgeKinds,
)
from agent_console_contracts.logs import LogEvent


def _drop_actual(_value: Any) -> None:
    # 판정 근거의 실제 값은 쓰지 않는다. 가림 함수로 None을 주면 근거를 줄이는 비용(긴 목록의 JSON
    # 직렬화)이 없어진다. 결과(참·거짓)는 같다.
    return None


def event_subject(event: LogEvent) -> dict[str, Any]:
    """조건이 볼 판단 대상(이벤트 JSON, 키는 계약 별칭 — `from` 등)."""
    return event.model_dump(mode="json", by_alias=True)


def condition_holds(
    spec: ConditionSpec, subject: Any, operators: Mapping[str, ConditionOperator]
) -> bool:
    """조건 판정(참·거짓만). 근거는 만들지 않는다."""
    return evaluate_conditions(spec, subject, operators, redact=_drop_actual).result


def group_key(subject: Any, pointer: str) -> str | None:
    """묶음 값. 값이 없거나 null·빈 문자열이면 None("(이름 없음)" 묶음).

    문자열은 그대로, 다른 값은 JSON 글(키 정렬)로 바꾼다. 선택 필터 `arch_group`의 빈 문자열은
    None 묶음과 같다.
    """
    value = resolve_pointer(subject, pointer)
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
        self._cells = [
            (cid, cell.when, cell.group_by)
            for cid, cell in profile.cells.items()
            if cell.when is not None
        ]
        # 같은 id의 연결이 여럿이면 처음 것만 쓴다(프로필 검사가 중복 id를 알린다).
        first: dict[str, ArchitectureEdge] = {}
        for edge in profile.edges:
            first.setdefault(edge.id, edge)
        self._edges = [
            (eid, edge.when)
            for eid, edge in first.items()
            if edge.when is not None and is_observed_kind(edge.kind)
        ]

    def match_subject(self, subject: Mapping[str, Any]) -> EventMatch:
        """이미 만든 판단 대상(`event_subject`)으로 판정한다."""
        cells: list[str] = []
        groups: dict[str, str | None] = {}
        for cid, spec, pointer in self._cells:
            if condition_holds(spec, subject, self.operators):
                cells.append(cid)
                if pointer is not None:
                    groups[cid] = group_key(subject, pointer)
        edges = [eid for eid, spec in self._edges if condition_holds(spec, subject, self.operators)]
        error = subject.get("category") in self.error_categories
        if not error and self.profile.error_when is not None:
            error = condition_holds(self.profile.error_when, subject, self.operators)
        return EventMatch(cells=tuple(cells), edges=tuple(edges), groups=groups, error=error)

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
