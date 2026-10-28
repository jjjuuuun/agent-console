"""link-memory-runs의 포트(이름 = 포트, design §5.7R.2). 다른 모듈은 이 파일을 import하지 않고 같은
이름을 자기 ``ports``에 선언해 연결한다. 아래 프로토콜은 이 모듈이 **받는** 쪽의 모양이다(제공
모듈을 import하지 않는다).

받음:

- 필수 ``memory.service``: 메모리 서비스(``MemoryServiceLike`` — ``catalog()``·``toolkit(...)``).
  ``mod-memory``가 준다. 없으면 이 연동은 꺼진다(실행은 메모리 도구 없이, 메모리 칸은 백엔드가
  적용하지 못한 칸 경고 R13.5).

제공:

- ``runs.scopes``(여러 제공자): Run마다 노드 서비스 ``TOOL_PROVIDERS``(``ac-nodes-core``, X30)에
  메모리 도구 공급자를 더한다(``MemoryRunScope.scope_run``). 자식 Run은 부모 서비스를 물려받는다.
- ``definitions.checks``(여러 제공자): 메모리 리소스의 모르는 범위 종류 경고
  (``MemoryResourceCheck``).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agent_console_contracts.memory import (
    MemoryAccessConfig,
    MemoryAccessContext,
    MemoryAuthor,
)
from agent_console_memory import (
    EventSink,
    MemoryToolkit,
    ScopeKindCatalog,
    ToolText,
    WriteBudget,
)
from agent_console_modkit import PortKey


@runtime_checkable
class MemoryServiceLike(Protocol):
    """``memory.service`` 모양 중 이 연동이 쓰는 부분."""

    def catalog(self) -> ScopeKindCatalog:
        """지금 범위 종류 목록."""
        ...

    def toolkit(
        self,
        access: MemoryAccessConfig,
        context: MemoryAccessContext,
        *,
        on_event: EventSink | None = None,
        author: MemoryAuthor | None = None,
        write_budget: WriteBudget | None = None,
        text: ToolText | None = None,
    ) -> MemoryToolkit:
        """에이전트 도구 묶음."""
        ...


MEMORY_SERVICE: PortKey[MemoryServiceLike] = PortKey(
    "memory.service", "공유 메모리(범위 종류·도구 묶음)"
)
RUN_SCOPES: PortKey[Any] = PortKey(
    "runs.scopes", "실행 범위(Run마다 메모리 도구 공급자)", multi=True
)
DEFINITION_CHECKS: PortKey[Any] = PortKey("definitions.checks", "저장 전 정의 검사", multi=True)

__all__ = ["DEFINITION_CHECKS", "MEMORY_SERVICE", "RUN_SCOPES", "MemoryServiceLike"]
