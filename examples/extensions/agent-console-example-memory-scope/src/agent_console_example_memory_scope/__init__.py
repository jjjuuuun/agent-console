"""agent-console-example-memory-scope: 예제 메모리 계산 범위 종류 플러그인(X29).

엔진·서버에는 entry point(``agent_console.memory_scope_kinds``)로만 등록된다. 공개 계약
(``agent_console_contracts``)과 메모리 라이브러리(``agent_console_memory``)만 사용한다.

공개 API:
    - entry point 대상: ``scope_kinds()`` → ``[MemoryScopeKind]``
    - 만들기: ``iso_week_scope_kind(clock)``, ``iso_week_id(date)``
    - 상수: ``KIND_ID``
"""

from agent_console_example_memory_scope.scope_kinds import (
    KIND_ID,
    Clock,
    iso_week_id,
    iso_week_scope_kind,
    scope_kinds,
    utc_now,
)

__all__ = ["KIND_ID", "Clock", "iso_week_id", "iso_week_scope_kind", "scope_kinds", "utc_now"]
