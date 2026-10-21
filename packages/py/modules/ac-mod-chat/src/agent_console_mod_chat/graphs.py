"""팀 구성 조회 어댑터: ``definitions.lookup``(선택 포트) → ``agent_console_chat.GraphLookup``."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import ValidationError

from agent_console_contracts import Graph
from agent_console_store import GRAPH_KIND, StoreError

from .ports import DefinitionLookup


class PortGraphLookup:
    """``get_graph(id)``: 정의 읽기 포트로 팀 구성을 찾는다. 포트가 없거나 정의가 없거나 계약에
    맞지 않으면 None.

    Args:
        lookup: 지금의 ``definitions.lookup`` 구현(없으면 None)을 돌려주는 함수(조립 뒤에 생기는
            포트도 읽을 수 있게 호출할 때마다 부른다).
        kind: 팀 구성 정의 종류 이름.
    """

    def __init__(
        self, lookup: Callable[[], DefinitionLookup | None], *, kind: str = GRAPH_KIND.name
    ) -> None:
        self._lookup = lookup
        self._kind = kind

    @property
    def available(self) -> bool:
        """정의 읽기 포트가 있는지."""
        return self._lookup() is not None

    def get_graph(self, graph_id: str) -> Graph | None:
        lookup = self._lookup()
        if lookup is None:
            return None
        try:
            return Graph.model_validate(lookup.get(self._kind, graph_id).document)
        except (StoreError, ValidationError):
            return None


__all__ = ["PortGraphLookup"]
