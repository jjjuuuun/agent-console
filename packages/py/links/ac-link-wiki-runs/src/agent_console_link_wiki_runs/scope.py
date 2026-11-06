"""실행 범위(``runs.scopes``, X26): Run마다 노드 서비스 ``TOOL_PROVIDERS``에 위키 도구 공급자.

공급자는 루트 Run 하나에 하나다. 그래서 실행당 쓰기 한도(``WriteBudget``)를 그 Run의 모든 노드·자식
Run이 함께 쓰고, 위키 공간은 루트 Run의 ``project_id``다(자식 Run은 부모 서비스를 물려받아 같은
공급자를 쓴다). 쓴 주체 이름(``label``)은 그 Run의 노드 서비스 ``AGENT_LOOKUP``으로 읽는다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts import Graph, Issue
from agent_console_nodes_core import AGENT_LOOKUP, TOOL_PROVIDERS
from agent_console_runtime import ServiceKey, Services
from agent_console_wiki import WikiToolText, WriteBudget

from .ports import WikiServiceLike
from .provider import DEFAULT_PROVIDER_ID, AgentLookup, WikiToolProvider

__all__ = ["RunScopeResult", "WikiRunScope"]


@dataclass(frozen=True)
class RunScopeResult:
    """``runs.scopes`` 결과 모양(``mod-runs`` ``RunScope``와 같은 속성)."""

    services: Mapping[ServiceKey[Any], Any] = field(default_factory=dict)
    warnings: Sequence[Issue] = ()


class WikiRunScope:
    """``runs.scopes`` 항목: Run마다 위키 도구 공급자 하나.

    Args:
        service: 지금 위키 서비스(``wiki.service``)를 돌려주는 함수. None이면 범위를 더하지
            않는다(위키 칸은 소비되지 않아 R13.5 경고가 난다).
        slot: 위키 묶음 칸 이름(리소스 종류 데이터).
        max_writes_per_run: 실행 하나의 쓰기 한도(쓰기·옮기기·지우기, None = 없음).
        text: 도구 문구(없으면 ``ac-wiki`` 기본 데이터).
        provider_id: 공급자 id.
    """

    def __init__(
        self,
        service: Callable[[], WikiServiceLike | None],
        *,
        slot: str,
        max_writes_per_run: int | None = None,
        text: WikiToolText | None = None,
        provider_id: str = DEFAULT_PROVIDER_ID,
    ) -> None:
        self._service = service
        self.slot = slot
        self.max_writes_per_run = max_writes_per_run
        self.text = text
        self.provider_id = provider_id

    def provider_for(
        self, project_id: str | None, agent_lookup: AgentLookup | None = None
    ) -> WikiToolProvider:
        """Run 하나의 공급자(새 쓰기 한도)."""
        return WikiToolProvider(
            self._service,
            slot=self.slot,
            id=self.provider_id,
            project_id=project_id,
            agent_lookup=agent_lookup,
            write_budget=WriteBudget(self.max_writes_per_run),
            text=self.text,
        )

    def scope_run(
        self, graph: Graph, services: Services, *, project_id: str | None
    ) -> RunScopeResult | None:
        """``runs.scopes``: 이 Run의 ``TOOL_PROVIDERS``에 공급자를 붙인다(이미 있는 공급자 뒤).

        위키 서비스가 없으면 None.
        """
        if self._service() is None:
            return None
        provider = self.provider_for(project_id, services.get(AGENT_LOOKUP))
        existing = services.get(TOOL_PROVIDERS) or ()
        return RunScopeResult(services={TOOL_PROVIDERS: (*existing, provider)})
