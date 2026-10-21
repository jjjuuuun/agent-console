"""`ac-resources.ResourceLookup`을 함수 두 개로 만족하는 얇은 어댑터(앱 조립용).

이 패키지는 저장소(`ac-store`)를 모른다. 앱이 저장소 메서드를 함수로 넘긴다::

    from agent_console_nodes_core import RESOURCE_LOOKUP, FunctionResources

    def find(ref):
        try:
            return store.get("resource", ref).model(Resource)
        except NotFound:
            return None

    def read(resource):
        return store.read_content("resource", resource.id)

    def read_files(resource):  # 선택: 여러 파일 본문 종류(skill 등)
        return {f.path: store.read_file("resource", resource.id, f.path)
                for f in store.list_files("resource", resource.id)}

    services = Services({RESOURCE_LOOKUP: FunctionResources(find, read, read_files)})
"""

from __future__ import annotations

from collections.abc import Callable

from agent_console_contracts import Resource
from agent_console_resources import Content, ContentFiles

__all__ = ["FunctionResources"]


class FunctionResources:
    """`get_resource(ref)`·`read_content(resource)`·`read_files(resource)`를 주입한 함수로 처리한다
    (`ac-resources.ResourceLookup` + 선택 능력 `FileContentLookup`).

    Args:
        find: id → 정의(없으면 None. `LookupError`도 "없음"으로 본다).
        read: 정의 → 본문(`str | bytes | None`). 예외는 "본문 없음"(None)으로 본다.
        read_files: 선택. 정의 → 여러 파일 본문(`{경로: 바이트}`). 없으면 여러 파일 종류의 본문은
            None. 예외는 None으로 본다.
    """

    def __init__(
        self,
        find: Callable[[str], Resource | None],
        read: Callable[[Resource], Content],
        read_files: Callable[[Resource], ContentFiles | None] | None = None,
    ) -> None:
        self._find = find
        self._read = read
        self._read_files = read_files

    def get_resource(self, ref: str) -> Resource | None:
        """id로 정의를 찾는다. 없으면 None."""
        try:
            return self._find(ref)
        except LookupError:
            return None

    def read_content(self, resource: Resource) -> Content:
        """정의의 본문. 읽지 못하면 None."""
        try:
            return self._read(resource)
        except Exception:
            return None

    def read_files(self, resource: Resource) -> ContentFiles | None:
        """여러 파일 본문. 함수가 없거나 읽지 못하면 None."""
        if self._read_files is None:
            return None
        try:
            return self._read_files(resource)
        except Exception:
            return None
