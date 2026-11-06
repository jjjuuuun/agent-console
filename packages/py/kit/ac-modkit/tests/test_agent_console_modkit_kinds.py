"""6R.5: 정의 종류 기여 포트(X44). 키트는 종류 값의 타입을 모른다."""

from __future__ import annotations

from typing import Any

from agent_console_modkit import (
    DEFINITION_KIND_CONTRIBUTIONS,
    KindContribution,
    ModuleContext,
    assemble,
)
from agent_console_modkit.testing import fake_module


def _provider(module_id: str, *items: KindContribution[Any]) -> Any:
    def build(ctx: ModuleContext) -> None:
        for item in items:
            ctx.provide(DEFINITION_KIND_CONTRIBUTIONS, item)

    return fake_module(module_id, provides=[DEFINITION_KIND_CONTRIBUTIONS], on_build=build)


def test_port_is_multi_and_named() -> None:
    assert DEFINITION_KIND_CONTRIBUTIONS.name == "definitions.kind_contributions"
    assert DEFINITION_KIND_CONTRIBUTIONS.multi


def test_contribution_defaults() -> None:
    c: KindContribution[str] = KindContribution("note")
    assert (c.kind, c.references, c.summary_fields) == ("note", None, ())


def test_consumer_gets_all_contributions_in_module_order() -> None:
    seen: list[list[Any]] = []

    def consume(ctx: ModuleContext) -> None:
        seen.append([c.kind for c in ctx.ports(DEFINITION_KIND_CONTRIBUTIONS)])

    consumer = fake_module("consumer", optional=[DEFINITION_KIND_CONTRIBUTIONS], on_build=consume)
    refs = KindContribution("b1", references=lambda doc: [("agent", str(doc["agent"]))])
    assembly = assemble(
        [consumer, _provider("b-kinds", refs), _provider("a-kinds", KindContribution("a1"))]
    )
    assert seen == [["a1", "b1"]]
    found = assembly.ports(DEFINITION_KIND_CONTRIBUTIONS)
    assert [list(c.references({"agent": "rev"})) for c in found if c.references] == [
        [("agent", "rev")]
    ]


def test_consumer_alone_gets_empty_list() -> None:
    seen: list[int] = []

    def consume(ctx: ModuleContext) -> None:
        seen.append(len(ctx.ports(DEFINITION_KIND_CONTRIBUTIONS)))

    assemble([fake_module("consumer", optional=[DEFINITION_KIND_CONTRIBUTIONS], on_build=consume)])
    assert seen == [0]
