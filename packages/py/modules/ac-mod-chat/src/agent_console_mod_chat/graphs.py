"""팀 구성 조회 어댑터: ``definitions.lookup``(선택 포트) → ``agent_console_chat.GraphLookup``,
``definitions.spaces``(선택 포트) → ``agent_console_chat.ProjectGraphLookup``(5.7R.33y)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import ValidationError

from agent_console_contracts import Graph
from agent_console_store import GRAPH_KIND, StoreError

from .ports import DefinitionLookup, DefinitionSpaces

_log = logging.getLogger("agent_console_mod_chat")


class PortGraphLookup:
    """``get_graph(id)``: 정의 읽기 포트로 팀 구성을 찾는다. 포트가 없거나 정의가 없거나 계약에
    맞지 않으면 None.

    ``get_project_graph(project_id, id)``: ``definitions.spaces``가 있으면 그 공간에서만 찾는다
    (공간을 열 수 없거나 없으면 None — 라이브러리로 넘어가지 않는다). 포트가 없으면 ``get_graph``와
    같다.

    Args:
        lookup: 지금의 ``definitions.lookup`` 구현(없으면 None)을 돌려주는 함수(조립 뒤에 생기는
            포트도 읽을 수 있게 호출할 때마다 부른다).
        kind: 팀 구성 정의 종류 이름.
        spaces: 지금의 ``definitions.spaces`` 구현(없으면 None)을 돌려주는 함수.
    """

    def __init__(
        self,
        lookup: Callable[[], DefinitionLookup | None],
        *,
        kind: str = GRAPH_KIND.name,
        spaces: Callable[[], DefinitionSpaces | None] = lambda: None,
    ) -> None:
        self._lookup = lookup
        self._kind = kind
        self._spaces = spaces

    @property
    def available(self) -> bool:
        """정의 읽기 포트가 있는지."""
        return self._lookup() is not None

    def get_graph(self, graph_id: str) -> Graph | None:
        return self._read(self._lookup(), graph_id)

    def get_project_graph(self, project_id: str, graph_id: str) -> Graph | None:
        spaces = self._spaces()
        if spaces is None:
            return self.get_graph(graph_id)
        try:
            store = spaces.open(project_id)
        except Exception:  # 제공 모듈의 오류 타입(모르는 공간·폴더 없음)을 모른다 — "없음"
            _log.debug("정의 공간을 열 수 없음: %s", project_id, exc_info=True)
            return None
        return self._read(store, graph_id)

    def _read(self, source: DefinitionLookup | None, graph_id: str) -> Graph | None:
        if source is None:
            return None
        try:
            return Graph.model_validate(source.get(self._kind, graph_id).document)
        except (StoreError, ValidationError):
            return None


__all__ = ["PortGraphLookup"]
