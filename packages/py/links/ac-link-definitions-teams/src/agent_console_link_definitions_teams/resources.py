"""정의 저장소 하나 위의 리소스 조회(공간 안 유효 설정·묶음 미리보기, 요청 11/08 후속).

``resources.lookup`` 포트(보통 ``mod-resources``)는 라이브러리의 리소스를 읽는다. 프로젝트 공간
(``definitions.spaces``)의 팀 구성을 계산할 때는 그 공간 저장소의 리소스를 읽어야 하므로, 공간
저장소를 ``ResourceLookup``(+ 선택 능력 ``read_files``)으로 감싼다. 읽을 수 없는 정의·본문은
"없음"(None)이다(묶음 조립이 경고로 바꾼다). 다른 출처로 넘어가 찾지 않는다.

>>> from agent_console_store import DEFAULT_KINDS, InMemoryDefinitionStore
>>> store = InMemoryDefinitionStore(DEFAULT_KINDS)
>>> found = StoreResourceLookup(store)
>>> found.get_resource("ghost") is None
True
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from agent_console_contracts import Resource
from agent_console_resources import Content, ContentFiles
from agent_console_store import RESOURCE_KIND, StoreError

__all__ = ["StoreResourceLookup"]

_MISSING = (StoreError, ValidationError, LookupError, OSError)


class StoreResourceLookup:
    """정의 저장소의 리소스 종류를 읽는 ``ResourceLookup``.

    Args:
        store: 정의 저장소(``get``. 선택 ``read_content``·``list_files``·``read_file``).
        kind: 리소스 정의 종류 이름(기본 = ``agent_console_store`` 기본 종류).
    """

    def __init__(self, store: Any, kind: str = RESOURCE_KIND.name) -> None:
        self._store = store
        self._kind = kind

    def get_resource(self, ref: str) -> Resource | None:
        """id로 정의를 찾는다. 없거나 읽을 수 없으면 None."""
        try:
            return Resource.model_validate(self._store.get(self._kind, ref).document)
        except _MISSING:
            return None

    def read_content(self, resource: Resource) -> Content:
        """정의의 본문. 저장소가 본문을 모르거나 읽지 못하면 None."""
        reader = getattr(self._store, "read_content", None)
        if reader is None:
            return None
        try:
            found: Content = reader(self._kind, resource.id)
        except _MISSING:
            return None
        return found

    def read_files(self, resource: Resource) -> ContentFiles | None:
        """여러 파일 본문(``{경로: 바이트}``). 저장소가 모르거나 읽지 못하면 None."""
        lister = getattr(self._store, "list_files", None)
        reader = getattr(self._store, "read_file", None)
        if lister is None or reader is None:
            return None
        try:
            return {
                f.path: reader(self._kind, resource.id, f.path)
                for f in lister(self._kind, resource.id)
            }
        except _MISSING:
            return None
