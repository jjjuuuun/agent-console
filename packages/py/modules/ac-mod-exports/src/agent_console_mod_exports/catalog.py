"""``ExportCatalog`` 어댑터: 정의 읽기(``definitions.lookup``) + 의존(``exports.dependencies``)."""

from __future__ import annotations

import copy
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from agent_console_exports import DependencyLike
from agent_console_store import StoreError

from .ports import DefinitionLookup, ExportDependencies

_log = logging.getLogger("agent_console_mod_exports")

_MISSING = (StoreError, KeyError, ValueError)
"""읽을 수 없는 정의(없음·잘못된 id·손상)로 보는 예외."""


class LookupExportCatalog:
    """정의 읽기 포트로 만든 카탈로그(읽기만 한다).

    Args:
        lookup: 정의 읽기.
        dependencies: 의존 계산. 없으면 의존 없음(고른 항목만).
    """

    def __init__(
        self, lookup: DefinitionLookup, dependencies: ExportDependencies | None = None
    ) -> None:
        self._lookup = lookup
        self._dependencies = dependencies

    def document(self, kind: str, id: str) -> Mapping[str, Any] | None:
        try:
            return copy.deepcopy(dict(self._lookup.get(kind, id).document))
        except _MISSING:
            return None

    def files(self, kind: str, id: str) -> Mapping[str, bytes]:
        lookup = self._lookup
        try:
            return {f.path: lookup.read_file(kind, id, f.path) for f in lookup.list_files(kind, id)}
        except _MISSING:
            return {}

    def dependencies(self, kind: str, id: str) -> Sequence[DependencyLike]:
        if self._dependencies is None:
            return []
        try:
            return self._dependencies.dependencies(kind, id)
        except Exception as exc:  # 해석할 수 없는 정의: 함께 내보낼 것이 없다(경고 로그)
            _log.warning(
                "내보내기: %s/%s의 쓰는 정의를 찾지 못했습니다(%s)", kind, id, type(exc).__name__
            )
            return []


__all__ = ["LookupExportCatalog"]
