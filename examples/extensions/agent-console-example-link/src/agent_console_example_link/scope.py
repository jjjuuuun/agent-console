"""실행 범위(``runs.scopes``, X26): Run마다 노드 서비스 ``TOOL_PROVIDERS``에 노트 도구
공급자를 더한다.

공급자는 루트 Run 하나에 하나다. 노트 공간은 루트 Run의 ``project_id``다(자식 Run은 부모 서비스를
물려받아 같은 공급자를 쓴다).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts import Graph, Issue
from agent_console_nodes_core import TOOL_PROVIDERS
from agent_console_runtime import ServiceKey, Services

from .ports import NotesReaderLike
from .provider import NotesToolProvider
from .settings import NotesToolText

__all__ = ["NotesRunScope", "RunScopeResult"]


@dataclass(frozen=True)
class RunScopeResult:
    """``runs.scopes`` 결과 모양(실행 모듈의 ``RunScope``와 같은 속성 — 이름으로만 맞춘다)."""

    services: Mapping[ServiceKey[Any], Any] = field(default_factory=dict)
    warnings: Sequence[Issue] = ()


class NotesRunScope:
    """``runs.scopes`` 항목.

    Args:
        reader: 지금 노트 읽기 포트를 돌려주는 함수. None을 돌려주면 범위를 더하지 않는다.
        slot: 노트 묶음 칸 이름(리소스 종류 데이터).
        text: 도구 문구.
        provider_id: 공급자 id.
        max_notes: 한 번에 줄 노트 수 상한.
    """

    def __init__(
        self,
        reader: Callable[[], NotesReaderLike | None],
        *,
        slot: str,
        text: NotesToolText,
        provider_id: str,
        max_notes: int | None = None,
    ) -> None:
        self._reader = reader
        self.slot = slot
        self.text = text
        self.provider_id = provider_id
        self.max_notes = max_notes

    def scope_run(
        self, graph: Graph, services: Services, *, project_id: str | None
    ) -> RunScopeResult | None:
        """이 Run의 ``TOOL_PROVIDERS``에 공급자를 붙인다(이미 있는 공급자 뒤).

        노트 읽기 포트가 없으면 None.
        """
        if self._reader() is None:
            return None
        provider = NotesToolProvider(
            self._reader,
            slot=self.slot,
            text=self.text,
            id=self.provider_id,
            project_id=project_id,
            max_notes=self.max_notes,
        )
        existing = services.get(TOOL_PROVIDERS) or ()
        return RunScopeResult(services={TOOL_PROVIDERS: (*existing, provider)})
