"""실행 범위(``runs.scopes``, X26): Run마다 노드 서비스 ``TOOL_PROVIDERS``에 메모리 도구 공급자.

공급자는 Run 하나에 하나다. 그래서 실행당 쓰기 한도(``WriteBudget``)를 그 Run의 모든 노드·자식
Run이 함께 쓰고, 맥락의 ``project_id``·``root_graph_id``는 루트 Run 값이다. 자식 Run은 부모 서비스를
물려받아 같은 공급자를 쓴다(맥락 ``graph_id``는 자식 팀).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts import Graph, Issue
from agent_console_memory import ToolText, WriteBudget
from agent_console_nodes_core import TOOL_PROVIDERS
from agent_console_runtime import ServiceKey, Services

from .ports import MemoryServiceLike
from .provider import DEFAULT_PROVIDER_ID, MemoryToolProvider

__all__ = ["MemoryRunScope", "RunScopeResult"]


@dataclass(frozen=True)
class RunScopeResult:
    """``runs.scopes`` 결과 모양(``mod-runs`` ``RunScope``와 같은 속성)."""

    services: Mapping[ServiceKey[Any], Any] = field(default_factory=dict)
    warnings: Sequence[Issue] = ()


class MemoryRunScope:
    """``runs.scopes`` 항목: Run마다 메모리 도구 공급자 하나.

    Args:
        service: 지금 메모리 서비스(``memory.service``)를 돌려주는 함수. None이면 범위를 더하지
            않는다(메모리 칸은 소비되지 않아 R13.5 경고가 난다).
        slot: 메모리 묶음 칸 이름(리소스 종류 데이터).
        max_writes_per_run: 실행 하나의 쓰기 한도(None = 없음).
        text: 도구 문구(없으면 ``ac-memory`` 기본 데이터).
        provider_id: 공급자 id.
    """

    def __init__(
        self,
        service: Callable[[], MemoryServiceLike | None],
        *,
        slot: str,
        max_writes_per_run: int | None = None,
        text: ToolText | None = None,
        provider_id: str = DEFAULT_PROVIDER_ID,
    ) -> None:
        self._service = service
        self.slot = slot
        self.max_writes_per_run = max_writes_per_run
        self.text = text
        self.provider_id = provider_id

    def provider_for(self, graph_id: str, project_id: str | None) -> MemoryToolProvider:
        """Run 하나의 공급자(새 쓰기 한도)."""
        return MemoryToolProvider(
            self._service,
            slot=self.slot,
            id=self.provider_id,
            project_id=project_id,
            root_graph_id=graph_id,
            write_budget=WriteBudget(self.max_writes_per_run),
            text=self.text,
        )

    def scope_run(
        self, graph: Graph, services: Services, *, project_id: str | None
    ) -> RunScopeResult | None:
        """``runs.scopes``: 이 Run의 ``TOOL_PROVIDERS``에 공급자를 붙인다(이미 있는 공급자 뒤).

        메모리 서비스가 없으면 None.
        """
        if self._service() is None:
            return None
        provider = self.provider_for(graph.id, project_id)
        existing = services.get(TOOL_PROVIDERS) or ()
        return RunScopeResult(services={TOOL_PROVIDERS: (*existing, provider)})
