"""조건 연산자 레지스트리와 로딩(X22 entry point `agent_console.condition_operators`)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from importlib.metadata import EntryPoint
from typing import Any, Final

from agent_console_contracts import ConditionOperatorDescriptor
from agent_console_registry import LoadReport, Registry, load_entry_points

from ._protocol import ConditionOperator

CONDITION_OPERATORS_GROUP: Final = "agent_console.condition_operators"
"""X22 entry point 그룹. 이름 = 등록 key = 디스크립터 id."""

CONDITION_OPERATORS_EXTENSION: Final = "condition_operators"
"""레지스트리 이름(메시지·이름 붙은 확장 레지스트리 이름)."""


def as_condition_operator(obj: Any) -> ConditionOperator:
    """로드한 객체를 조건 연산자로 검사한다(클래스면 인자 없이 인스턴스화).

    Raises:
        TypeError: `descriptor`(ConditionOperatorDescriptor)·`evaluate`가 없을 때.
    """
    item = obj() if isinstance(obj, type) else obj
    if not isinstance(getattr(item, "descriptor", None), ConditionOperatorDescriptor) or not (
        isinstance(item, ConditionOperator)
    ):
        raise TypeError(f"condition_operator가 아니다: {obj!r}")
    return item


def new_operator_registry(name: str = CONDITION_OPERATORS_EXTENSION) -> Registry[ConditionOperator]:
    """검사기(`as_condition_operator`)가 붙은 빈 레지스트리."""
    return Registry(name, validator=as_condition_operator)


def load_condition_operators(
    registry: Registry[ConditionOperator],
    *,
    enabled: set[str] | None = None,
    entry_points: Iterable[EntryPoint] | None = None,
) -> list[LoadReport]:
    """entry point 그룹 `agent_console.condition_operators`를 `registry`에 로드한다.

    기본 연산자 10개도 이 패키지의 entry point로 같은 길을 탄다(특별 취급 없음).

    Args:
        registry: 대상 레지스트리(보통 `new_operator_registry()`).
        enabled: 주어지면 이 이름만 로드.
        entry_points: 테스트용 주입(그룹이 맞는 것만 쓴다).

    Returns:
        항목별 `LoadReport`(실패는 예외가 아니라 보고).
    """
    eps = None
    if entry_points is not None:
        eps = [ep for ep in entry_points if ep.group == CONDITION_OPERATORS_GROUP]
    return load_entry_points(
        CONDITION_OPERATORS_GROUP,
        registry,
        enabled=enabled,
        validate=as_condition_operator,
        entry_points=eps,
    )


def operator_map(registry: Registry[ConditionOperator]) -> dict[str, ConditionOperator]:
    """레지스트리 → `{id: 연산자}`(key별 최신). 평가·검사 함수에 넘긴다."""
    return {entry.key: entry.item for entry in registry.list()}


def operator_descriptors(
    operators: Mapping[str, ConditionOperator] | Registry[ConditionOperator],
) -> list[ConditionOperatorDescriptor]:
    """연산자 디스크립터 목록(id 순). `GET /condition-operators` 응답 모양."""
    found = operator_map(operators) if isinstance(operators, Registry) else dict(operators)
    return [found[key].descriptor for key in sorted(found)]


def default_operators(
    *, entry_points: Iterable[EntryPoint] | None = None
) -> tuple[dict[str, ConditionOperator], list[LoadReport]]:
    """설치된 entry point로 새 레지스트리를 채워 `({id: 연산자}, 보고)`를 돌려준다.

    부를 때마다 새로 읽는다(전역 상태 없음).
    """
    registry = new_operator_registry()
    reports = load_condition_operators(registry, entry_points=entry_points)
    return operator_map(registry), reports
