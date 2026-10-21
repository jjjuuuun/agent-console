"""레지스트리 묶음 `Registries`와 확장 지점 로딩(design §3.1)."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint
from types import ModuleType
from typing import Any

from agent_console_registry import LoadReport, Registry, Validator, load_entry_points, load_plugins

from ._delegation import (
    DELEGATION_STRATEGIES_EXTENSION,
    DELEGATION_STRATEGIES_GROUP,
    DelegationStrategy,
)
from ._interactions import (
    INTERACTION_KINDS_EXTENSION,
    INTERACTION_KINDS_GROUP,
    InteractionKind,
    as_interaction_kind,
)
from ._interfaces import EdgeType, ExecutionBackend, NodeType, SecretProvider

NODE_TYPES_GROUP = "agent_console.node_types"
"""X1 entry point 그룹."""
EDGE_TYPES_GROUP = "agent_console.edge_types"
"""X2 entry point 그룹."""
BACKENDS_GROUP = "agent_console.backends"
"""X3 entry point 그룹."""
SECRET_PROVIDERS_GROUP = "agent_console.secret_providers"
"""X10 entry point 그룹."""


@dataclass
class Registries:
    """앱이 시작 시 만들어 주입하는 레지스트리 묶음. 전역 싱글턴이 아니다.

    `load_plugins(paths, registries)`의 target으로 넘기면 플러그인이 `register(registries)`에서
    원하는 레지스트리에 등록한다(`load_registry_plugins`). runtime이 모르는 확장 지점(예: 라우팅
    분류기)은 `extension(name, validator=)`으로 이름 붙은 추가 레지스트리를 만들어 쓴다.

    기본 레지스트리(노드·엣지·백엔드·비밀 공급자·위임 방식·상호작용 종류)에는 검사기
    (`as_node_type` 등)가 붙어 있어, 어느 경로로 등록해도 같은 검사를 거친다(H4/D12).
    """

    node_types: Registry[NodeType] = field(
        default_factory=lambda: Registry("node_types", validator=as_node_type)
    )
    edge_types: Registry[EdgeType] = field(
        default_factory=lambda: Registry("edge_types", validator=as_edge_type)
    )
    backends: Registry[ExecutionBackend] = field(
        default_factory=lambda: Registry("backends", validator=as_backend)
    )
    secret_providers: Registry[SecretProvider] = field(
        default_factory=lambda: Registry("secret_providers", validator=as_secret_provider)
    )
    extensions: dict[str, Registry[Any]] = field(default_factory=dict)

    def extension(self, name: str, *, validator: Validator[Any] | None = None) -> Registry[Any]:
        """이름 붙은 추가 레지스트리(없으면 만든다). 예: `extension("my_classifiers")`.

        Args:
            name: 확장 지점 이름.
            validator: 선택. 등록 검사기. 레지스트리를 만들 때 붙이고, 이미 있으면 붙인다
                (이미 등록된 항목도 검사). 이후 모든 등록(entry point·모듈·`register(registries)`
                플러그인)이 이 검사를 거친다.

        Raises:
            agent_console_registry.RegistryError: 다른 검사기가 이미 붙어 있을 때.
            agent_console_registry.InvalidExtensionError: 이미 등록된 항목이 검사를 통과하지
                못할 때.
        """
        registry = self.extensions.get(name)
        if registry is None:
            registry = self.extensions[name] = Registry(name, validator=validator)
        elif validator is not None:
            registry.set_validator(validator)
        return registry

    def all(self) -> list[Registry[Any]]:
        """묶음의 모든 레지스트리(기본 4개 + 이름 붙은 확장). `load_plugins(watch=)`에 쓴다."""
        return [
            self.node_types,
            self.edge_types,
            self.backends,
            self.secret_providers,
            *self.extensions.values(),
        ]

    @property
    def delegation_strategies(self) -> Registry[DelegationStrategy]:
        """X12 위임 방식 레지스트리(= `extension(DELEGATION_STRATEGIES_EXTENSION)`)."""
        return self.extension(DELEGATION_STRATEGIES_EXTENSION, validator=as_delegation_strategy)

    @property
    def interaction_kinds(self) -> Registry[InteractionKind]:
        """X15 상호작용 종류 레지스트리(= `extension(INTERACTION_KINDS_EXTENSION)`)."""
        return self.extension(INTERACTION_KINDS_EXTENSION, validator=as_interaction_kind)


def _instantiate(obj: Any) -> Any:
    return obj() if isinstance(obj, type) else obj


def _checker[T](protocol: type[T], label: str) -> Callable[[Any], T]:
    def check(obj: Any) -> T:
        item = _instantiate(obj)
        if not isinstance(item, protocol) or not hasattr(item, "descriptor"):
            raise TypeError(f"{label}가 아니다: {obj!r}")
        return item

    check.__name__ = f"as_{label}"
    return check


as_node_type: Callable[[Any], NodeType] = _checker(NodeType, "node_type")  # type: ignore[type-abstract]
"""로드한 객체를 NodeType으로 검사(클래스면 인자 없이 인스턴스화). `load_*`의 validate."""
as_edge_type: Callable[[Any], EdgeType] = _checker(EdgeType, "edge_type")  # type: ignore[type-abstract]
"""로드한 객체를 EdgeType으로 검사."""
as_backend: Callable[[Any], ExecutionBackend] = _checker(ExecutionBackend, "backend")  # type: ignore[type-abstract]
"""로드한 객체를 ExecutionBackend로 검사."""
as_delegation_strategy: Callable[[Any], DelegationStrategy] = _checker(
    DelegationStrategy,  # type: ignore[type-abstract]
    "delegation_strategy",
)
"""로드한 객체를 DelegationStrategy(X12)로 검사."""


def as_secret_provider(obj: Any) -> SecretProvider:
    """로드한 객체를 SecretProvider로 검사."""
    item = _instantiate(obj)
    if not isinstance(item, SecretProvider):
        raise TypeError(f"secret_provider가 아니다: {obj!r}")
    return item


def descriptor_version(item: Any) -> int:
    """`item.descriptor.version`(없으면 1). `load_*`의 version_of."""
    return int(getattr(getattr(item, "descriptor", None), "version", 1) or 1)


def load_registries(
    registries: Registries,
    *,
    enabled: set[str] | None = None,
    entry_points: Iterable[EntryPoint] | None = None,
) -> list[LoadReport]:
    """X1·X2·X3·X12·X15 entry point 그룹을 `registries`에 로드한다(실패는 보고서로).

    Args:
        enabled: 주어지면 이 이름의 entry point만 로드(그룹 공통).
        entry_points: 테스트용 주입. 주면 그룹이 맞는 것만 각 레지스트리에 쓴다.

    비밀 공급자(X10)는 순서와 생성 인자(환경 등)를 앱이 정하므로 여기서 로드하지 않는다.
    """
    eps = list(entry_points) if entry_points is not None else None

    def pick(group: str) -> list[EntryPoint] | None:
        return None if eps is None else [ep for ep in eps if ep.group == group]

    reports: list[LoadReport] = []
    reports += load_entry_points(
        NODE_TYPES_GROUP,
        registries.node_types,
        enabled=enabled,
        validate=as_node_type,
        version_of=descriptor_version,
        entry_points=pick(NODE_TYPES_GROUP),
    )
    reports += load_entry_points(
        EDGE_TYPES_GROUP,
        registries.edge_types,
        enabled=enabled,
        validate=as_edge_type,
        version_of=descriptor_version,
        entry_points=pick(EDGE_TYPES_GROUP),
    )
    reports += load_entry_points(
        BACKENDS_GROUP,
        registries.backends,
        enabled=enabled,
        validate=as_backend,
        entry_points=pick(BACKENDS_GROUP),
    )
    reports += load_entry_points(
        DELEGATION_STRATEGIES_GROUP,
        registries.delegation_strategies,
        enabled=enabled,
        validate=as_delegation_strategy,
        entry_points=pick(DELEGATION_STRATEGIES_GROUP),
    )
    reports += load_entry_points(
        INTERACTION_KINDS_GROUP,
        registries.interaction_kinds,
        enabled=enabled,
        validate=as_interaction_kind,
        version_of=descriptor_version,
        entry_points=pick(INTERACTION_KINDS_GROUP),
    )
    return reports


def load_registry_plugins(
    paths: Iterable[str],
    registries: Registries,
    *,
    enabled: set[str] | None = None,
    import_module: Callable[[str], ModuleType] = importlib.import_module,
) -> list[LoadReport]:
    """`register(registries)` 플러그인(설정 `plugins.modules`)을 로드한다.

    entry point 경로와 같은 규칙을 따른다: 등록은 각 레지스트리의 검사기를 거치고(거부 →
    `failed`), `enabled`가 주어지면 플러그인이 등록한 key 중 집합에 없는 것은 해제해
    `disabled`로 보고한다.
    """
    return load_plugins(
        paths, registries, enabled=enabled, watch=registries.all, import_module=import_module
    )
