"""저장 전 정의 검사(``definitions.checks``): 메모리 리소스의 모르는 범위 종류 경고.

메모리 리소스(종류 = 리소스 종류 데이터의 ``id``)의 ``config.scopes[i].kind``·``default_scope``가
지금 범위 종류 목록(``memory.service`` ``catalog()``)에 없으면 warning
``memory.unknown_scope_kind``(path = 리소스 문서 기준). 저장은 막지 않는다(에이전트가 그 범위를
부르면 ``scope_unavailable``). 형식 검사는 리소스 종류(``MemoryResourceType``)가 따로 한다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from agent_console_contracts import Issue, KnownIssueCodes
from agent_console_store import RESOURCE_KIND

from .ports import MemoryServiceLike

__all__ = ["MemoryResourceCheck"]


def _document(document: Mapping[str, Any] | BaseModel) -> Mapping[str, Any]:
    if isinstance(document, BaseModel):
        return document.model_dump(mode="json")
    return document


class MemoryResourceCheck:
    """``definitions.checks`` 하나.

    Args:
        service: 지금 메모리 서비스를 돌려주는 함수(None이면 검사하지 않는다).
        resource_type: 메모리 리소스 종류 id(리소스 종류 데이터).
        resource_kind: 정의 종류 이름(기본 ``agent_console_store.RESOURCE_KIND``).
    """

    def __init__(
        self,
        service: Callable[[], MemoryServiceLike | None],
        *,
        resource_type: str,
        resource_kind: str = RESOURCE_KIND.name,
    ) -> None:
        self._service = service
        self.resource_type = resource_type
        self.resource_kind = resource_kind

    def issues(self, kind: str, document: Mapping[str, Any] | BaseModel) -> Sequence[Issue]:
        """모르는 범위 종류마다 경고(메시지에 설정 값 외의 내용은 없다)."""
        if kind != self.resource_kind:
            return []
        doc = _document(document)
        if doc.get("type") != self.resource_type:
            return []
        config = doc.get("config")
        if not isinstance(config, Mapping):
            return []
        service = self._service()
        if service is None:
            return []
        known = set(service.catalog().ids())
        found: list[Issue] = []
        scopes = config.get("scopes")
        if isinstance(scopes, Sequence) and not isinstance(scopes, str | bytes):
            for index, item in enumerate(scopes):
                value = item.get("kind") if isinstance(item, Mapping) else None
                if isinstance(value, str) and value not in known:
                    found.append(self._issue(value, f"/config/scopes/{index}/kind"))
        default = config.get("default_scope")
        if isinstance(default, str) and default and default not in known:
            found.append(self._issue(default, "/config/default_scope"))
        return found

    @staticmethod
    def _issue(kind: str, path: str) -> Issue:
        return Issue(
            severity="warning",
            code=KnownIssueCodes.MEMORY_UNKNOWN_SCOPE_KIND,
            message=(
                f"범위 종류 {kind!r}가 메모리 설정에 없습니다. 에이전트는 이 범위를 쓸 수 없습니다"
            ),
            path=path,
            details={"kind": kind},
        )
