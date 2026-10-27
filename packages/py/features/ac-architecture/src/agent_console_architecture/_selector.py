"""선택 필터 `arch`(`<프로필 id>:<cell|edge|unassigned>[:<id>]`) 만들기·읽기와 이벤트 판정 함수."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass

from agent_console_conditions import ConditionOperator
from agent_console_contracts.architecture import (
    ArchitectureProfile,
    ArchitectureSelector,
    KnownArchitectureTargets,
)
from agent_console_contracts.logs import LogEvent

from ._match import ProfileMatcher, is_observed_kind

_SEP = ":"


class ArchitectureSelectorError(ValueError):
    """선택 필터를 쓸 수 없다(형식이 틀림, 다른 프로필, 없는 칸·연결, 묶을 값이 없는 칸의 묶음)."""


@dataclass(frozen=True, slots=True)
class ArchTarget:
    """`arch` 문자열을 읽은 결과.

    Attributes:
        profile: 프로필 id.
        kind: 대상 종류(`cell`·`edge`·`unassigned`).
        id: 칸·연결 id(`unassigned`면 None).
    """

    profile: str
    kind: str
    id: str | None = None


def format_arch(profile_id: str, kind: str, target_id: str | None = None) -> str:
    """`arch` 문자열을 만든다(`<프로필>:<종류>` 또는 `<프로필>:<종류>:<id>`)."""
    parts = [profile_id, kind] if target_id is None else [profile_id, kind, target_id]
    return _SEP.join(parts)


def parse_arch(value: str) -> ArchTarget:
    """`arch` 문자열을 읽는다. 칸·연결 id에는 `:`가 들어가도 된다(셋째 조각 전체).

    Raises:
        ArchitectureSelectorError: 형식이 틀렸을 때.
    """
    profile, sep, rest = value.partition(_SEP)
    if not sep or not profile:
        raise ArchitectureSelectorError(f"구조도 선택 형식이 아닙니다: {value!r}")
    kind, sep, target = rest.partition(_SEP)
    if kind == KnownArchitectureTargets.UNASSIGNED and not sep:
        return ArchTarget(profile=profile, kind=kind)
    if kind in (KnownArchitectureTargets.CELL, KnownArchitectureTargets.EDGE) and target:
        return ArchTarget(profile=profile, kind=kind, id=target)
    raise ArchitectureSelectorError(f"구조도 선택 형식이 아닙니다: {value!r}")


EventPredicate = Callable[[LogEvent], bool]
"""이벤트 판정 함수(참 = 표에 남긴다)."""


def selector_predicate(
    profile: ArchitectureProfile,
    selector: ArchitectureSelector,
    *,
    profile_id: str,
    operators: Mapping[str, ConditionOperator],
) -> EventPredicate:
    """선택 필터 → 이벤트 판정 함수. 투영 결과의 같은 대상 `count`와 같은 이벤트를 고른다.

    판정 = 대상 조건에 맞음 AND (`arch_group`이 있으면 같은 묶음) AND (`arch_sources`가 있으면 그
    출처). 수 일치를 위해 질의 쪽은 투영 결과의 `max_seq`를 함께 걸어야 한다.

    Args:
        profile: 프로필.
        selector: 선택 필터(투영 결과의 `selector`).
        profile_id: 이 프로필의 id(`arch`의 프로필과 같아야 한다).
        operators: 조건 연산자.

    Returns:
        이벤트 판정 함수(순수 함수, 같은 이벤트에 늘 같은 값).

    Raises:
        ArchitectureSelectorError: 형식이 틀렸거나 다른 프로필, 없는 칸·연결, 묶을 값이 없는 대상에
            묶음 값을 줬을 때.
    """
    target = parse_arch(selector.arch)
    if target.profile != profile_id:
        raise ArchitectureSelectorError(
            f"구조도 선택의 프로필 {target.profile!r}이(가) {profile_id!r}과(와) 다릅니다"
        )
    matcher = ProfileMatcher(profile, operators)
    group = selector.arch_group
    sources: Collection[str] | None = (
        frozenset(selector.arch_sources) if selector.arch_sources is not None else None
    )
    want_group: str | None = group or None

    if target.kind == KnownArchitectureTargets.CELL:
        cell_id = target.id or ""
        cell = profile.cells.get(cell_id)
        if cell is None:
            raise ArchitectureSelectorError(
                f"프로필 {profile_id!r}에 칸 {cell_id!r}이(가) 없습니다"
            )
        if group is not None and cell.group_by is None:
            raise ArchitectureSelectorError(f"칸 {cell_id!r}은(는) 묶을 값이 없습니다")

        def hit(event: LogEvent) -> bool:
            found = matcher.match(event)
            if cell_id not in found.cells:
                return False
            return group is None or found.groups.get(cell_id) == want_group

    elif target.kind == KnownArchitectureTargets.EDGE:
        edge_id = target.id or ""
        edge = next((e for e in profile.edges if e.id == edge_id), None)
        if edge is None:
            raise ArchitectureSelectorError(
                f"프로필 {profile_id!r}에 연결 {edge_id!r}이(가) 없습니다"
            )
        if group is not None:
            raise ArchitectureSelectorError("연결에는 묶음 값을 줄 수 없습니다")
        if not is_observed_kind(edge.kind):
            return lambda _event: False

        def hit(event: LogEvent) -> bool:
            return edge_id in matcher.match(event).edges

    else:
        if group is not None:
            raise ArchitectureSelectorError("분류 안 됨에는 묶음 값을 줄 수 없습니다")
        if not profile.unassigned:
            return lambda _event: False

        def hit(event: LogEvent) -> bool:
            return matcher.match(event).unassigned

    if sources is None:
        return hit
    allowed = sources

    def hit_from_sources(event: LogEvent) -> bool:
        return event.source in allowed and hit(event)

    return hit_from_sources
