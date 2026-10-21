"""타입드 서비스 조회: 노드가 필요한 앱 제공 서비스를 runtime이 모른 채 전달한다.

runtime은 라우팅·정의 저장소 같은 구체 서비스를 모른다. 서비스를 **쓰는 쪽**(플러그인)이
`ServiceKey`를 정의해 공개하고, 앱이 같은 키로 구현을 넣어 `GraphRuntime`에 주입한다.

    AGENTS = ServiceKey[AgentLookup]("agents")          # 플러그인(ac-nodes-core)이 정의
    services = Services({AGENTS: lookup})               # 앱(apps/server)이 조립
    lookup = ctx.services.require(AGENTS)               # 노드 구현이 사용
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class ServiceKey[T]:
    """서비스 키. 같은 `name`이면 같은 키다(타입 인자는 정적 검사용)."""

    name: str

    def __repr__(self) -> str:
        return f"ServiceKey({self.name!r})"


class MissingServiceError(LookupError):
    """`Services.require`로 찾는 서비스가 주입되지 않았다."""

    def __init__(self, key: ServiceKey[Any]) -> None:
        super().__init__(f"서비스 {key.name!r}가 주입되지 않았습니다")
        self.key = key


class Services:
    """불변 서비스 묶음. `get`/`require`로 꺼내고 `with_`로 추가한 사본을 만든다."""

    __slots__ = ("_items",)

    def __init__(self, items: Mapping[ServiceKey[Any], Any] | None = None) -> None:
        self._items: dict[str, Any] = {key.name: value for key, value in (items or {}).items()}

    def get[T](self, key: ServiceKey[T], default: T | None = None) -> T | None:
        """서비스를 돌려준다. 없으면 `default`."""
        if key.name in self._items:
            return cast("T", self._items[key.name])
        return default

    def require[T](self, key: ServiceKey[T]) -> T:
        """서비스를 돌려준다. 없으면 `MissingServiceError`."""
        if key.name not in self._items:
            raise MissingServiceError(key)
        return cast("T", self._items[key.name])

    def with_[T](self, key: ServiceKey[T], value: T) -> Services:
        """`key`를 추가(또는 교체)한 새 묶음."""
        clone = Services()
        clone._items = {**self._items, key.name: value}
        return clone

    def __contains__(self, key: object) -> bool:
        return isinstance(key, ServiceKey) and key.name in self._items

    def names(self) -> Iterator[str]:
        """주입된 서비스 이름(진단용)."""
        return iter(sorted(self._items))
