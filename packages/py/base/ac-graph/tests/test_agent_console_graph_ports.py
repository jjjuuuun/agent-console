"""node_ports: 정적/동적 포트 해석."""

from collections.abc import Mapping
from typing import Any

import pytest

from agent_console_contracts import NodeTypeDescriptor, PortDef, PortSpec
from agent_console_graph import PortsUnavailableError, node_ports


def test_static_ports_and_default_empty() -> None:
    spec = PortSpec(inputs=[PortDef(name="i")])
    assert node_ports(NodeTypeDescriptor(id="zz", title="t", static_ports=spec), {}) == spec
    assert node_ports(NodeTypeDescriptor(id="zz", title="t"), {}) == PortSpec()


def test_dynamic_ports_call_resolver_or_raise() -> None:
    desc = NodeTypeDescriptor(id="zz", title="t", dynamic_ports=True)

    def resolver(d: NodeTypeDescriptor, config: Mapping[str, Any]) -> PortSpec:
        return PortSpec(outputs=[PortDef(name=config["p"])])

    assert node_ports(desc, {"p": "q"}, resolver).outputs[0].name == "q"
    with pytest.raises(PortsUnavailableError):
        node_ports(desc, {})
