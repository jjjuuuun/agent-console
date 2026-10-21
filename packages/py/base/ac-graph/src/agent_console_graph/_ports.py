"""포트 해석: 노드 타입 디스크립터 + config → 실제 포트 목록."""

from collections.abc import Mapping
from typing import Any, Protocol

from agent_console_contracts import NodeTypeDescriptor, PortSpec


class PortResolver(Protocol):
    """동적 포트 해석기(주입). 보통 노드 타입 구현의 ``resolve_ports(config)``를 감싼다.

    ac-graph는 노드 타입 구현(ac-runtime)을 모르므로 호출자가 넘긴다. 예::

        def resolver(desc, config):
            return registry.get(desc.id, desc.version).resolve_ports(dict(config))

    예외를 던지면 검증은 ``port_resolution_failed`` 이슈로 보고한다.
    """

    def __call__(self, descriptor: NodeTypeDescriptor, config: Mapping[str, Any], /) -> PortSpec:
        """`descriptor` 타입 노드가 `config`일 때의 포트 목록을 돌려준다."""
        ...


class PortsUnavailableError(Exception):
    """동적 포트 노드인데 해석기가 주어지지 않았다."""


def node_ports(
    descriptor: NodeTypeDescriptor,
    config: Mapping[str, Any],
    resolve_ports: PortResolver | None = None,
) -> PortSpec:
    """노드의 실제 포트 목록.

    `descriptor.dynamic_ports`가 참이면 `resolve_ports`를 호출하고, 아니면 `static_ports`
    (없으면 빈 포트)를 돌려준다.

    Raises:
        PortsUnavailableError: 동적 포트인데 `resolve_ports`가 None일 때.
        Exception: `resolve_ports`가 던진 예외를 그대로 전파한다.
    """
    if descriptor.dynamic_ports:
        if resolve_ports is None:
            raise PortsUnavailableError(
                f"노드 타입 {descriptor.id!r}는 동적 포트지만 포트 해석기가 없습니다"
            )
        return resolve_ports(descriptor, config)
    return descriptor.static_ports or PortSpec()
