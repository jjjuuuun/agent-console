# ruff: noqa: N818
"""정의 저장소 공간 고르기: 공간 이름 → `DefinitionStore`(포트 `definitions.spaces`, design §PI.10).

정의를 다루는 모듈(정의·리소스·버전)은 요청의 공간 이름(REST `?project=<id>`)으로 저장소를 고른다.
이름이 없으면 기본 저장소(앱 workspace 라이브러리)다. 공간 이름은 **불투명 문자열**이다 — 이 모듈과
소비 모듈은 그 이름이 무엇을 가리키는지(프로젝트 등) 모른다. 이름 → 저장소는 포트 제공자가 정한다.

- 포트가 없는데 이름이 왔다 → `SpacesUnavailable`(`feature_unavailable`, 409). 질의를 조용히
  무시하고 라이브러리에 쓰지 않는다.
- 제공자가 모르는 이름(`LookupError`) → `UnknownSpace`(`project.not_found`, 404).
- 제공자의 다른 저장소 예외(`StoreError` — 폴더 없음 등)는 그대로 올린다.

>>> from agent_console_store import InMemoryDefinitionStore
>>> library = InMemoryDefinitionStore()
>>> stores = SpaceStores(library, lambda: None)
>>> stores.get(None) is library
True
>>> stores.get("a")
Traceback (most recent call last):
...
agent_console_store.spaces.SpacesUnavailable: definition spaces are not available (no provider)
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, runtime_checkable

from agent_console_contracts import ErrorCodes

from .errors import StoreError
from .interfaces import DefinitionStore

DEFINITIONS_SPACES_PORT = "definitions.spaces"
"""포트 이름: 공간 이름 → 정의 저장소(`DefinitionSpaces`). 소비 모듈은 이 이름으로 `PortKey`를
자기 ``ports.py``에 선언한다."""


@runtime_checkable
class DefinitionSpaces(Protocol):
    """`definitions.spaces` 포트 모양: 공간 이름 → 그 공간의 정의 저장소.

    제공자가 공간 캐시·버전 기록소(그 공간의 기록 DB 등)·쓰기 검사를 맡는다.
    """

    def open(self, space: str) -> DefinitionStore:
        """그 공간의 정의 저장소.

        Raises:
            LookupError: 모르는 공간.
            StoreError: 그 밖에 열 수 없다(폴더 없음 등, 코드는 예외의 `code`).
        """
        ...


class MappedSpaces:
    """`DefinitionSpaces` 예제 구현: 이름 → 저장소 표(단독 실행·테스트·다른 앱에서 그대로 쓴다).

    >>> from agent_console_store import InMemoryDefinitionStore
    >>> a = InMemoryDefinitionStore()
    >>> MappedSpaces({"a": a}).open("a") is a
    True

    Args:
        stores: 공간 이름 → 저장소. 없는 이름은 `KeyError`(`LookupError` → 404).
    """

    def __init__(self, stores: Mapping[str, DefinitionStore]) -> None:
        self.stores = dict(stores)

    def open(self, space: str) -> DefinitionStore:
        return self.stores[space]


class UnknownSpace(StoreError):
    """요청한 공간을 제공자가 모른다 -> `project.not_found`(404).

    Attributes:
        space: 요청한 공간 이름.
    """

    code = ErrorCodes.PROJECT_NOT_FOUND

    def __init__(self, space: str) -> None:
        super().__init__(f"unknown space: {space}")
        self.space = space


class SpacesUnavailable(StoreError):
    """공간 이름이 왔는데 `definitions.spaces` 제공자가 없다 -> `feature_unavailable`(409)."""

    code = ErrorCodes.FEATURE_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__("definition spaces are not available (no provider)")


class SpaceStores[S: DefinitionStore]:
    """요청의 공간 이름으로 정의 저장소를 고른다.

    Args:
        default: 공간 이름이 없을 때의 저장소(라이브러리).
        spaces: 지금 `definitions.spaces` 제공자(부를 때마다 — 늦게 켜진 제공자도 보인다).
            없으면 None.
        cast: 제공자 저장소 → `S`(소비 모듈이 더 좁은 모양을 쓸 때 확인·변환). 기본은 그대로.
    """

    def __init__(
        self,
        default: S,
        spaces: Callable[[], DefinitionSpaces | None],
        *,
        cast: Callable[[DefinitionStore], S] | None = None,
    ) -> None:
        self.default = default
        self._spaces = spaces
        self._cast = cast

    @property
    def available(self) -> bool:
        """지금 공간 제공자가 있나."""
        return self._spaces() is not None

    def get(self, space: str | None) -> S:
        """공간 이름(None·빈 문자열 = 기본) → 저장소.

        Raises:
            SpacesUnavailable: 이름이 왔는데 제공자가 없다.
            UnknownSpace: 제공자가 모르는 이름.
            StoreError: 제공자가 그 공간을 열 수 없다.
        """
        if not space:
            return self.default
        provider = self._spaces()
        if provider is None:
            raise SpacesUnavailable()
        try:
            store: DefinitionStore | None = provider.open(space)
        except StoreError:
            raise
        except LookupError as exc:
            raise UnknownSpace(space) from exc
        if store is None:
            raise UnknownSpace(space)
        if self._cast is not None:
            return self._cast(store)
        return store  # type: ignore[return-value]  # cast가 없으면 S = DefinitionStore


__all__ = [
    "DEFINITIONS_SPACES_PORT",
    "DefinitionSpaces",
    "MappedSpaces",
    "SpaceStores",
    "SpacesUnavailable",
    "UnknownSpace",
]
