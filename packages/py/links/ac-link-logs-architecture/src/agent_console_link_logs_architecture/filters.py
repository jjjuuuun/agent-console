"""이벤트 표 필터 ``arch``·``arch_group``·``arch_sources``(X28, 포트 ``logs.filter_predicates``).

필터 이름은 계약 ``ArchitectureSelector``의 필드 이름이다(구조도 결과의 ``selector``를 그대로
질의 인자로 넘긴다). 판정은 ``selector_predicate``이고, 판정기는 범위 캐시를 먼저 본다
(``MemoMatcher`` — 구조도를 그린 범위의 이벤트는 다시 판정하지 않는다).

표의 전체 수가 칸의 ``count``와 같으려면 표 질의에 구조도 결과의 ``max_seq``와 같은 범위 필터를
함께 넘긴다(design §5.5R.2.4).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Final

from agent_console_architecture import ArchitectureSelectorError, parse_arch, selector_predicate
from agent_console_contracts.architecture import ArchitectureSelector
from agent_console_contracts.logs import LogFilterFieldInfo
from agent_console_logs import EventPredicate, LogFilterContext

from .ports import ArchitectureCatalogReader
from .scopes import MemoMatcher, ScopeCache, profile_key

_FIELDS: Final = ArchitectureSelector.model_fields
TARGET_FIELD: Final = "arch"
GROUP_FIELD: Final = "arch_group"
SOURCES_FIELD: Final = "arch_sources"
assert {TARGET_FIELD, GROUP_FIELD, SOURCES_FIELD} == set(_FIELDS), (
    "계약 ArchitectureSelector와 다름"
)

FIELD_TITLES: Final[Mapping[str, str]] = {
    TARGET_FIELD: "구조도 대상",
    GROUP_FIELD: "구조도 묶음",
    SOURCES_FIELD: "구조도 출처",
}
"""필터 표시 이름(``GET /logs/schema`` filters의 ``title``)."""


def selector_fields() -> list[LogFilterFieldInfo]:
    """필터 이름·설명(계약 ``ArchitectureSelector`` 필드에서)."""
    return [
        LogFilterFieldInfo(
            id=name,
            title=FIELD_TITLES.get(name, name),
            description=info.description,
            multi=name == SOURCES_FIELD,
        )
        for name, info in _FIELDS.items()
    ]


def selector_from_values(values: Mapping[str, tuple[str, ...]]) -> ArchitectureSelector:
    """필터 값 → ``ArchitectureSelector``.

    ``arch``는 값 하나, ``arch_group``은 값 하나(쉼표가 든 묶음 값은 쉼표로 다시 잇는다,
    빈 값 = 이름
    없는 묶음), ``arch_sources``는 여러 값.

    Raises:
        ValueError: ``arch``가 없거나 둘 이상(422로 바뀐다).
    """
    target = values.get(TARGET_FIELD, ())
    if len(target) != 1:
        raise ValueError(
            f"{TARGET_FIELD}: 값 하나가 필요합니다"
            if target
            else f"{GROUP_FIELD}·{SOURCES_FIELD}는 {TARGET_FIELD}와 함께 씁니다"
        )
    group = values.get(GROUP_FIELD)
    sources = values.get(SOURCES_FIELD)
    return ArchitectureSelector(
        arch=target[0],
        arch_group=",".join(group) if group is not None else None,
        arch_sources=list(sources) if sources is not None else None,
    )


class ArchitectureFilter:
    """필터 확장(X28): 구조도 칸·연결·묶음·분류 안 됨으로 이벤트를 거른다.

    Args:
        catalog: 프로필·연산자(``architecture.catalog``).
        cache: 범위 캐시(판정 결과 재사용). 없으면 매번 판정한다.
        on_matcher: 판정기를 만들 때 부르는 함수(측정·테스트용).
    """

    def __init__(
        self,
        catalog: ArchitectureCatalogReader,
        cache: ScopeCache | None = None,
        *,
        on_matcher: Callable[[MemoMatcher], None] | None = None,
    ) -> None:
        self._catalog = catalog
        self._cache = cache if cache is not None else ScopeCache(max_scopes=0, max_events=0)
        self._on_matcher = on_matcher
        self._fields = selector_fields()

    @property
    def fields(self) -> Sequence[LogFilterFieldInfo]:
        return self._fields

    def build(
        self, values: Mapping[str, tuple[str, ...]], context: LogFilterContext
    ) -> EventPredicate:
        """필터 값 → 이벤트 판정 함수.

        Raises:
            ValueError: 형식이 틀림, 없는(또는 끈) 프로필, 없는 칸·연결, 묶을 값이 없는 대상.
        """
        selector = selector_from_values(values)
        try:
            target = parse_arch(selector.arch)
        except ArchitectureSelectorError as exc:
            raise ValueError(str(exc)) from None
        entry = self._catalog.catalog().get(target.profile)
        if entry is None:
            raise ValueError(f"구조도 프로필 {target.profile!r}이(가) 없습니다")
        operators = self._catalog.operators()
        errors = context.query.error_categories
        matcher = MemoMatcher(
            entry.profile,
            operators,
            key=profile_key(entry.id, entry.profile, operators, errors),
            cache=self._cache,
            error_categories=errors,
        )
        if self._on_matcher is not None:
            self._on_matcher(matcher)
        try:
            return selector_predicate(
                entry.profile, selector, profile_id=entry.id, operators=operators, matcher=matcher
            )
        except ArchitectureSelectorError as exc:
            raise ValueError(str(exc)) from None


__all__ = [
    "FIELD_TITLES",
    "GROUP_FIELD",
    "SOURCES_FIELD",
    "TARGET_FIELD",
    "ArchitectureFilter",
    "selector_fields",
    "selector_from_values",
]
