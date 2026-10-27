"""테스트 도구: 가짜 시계, 표본 쓴 주체·맥락·범위 종류, 저장소 계약 테스트 묶음.

- ``FakeClock``: 손으로 움직이는 시계(저장소 `clock=`에 넣는다).
- ``user_author``·``agent_author_sample``·``sample_context``: 표본 값.
- ``sample_scope_kinds(names)``: 이름을 고를 수 있는 범위 종류 셋(R0 시험).
- ``sample_plugin_scope_kinds``: X29 플러그인 모양 표본(가짜 entry point 대상).
- 하위 모듈 ``contract``의 ``MemoryStoreContractTests``: 저장소 구현(X31)이 지켜야 할 의미.
  상속해 ``make_store``를 채운다(pytest가 필요해 따로 import한다).
"""

from ._samples import (
    FakeClock,
    agent_author_sample,
    sample_context,
    sample_plugin_scope_kinds,
    sample_scope_kinds,
    user_author,
)

__all__ = [
    "FakeClock",
    "agent_author_sample",
    "sample_context",
    "sample_plugin_scope_kinds",
    "sample_scope_kinds",
    "user_author",
]
