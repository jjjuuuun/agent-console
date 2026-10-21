"""디스크립터 묶음: 플러그인 레지스트리 묶음(구조적) → ``TeamCatalog``(3R.12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts import (
    AgentSettings,
    BackendCapabilities,
    BackendDescriptor,
    Issue,
    NodeTypeDescriptor,
)
from agent_console_registry import Registry
from agent_console_teams import TeamCatalog, catalog_from_registries
from agent_console_teams.testing import Kit


@dataclass
class _Described:
    descriptor: Any


class _Validating:
    """``validate_settings`` 훅이 있는 백엔드."""

    descriptor = BackendDescriptor(
        id="b-hook", title="훅", capabilities=BackendCapabilities(resume=True)
    )

    def validate_settings(self, effective: AgentSettings, grant: Any) -> list[Issue]:
        return []


@dataclass
class _Registries:
    node_types: Registry[Any] = field(default_factory=lambda: Registry("node_types"))
    edge_types: Registry[Any] = field(default_factory=lambda: Registry("edge_types"))
    delegation_strategies: Registry[Any] = field(default_factory=lambda: Registry("s"))
    backends: Registry[Any] = field(default_factory=lambda: Registry("backends"))


def test_catalog_reads_every_registry_and_plans() -> None:
    k = Kit()
    regs = _Registries()
    for d in k.node_types:
        regs.node_types.register(d.id, _Described(d))
    old = NodeTypeDescriptor(id=k["worker"], title="옛 일꾼", version=0)
    regs.node_types.register(old.id, _Described(old), version=0)
    for e in k.edge_types:
        regs.edge_types.register(e.id, _Described(e))
    for s in k.strategies:
        regs.delegation_strategies.register(s.id, _Described(s))
    plain = BackendDescriptor(id="b-plain", title="평범")
    regs.backends.register("b-plain", _Described(plain))
    regs.backends.register("b-hook", _Validating())

    catalog = catalog_from_registries(regs)

    assert len(catalog.node_types) == len(k.node_types) + 1  # 모든 버전
    assert {e.id for e in catalog.edge_types} == {e.id for e in k.edge_types}
    assert set(catalog.strategies) == {s.id for s in k.strategies}
    assert catalog.backends["b-hook"].resume
    assert set(catalog.settings_validators) == {"b-hook"}
    graph = k.graph([k.person(), k.worker("a", "alice")], [k.edge("e1", "entry", "me", "a")])
    plan = catalog.plan(graph)
    assert plan.entry_nodes == ("a",)


def test_missing_registries_give_empty_catalog() -> None:
    assert catalog_from_registries(None) == TeamCatalog()
    assert catalog_from_registries(object()).node_types == ()


def test_try_plan_returns_none_on_failure() -> None:
    k = Kit()
    graph = k.graph([k.worker("a", "alice")], [])
    assert TeamCatalog(node_types=tuple(k.node_types)).try_plan(graph) is not None

    class Broken(TeamCatalog):
        def plan(self, graph: Any, **_: Any) -> Any:
            raise ValueError("해석 불가")

    assert Broken().try_plan(graph) is None
