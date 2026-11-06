# ruff: noqa: N818
"""메모리 공간 고르기: 공간 이름 → 그 공간의 ``MemoryService``(포트 ``memory.spaces``, 5.7R.33z).

이름이 없으면 기본 서비스(앱 DB 라이브러리 메모리)다. 공간 이름은 불투명 문자열이고 이 모듈은 그
이름이 무엇(프로젝트 등)인지 모른다. 이름 → 저장소는 포트 제공자가 정한다. 정의 공간(``ac-store``
``SpaceStores``, 33x)과 같은 규칙이다.

- 제공자가 없는데 이름이 왔다 → ``MemorySpacesUnavailable``(409 ``feature_unavailable``). 질의를
  무시하고 라이브러리에 쓰지 않는다.
- 제공자가 모르는 이름(``LookupError``) → ``UnknownMemorySpace``(404 ``project.not_found``).
- 제공자의 다른 예외에 ``code`` 속성이 있으면 ``MemorySpaceError``(그 코드, 예: 폴더 없음 409).

공간마다 서비스 하나를 캐시한다(같은 저장소 객체가 오는 동안). 범위 종류·사용자 설정·한도·비밀
규칙은 모든 공간이 같다(앱 설정 하나).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from agent_console_contracts import ErrorCodes
from agent_console_memory import MemoryStore

from .ports import MemorySpaces

if TYPE_CHECKING:
    from .service import MemoryService


class MemorySpaceError(Exception):
    """공간을 열 수 없다(코드 = 계약 오류 코드, 응답 상태는 호스트 표).

    Attributes:
        code: 오류 코드.
        space: 요청한 공간 이름.
    """

    code: str = ErrorCodes.FEATURE_UNAVAILABLE

    def __init__(self, message: str, *, space: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.space = space
        if code is not None:
            self.code = code


class MemorySpacesUnavailable(MemorySpaceError):
    """공간 이름이 왔는데 ``memory.spaces`` 제공자가 없다 → ``feature_unavailable``(409)."""

    def __init__(self, space: str) -> None:
        super().__init__(
            "프로젝트 메모리를 쓸 수 없습니다(메모리 공간 제공자 없음)",
            space=space,
            code=ErrorCodes.FEATURE_UNAVAILABLE,
        )


class UnknownMemorySpace(MemorySpaceError):
    """제공자가 모르는 공간 → ``project.not_found``(404)."""

    def __init__(self, space: str) -> None:
        super().__init__("그 프로젝트가 없습니다", space=space, code=ErrorCodes.PROJECT_NOT_FOUND)


type ServiceFactory = Callable[[MemoryStore, Mapping[str, str]], "MemoryService"]
"""공간 저장소 + 맥락 바꾸기 → 그 공간의 서비스(모듈이 라이브러리와 같은 설정으로 만든다)."""


class MemorySpaceServices:
    """공간 이름 → ``MemoryService``.

    Args:
        provider: 지금 ``memory.spaces`` 제공자(부를 때마다 — 늦게 켜진 제공자도 보인다). 없으면
            None.
        make: 공간 저장소로 서비스를 만드는 함수.
        library: 이름 없는 요청의 서비스(라이브러리). 만든 뒤 붙여도 된다.
    """

    def __init__(
        self,
        provider: Callable[[], MemorySpaces | None],
        make: ServiceFactory,
        *,
        library: MemoryService | None = None,
    ) -> None:
        self.library = library
        self._provider = provider
        self._make = make
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[MemoryStore, MemoryService]] = {}

    @property
    def available(self) -> bool:
        """지금 공간 제공자가 있나."""
        return self._provider() is not None

    def get(self, space: str) -> MemoryService:
        """공간 이름(비지 않음) → 서비스.

        Raises:
            MemorySpacesUnavailable: 제공자가 없다.
            UnknownMemorySpace: 제공자가 모르는 이름.
            MemorySpaceError: 제공자가 그 공간을 열 수 없다(``code`` 있는 예외).
        """
        provider = self._provider()
        if provider is None:
            raise MemorySpacesUnavailable(space)
        try:
            opened: Any = provider.open(space)
        except MemorySpaceError:
            raise
        except LookupError as exc:
            raise UnknownMemorySpace(space) from exc
        except Exception as exc:
            code = getattr(exc, "code", None)
            if isinstance(code, str) and code:
                raise MemorySpaceError(str(exc) or code, space=space, code=code) from exc
            raise
        if opened is None:
            raise UnknownMemorySpace(space)
        store: MemoryStore = opened.store
        context = {str(k): str(v) for k, v in dict(getattr(opened, "context", None) or {}).items()}
        with self._lock:
            cached = self._cache.get(space)
            if cached is not None and cached[0] is store:
                service = cached[1]
                service.context_overrides = context
                return service
            service = self._make(store, context)
            service.space_name = space
            self._cache[space] = (store, service)
            return service

    def forget(self, space: str) -> None:
        """캐시에서 뺀다(다음 ``get``이 새 서비스를 만든다)."""
        with self._lock:
            self._cache.pop(space, None)


__all__ = [
    "MemorySpaceError",
    "MemorySpaceServices",
    "MemorySpacesUnavailable",
    "ServiceFactory",
    "UnknownMemorySpace",
]
