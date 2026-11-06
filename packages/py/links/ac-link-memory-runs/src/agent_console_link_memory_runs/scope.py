"""실행 범위(``runs.scopes``, X26): Run마다 노드 서비스 ``TOOL_PROVIDERS``에 메모리 도구 공급자.

공급자는 Run 하나에 하나다. 그래서 실행당 쓰기 한도(``WriteBudget``)를 그 Run의 모든 노드·자식
Run이 함께 쓰고, 맥락의 ``project_id``·``root_graph_id``는 루트 Run 값이다. 자식 Run은 부모 서비스를
물려받아 같은 공급자를 쓴다(맥락 ``graph_id``는 자식 팀).

프로젝트 실행(``project_id``가 있음, 5.7R.33z)은 메모리 서비스의 ``space(project_id)``가 준
**그 공간 서비스만** 쓴다(라이브러리 메모리를 읽거나 쓰지 않는다). 공간 서비스가 맥락 바꾸기(예:
``project_id`` = 폴더 id)를 도구 맥락에 적용한다. 서비스에 ``space``가 없거나 공간을 열 수 없으면
(``link-projects-memory`` 꺼짐, 폴더 없음 등) 도구 모양은 그대로 주되 모든 호출이
``memory.scope_unavailable``이고, 메모리 칸이 있는 노드에 경고가 한 번 붙는다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts import Graph, Issue
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.memory import (
    MemoryAccessConfig,
    MemoryAccessContext,
    MemoryAuthor,
)
from agent_console_memory import (
    EventSink,
    InMemoryMemoryStore,
    MemoryToolkit,
    ScopeKindCatalog,
    ToolText,
    WriteBudget,
)
from agent_console_nodes_core import TOOL_PROVIDERS
from agent_console_runtime import ServiceKey, Services

from .ports import MemoryServiceLike
from .provider import DEFAULT_PROVIDER_ID, MemoryToolProvider

__all__ = ["MemoryRunScope", "RunScopeResult", "UnavailableMemoryService", "space_service"]

_log = logging.getLogger(__name__)


class UnavailableMemoryService:
    """공간 저장소를 쓸 수 없는 실행의 서비스: 같은 범위 종류·도구 모양, 모든 호출
    ``memory.scope_unavailable``(저장소는 빈 메모리 — 한 번도 닿지 않는다).

    Args:
        base: 범위 종류 목록을 빌릴 서비스.
        issue: 메모리 칸이 있는 노드에 붙일 경고.
    """

    def __init__(self, base: MemoryServiceLike, issue: Issue) -> None:
        self._catalog = base.catalog().unresolvable()
        self.issue = issue

    def catalog(self) -> ScopeKindCatalog:
        """범위를 풀지 않는 범위 종류 목록."""
        return self._catalog

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
        """모든 호출이 ``scope_unavailable``인 도구 묶음."""
        return MemoryToolkit(
            InMemoryMemoryStore(),
            access=access,
            context=context,
            catalog=self._catalog,
            author=author,
            text=text,
            on_event=on_event,
            write_budget=write_budget,
        )


def unavailable_issue(project_id: str, reason: str) -> Issue:
    """프로젝트 메모리 저장소를 쓸 수 없다는 경고(``memory.scope_unavailable``)."""
    return Issue(
        severity="warning",
        code=KnownIssueCodes.MEMORY_SCOPE_UNAVAILABLE,
        message=("이 실행의 프로젝트 메모리 저장소를 열 수 없어 메모리 도구가 동작하지 않습니다"),
        details={"project_id": project_id, "reason": reason},
    )


def space_service(base: MemoryServiceLike, project_id: str) -> MemoryServiceLike:
    """프로젝트 실행의 메모리 서비스(``base.space(project_id)``, 못 쓰면
    ``UnavailableMemoryService``). 라이브러리로 대신하지 않는다."""
    space = getattr(base, "space", None)
    if not callable(space):
        return UnavailableMemoryService(base, unavailable_issue(project_id, "no_spaces"))
    try:
        found = space(project_id)
    except Exception as exc:
        code = getattr(exc, "code", None)
        reason = code if isinstance(code, str) and code else type(exc).__name__
        _log.info("프로젝트 메모리 공간을 열지 못함: %s (%s)", project_id, reason)
        return UnavailableMemoryService(base, unavailable_issue(project_id, reason))
    if found is None:
        return UnavailableMemoryService(base, unavailable_issue(project_id, "not_found"))
    return found  # type: ignore[no-any-return]


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

    def provider_for(
        self,
        graph_id: str,
        project_id: str | None,
        service: Callable[[], MemoryServiceLike | None] | None = None,
    ) -> MemoryToolProvider:
        """Run 하나의 공급자(새 쓰기 한도). ``service``가 없으면 모듈 서비스."""
        return MemoryToolProvider(
            service if service is not None else self._service,
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
        base = self._service()
        if base is None:
            return None
        chosen: Callable[[], MemoryServiceLike | None] | None = None
        if project_id:
            found = space_service(base, project_id)
            chosen = lambda: found  # noqa: E731
        provider = self.provider_for(graph.id, project_id, chosen)
        existing = services.get(TOOL_PROVIDERS) or ()
        return RunScopeResult(services={TOOL_PROVIDERS: (*existing, provider)})
