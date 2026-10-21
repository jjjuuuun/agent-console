"""agent-console-registry: 타입드 레지스트리와 플러그인(entry point·모듈 목록) 로딩.

공개 API:
    - ``Registry[T](name, *, validator=None)`` / ``RegistryEntry[T]``: key(+version) → 구현.
      생성해서 주입한다(전역 없음). 검사기(``Validator``)를 붙이면 모든 등록이 검사를 거친다.
    - ``load_entry_points(group, registry, ...)``: entry point 그룹에서 로드·등록.
    - ``load_modules(paths, registry, ...)``: ``"[key=]pkg.mod:attr"`` 명시 경로에서 로드·등록.
    - ``load_plugins(paths, target, *, enabled=None, watch=None)``: ``register(target)`` 플러그인
      호출. ``enabled`` 에 없는 key로 등록된 항목은 해제하고 ``disabled`` 로 보고.
    - ``LoadReport``: 로딩 결과(실패는 예외 대신 여기에 담긴다).
    - 예외: ``RegistryError``, ``DuplicateKeyError``, ``InvalidExtensionError``,
      ``UnknownExtensionError``.
"""

from agent_console_registry._loading import (
    LoadReport,
    LoadStatus,
    load_entry_points,
    load_modules,
    load_plugins,
)
from agent_console_registry._registry import (
    DuplicateKeyError,
    InvalidExtensionError,
    Registry,
    RegistryEntry,
    RegistryError,
    UnknownExtensionError,
    Validator,
)

__all__ = [
    "DuplicateKeyError",
    "InvalidExtensionError",
    "LoadReport",
    "LoadStatus",
    "Registry",
    "RegistryEntry",
    "RegistryError",
    "UnknownExtensionError",
    "Validator",
    "load_entry_points",
    "load_modules",
    "load_plugins",
]
