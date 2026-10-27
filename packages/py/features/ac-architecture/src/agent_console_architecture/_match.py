"""이벤트 하나 → 맞은 칸·연결·묶음(순수 판정).

칸·연결은 프로필의 조건(`ConditionSpec`)으로만 판정한다. 시간상 이웃은 보지 않는다(R8.6):
연결은 그 전달을 기록한 이벤트 하나가 조건에 맞을 때만 센다. 칸·연결·범주·도구 이름은 이 모듈에
없고 전부 프로필 데이터에서 온다.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agent_console_conditions import (
    MISSING,
    CompiledConditions,
    ConditionOperator,
    SubjectPredicate,
    compile_conditions,
    compile_pointer,
    condition_keys,
    necessary_items,
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

GATE_KEYS = 3
"""거르기에 쓰는 최상위 키 수 상한(많이 쓰이는 키부터)."""

GATE_TABLE_LIMIT = 4096
"""거르기 표(최상위 키 값 묶음 → 판정할 칸·연결)에 기억할 묶음 수. 넘으면 새 묶음은 매번 거른다."""

MATCH_TABLE_LIMIT = 4096
"""같은 판정 결과(`EventMatch`)를 나눠 쓰려고 기억할 결과 수. 넘으면 새 결과는 기억하지 않는다."""

type _CellCheck = tuple[str, SubjectPredicate, Callable[[Any], Any] | None]
type _EdgeCheck = tuple[str, SubjectPredicate]


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
        self._edges: list[tuple[str, CompiledConditions]] = []
        edge_specs: list[ConditionSpec] = []
        for eid, edge in first.items():
            if edge.when is not None and is_observed_kind(edge.kind):
                self._edges.append((eid, compile_conditions(edge.when, operators)))
                edge_specs.append(edge.when)
        self._error_when = (
            compile_conditions(profile.error_when, operators)
            if profile.error_when is not None
            else None
        )
        # 판정은 컴파일한 함수를 바로 부른다(이벤트마다 수십 번 — 메서드 호출 한 단계를 줄인다)
        self._cell_checks: tuple[_CellCheck, ...] = tuple(
            (cid, c.predicate, g) for cid, c, g in self._cells
        )
        self._edge_checks: tuple[_EdgeCheck, ...] = tuple(
            (eid, c.predicate) for eid, c in self._edges
        )
        self._error_check = self._error_when.predicate if self._error_when is not None else None
        cell_specs = [cell.when for cell in profile.cells.values() if cell.when is not None]
        # 맞을 수 없는 칸·연결을 최상위 키 값으로 미리 거른다(결과는 같다, `_Gate`)
        self._gate = _Gate.build(
            list(zip(cell_specs, self._cell_checks, strict=True)),
            list(zip(edge_specs, self._edge_checks, strict=True)),
            operators,
        )
        self._results: dict[Any, EventMatch] = {}

    def match_subject(self, subject: Mapping[str, Any]) -> EventMatch:
        """이미 만든 판단 대상(`event_subject`)으로 판정한다.

        결과는 같은 결과끼리 같은 객체를 나눠 쓸 수 있다(`EventMatch`는 바꾸지 않는 값이다).
        """
        cell_checks: Sequence[tuple[str, SubjectPredicate | None, Callable[[Any], Any] | None]]
        edge_checks: Sequence[tuple[str, SubjectPredicate | None]]
        if self._gate is not None:
            cell_checks, edge_checks = self._gate.candidates(subject)
        else:
            cell_checks, edge_checks = self._cell_checks, self._edge_checks
        hit = [
            (cid, group_of)
            for cid, holds, group_of in cell_checks
            if holds is None or holds(subject)
        ]
        cells = tuple(cid for cid, _ in hit)
        groups = tuple((cid, _group_value(of(subject))) for cid, of in hit if of is not None)
        edges = tuple(eid for eid, holds in edge_checks if holds is None or holds(subject))
        category = subject.get("category")
        error = isinstance(category, str) and category in self.error_categories
        if not error and self._error_check is not None:
            error = bool(self._error_check(subject))
        key = (cells, edges, groups, error)
        found = self._results.get(key)
        if found is None:
            found = EventMatch(cells=cells, edges=edges, groups=dict(groups), error=error)
            if len(self._results) < MATCH_TABLE_LIMIT:
                self._results[key] = found
        return found

    def match(self, event: LogEvent) -> EventMatch:
        """이벤트 하나를 판정한다."""
        return self.match_subject(event_subject(event))


class _Gate:
    """최상위 키 몇 개의 값으로 칸·연결을 미리 판정하거나 거른다(판정 결과는 같다).

    칸·연결 조건 중 "참이려면 반드시 참인 `/키` 항목"(`necessary_items`)이 많이 쓰는 키를 최대
    `GATE_KEYS`개 고른다(둘 이상의 칸·연결이 쓰는 키만). 그 키들 값의 묶음(형식까지 같아야 같은
    값)마다 한 번,

    - 조건이 고른 키만 읽는 칸·연결(`condition_keys`)은 결과 자체를 기억하고(이벤트마다 판정하지
      않음),
    - 나머지는 고른 키의 필수 항목으로 맞을 수 없는 것을 거른다(남은 것만 이벤트마다 전체 조건으로).

    값을 해시할 수 없으면 거르지 않는다(모든 칸·연결을 판정).
    """

    def __init__(
        self,
        keys: tuple[str, ...],
        cells: tuple[tuple[_CellCheck, _Mode], ...],
        edges: tuple[tuple[_EdgeCheck, _Mode], ...],
    ) -> None:
        self.keys = keys
        self._cells = cells
        self._edges = edges
        self._all: _Entry = (
            tuple((cid, holds, of) for (cid, holds, of), _ in cells),
            tuple((eid, holds) for (eid, holds), _ in edges),
        )
        self._table: dict[tuple[Any, ...], _Entry] = {}

    @classmethod
    def build(
        cls,
        cells: list[tuple[ConditionSpec, _CellCheck]],
        edges: list[tuple[ConditionSpec, _EdgeCheck]],
        operators: Mapping[str, ConditionOperator],
    ) -> _Gate | None:
        """거를 키가 둘 이상의 칸·연결에 쓰일 때만 만든다(아니면 None)."""
        specs = [spec for spec, _ in (*cells, *edges)]
        items = [necessary_items(spec, operators) for spec in specs]
        counts: dict[str, int] = {}
        for found in items:
            for k in dict.fromkeys(k for k, _ in found):
                counts[k] = counts.get(k, 0) + 1
        order = sorted(counts, key=lambda k: -counts[k])  # 같은 수면 먼저 나온 키
        keys = tuple(k for k in order[:GATE_KEYS] if counts[k] >= 2)
        if not keys:
            return None
        chosen = frozenset(keys)

        def mode(spec: ConditionSpec, found: tuple[tuple[str, SubjectPredicate], ...]) -> _Mode:
            reads = condition_keys(spec)
            if reads is not None and reads <= chosen:
                return _EXACT
            return _all_of(found, chosen)

        modes = [mode(spec, found) for spec, found in zip(specs, items, strict=True)]
        return cls(
            keys,
            tuple(zip((c for _, c in cells), modes[: len(cells)], strict=True)),
            tuple(zip((e for _, e in edges), modes[len(cells) :], strict=True)),
        )

    def candidates(self, subject: Mapping[str, Any]) -> _Entry:
        """이 판단 대상의 (칸, 연결) 판정 목록(선언 순서). 판정 함수가 None이면 이미 참이다."""
        if type(subject) is not dict:
            return self._all
        get = subject.get
        try:
            slot = tuple([_freeze(get(k, MISSING)) for k in self.keys])
            found = self._table.get(slot)
        except TypeError:  # 해시할 수 없는 값
            return self._all
        if found is None:
            found = (
                tuple(
                    _entry(check, how, subject)
                    for check, how in self._cells
                    if _keep(check[1], how, subject)
                ),
                tuple(
                    _entry(check, how, subject)
                    for check, how in self._edges
                    if _keep(check[1], how, subject)
                ),
            )
            if len(self._table) < GATE_TABLE_LIMIT:
                self._table[slot] = found
        return found


class _Exact:
    """거르기 표지: 조건이 고른 키만 읽어 결과를 값 묶음마다 기억한다."""


_EXACT: Final = _Exact()

type _Mode = SubjectPredicate | _Exact | None
"""칸·연결 하나의 거르기 방식: 기억(`_EXACT`), 필수 항목으로 거르기(판정 함수), 안 거름(None)."""

type _Entry = tuple[
    tuple[tuple[str, SubjectPredicate | None, Callable[[Any], Any] | None], ...],
    tuple[tuple[str, SubjectPredicate | None], ...],
]


def _keep(holds: SubjectPredicate, how: _Mode, subject: Mapping[str, Any]) -> bool:
    if how is None:
        return True
    if isinstance(how, _Exact):
        return bool(holds(subject))
    return bool(how(subject))


def _entry(check: tuple[Any, ...], how: _Mode, subject: Mapping[str, Any]) -> Any:
    """표에 넣을 항목: 기억한 칸·연결은 판정 함수 자리를 None(이미 참)으로."""
    if isinstance(how, _Exact):
        return (check[0], None, *check[2:])
    return check


def _freeze(value: Any) -> Any:
    """값 → 해시 가능한 같음 키(형식까지 같아야 같은 키). 해시할 수 없으면 TypeError.

    문자열은 그대로(다른 형식은 튜플이라 섞이지 않는다), 나머지는 (형식, 값)이다 — `True`·`1`·
    `1.0`은 다른 키다.
    """
    kind = type(value)
    if kind is str:
        return value
    if kind is list:
        return (list, tuple(_freeze(v) for v in value))
    if kind is dict:
        return (dict, tuple(sorted((k, _freeze(v)) for k, v in value.items())))
    hash(value)
    return (kind, value)


def _all_of(
    items: tuple[tuple[str, SubjectPredicate], ...], keys: frozenset[str]
) -> SubjectPredicate | None:
    """`keys`의 항목 판정들의 그리고(없으면 None — 거르지 않는다)."""
    checks = tuple(check for k, check in items if k in keys)
    if not checks:
        return None
    if len(checks) == 1:
        return checks[0]
    return lambda subject: all(check(subject) for check in checks)


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
