"""테스트 도구: 가짜 시계, 표본 쓴 주체·맥락·범위 종류, 저장소 계약 테스트 묶음.

- ``FakeClock``: 손으로 움직이는 시계(저장소 `clock=`에 넣는다).
- ``user_author``·``agent_author_sample``·``sample_context``: 표본 값.
- ``sample_scope_kinds(names)``: 이름을 고를 수 있는 범위 종류 셋(R0 시험).
- ``sample_plugin_scope_kinds``: X29 플러그인 모양 표본(가짜 entry point 대상).
- ``sample_entry_summary``·``sample_entry``: 저장소 없이 만드는 항목 표본(정리 판단 대상·
  내보내기 형식).
- ``build_scale_store``·``ScaleLayout``·``WorkCounter``·``perf_strict``: SQLite 저장소 규모 측정
  도구(§5.7R.10). SQLite 저장소처럼 extra ``sqlite``(sqlalchemy)가 필요해 처음 꺼낼 때 불러온다
  (나머지 도구는 extra 없이 쓴다).
- 하위 모듈 ``contract``의 ``MemoryStoreContractTests``: 저장소 구현(X31)이 지켜야 할 의미.
  상속해 ``make_store``를 채운다(pytest가 필요해 따로 import한다).
"""

from typing import TYPE_CHECKING, Any

from ._entries import sample_entry, sample_entry_summary
from ._samples import (
    FakeClock,
    agent_author_sample,
    sample_context,
    sample_plugin_scope_kinds,
    sample_scope_kinds,
    user_author,
)

if TYPE_CHECKING:
    from ._scale import (
        ScaleLayout,
        WorkCounter,
        build_scale_store,
        percentile,
        perf_strict,
        time_calls,
    )

_SCALE_NAMES = frozenset(
    {"ScaleLayout", "WorkCounter", "build_scale_store", "percentile", "perf_strict", "time_calls"}
)


def __getattr__(name: str) -> Any:
    """규모 측정 도구는 처음 꺼낼 때 불러온다(sqlalchemy 없이도 이 모듈의 나머지를 쓰게)."""
    if name in _SCALE_NAMES:
        from . import _scale

        return getattr(_scale, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "FakeClock",
    "ScaleLayout",
    "WorkCounter",
    "agent_author_sample",
    "build_scale_store",
    "percentile",
    "perf_strict",
    "sample_context",
    "sample_entry",
    "sample_entry_summary",
    "sample_plugin_scope_kinds",
    "sample_scope_kinds",
    "time_calls",
    "user_author",
]
