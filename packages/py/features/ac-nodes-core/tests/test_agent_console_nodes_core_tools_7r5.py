"""ac-nodes-core 공급자 지침 `ToolProvision.instructions`(7R.5, design §7R X30 변경).

공급자는 테스트 공급자 `EchoToolProvider`와 이 파일의 임의 공급자만 쓴다(특정 기능을 모른다).
실행 도우미는 X30 테스트(`tools_57r12`)의 것을 그대로 쓴다.
"""

from __future__ import annotations

import hashlib
from typing import Any

from agent_console_backend_fake_agent import FakeBackend
from agent_console_contracts import (
    BundleSource,
    Graph,
    KnownResourceSlots,
    NodeSpec,
    Resource,
    ResourceBundle,
)
from agent_console_nodes_core import (
    CONTEXT_PREPARED_EVENT,
    INSTRUCTION_SOURCE_PREFIX,
    RESOURCE_LOOKUP,
    RESOURCE_TYPES_EXTENSION,
    TEAM_LOOKUP,
    MergedToolProvision,
    ToolProviderCodes,
    ToolProvision,
    ToolProvisionContext,
    attach_instructions,
    context_prepared_payload,
    instruction_source,
    provide_tools,
)
from agent_console_nodes_core.testing import EchoToolProvider
from agent_console_resources import InMemoryResources, load_resource_types
from agent_console_runtime.testing import SequentialIds, StepClock

from .test_agent_console_nodes_core_tools_57r12 import (  # type: ignore[import-not-found]
    Recording,
    Stack,
    _ctx,
    agent,
    calls,
    dele,
    e,
    make_stack,
    n,
    solo,
    team,
)

SLOT = KnownResourceSlots.INSTRUCTIONS


class Texts:
    """지침만 주는 공급자(도구 없음). 잘못된 항목 흉내도 낸다."""

    def __init__(self, id: str, *texts: Any) -> None:
        self.id = id
        self.texts = texts

    def provide(self, ctx: ToolProvisionContext) -> ToolProvision:
        return ToolProvision(instructions=self.texts)


# ---------------------------------------------------------------- 단위


def test_default_provision_has_no_instructions() -> None:
    assert ToolProvision().instructions == ()
    assert EchoToolProvider().provide(_ctx()).instructions == ()


def test_provide_tools_collects_instructions_in_provider_order() -> None:
    got = provide_tools(
        [Texts("t.a", "A1", "  ", "A2"), Texts("t.bad", 3, "B"), Texts("t.c", "C")], _ctx()
    )
    assert isinstance(got, MergedToolProvision)
    assert got.sourced_instructions() == [
        ("t.a", "A1"),
        ("t.a", "A2"),
        ("t.bad", "B"),
        ("t.c", "C"),
    ]
    # 글이 아닌 항목만 빠진다(공백뿐인 글은 조용히 빠진다)
    assert [(i.code, i.details["provider"], i.details["error"]) for i in got.warnings] == [
        (ToolProviderCodes.PROVIDER_FAILED, "t.bad", "int")
    ]


def test_attach_instructions_appends_after_existing_items_and_sources() -> None:
    base = ResourceBundle(
        slots={SLOT: ["리소스 지침"], "other": [1]},
        sources={SLOT: [BundleSource(ref="r1", resource_type="instruction")]},
    )
    got = attach_instructions(base, [("t.a", "A1"), ("t.b", "B1"), ("t.a", "A2")])
    assert got is not None
    assert got.slots[SLOT] == ["리소스 지침", "A1", "B1", "A2"]
    assert got.slots["other"] == [1]
    assert [s.ref for s in got.sources[SLOT]] == ["r1", "tool_provider:t.a", "tool_provider:t.b"]
    # 원본은 그대로
    assert base.slots[SLOT] == ["리소스 지침"]
    assert instruction_source("x") == f"{INSTRUCTION_SOURCE_PREFIX}x" == "tool_provider:x"


def test_attach_instructions_edges() -> None:
    assert attach_instructions(None, []) is None
    same = ResourceBundle(slots={"x": [1]})
    assert attach_instructions(same, []) is same
    fresh = attach_instructions(None, [("p", "글")])
    assert fresh is not None
    assert fresh.slots == {SLOT: ["글"]}
    wrapped = attach_instructions(ResourceBundle(slots={SLOT: "단일"}), [("p", "글")])
    assert wrapped is not None
    assert wrapped.slots[SLOT] == ["단일", "글"]


def test_context_payload_uses_inline_bodies_for_provider_sources() -> None:
    bundle = attach_instructions(None, [("t.a", "가나")])
    payload = context_prepared_payload(
        bundle, InMemoryResources([]), inline={"tool_provider:t.a": "가나"}
    )
    body = "가나".encode()
    assert [r.model_dump() for r in payload.resources] == [
        {
            "id": "tool_provider:t.a",
            "kind": SLOT,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }
    ]


# ---------------------------------------------------------------- 실행


def _with_instruction(stack: Stack, graph_nodes: list[NodeSpec], target: str) -> Graph:
    """`target` 노드에 지침 리소스(본문 "리소스 지침")를 붙인 1인 팀."""
    load_resource_types(stack.registries.extension(RESOURCE_TYPES_EXTENSION))
    stack.services[RESOURCE_LOOKUP] = InMemoryResources(
        [
            Resource.model_validate(
                {
                    "id": "ins",
                    "type": "instruction",
                    "name": "지침",
                    "config": {"text": "리소스 지침"},
                }
            )
        ]
    )
    graph: Graph = team(
        [
            *graph_nodes,
            NodeSpec.model_validate(
                {"id": "res", "type": "resource", "config": {"resource_ref": "ins"}}
            ),
        ],
        [
            e("m", "you", "says", target, "in", "message"),
            e("r", target, "out", "you", "hears", "reply"),
            e("u", "res", "provides", target, "resources", "uses"),
        ],
    )
    return graph


async def test_no_instructions_keeps_request_identical() -> None:
    """지침 없는 공급자 = 공급자 없음과 같은 요청(차등). 리소스 지침이 붙어 있어도 같다."""
    dumps = []
    for providers in (None, [EchoToolProvider("t.none", tools=False)], [Texts("t.blank", " ")]):
        stack = make_stack(agent("lead"), providers=providers)
        run = await stack.run(_with_instruction(stack, [n("lead")], "lead"), "x")
        assert run.status == "completed", run.error
        (req,) = stack.requests_of("lead")
        assert req.bundle is not None
        assert req.bundle.slots[SLOT] == ["리소스 지침"]
        dumps.append(req.model_dump(mode="json", exclude={"host_tools"}))
        (prepared,) = stack.events(run, CONTEXT_PREPARED_EVENT)
        assert [r["id"] for r in prepared.payload["resources"]] == ["ins"]
        assert not any(w["code"].startswith("tools.") for w in stack.warnings(run))
    assert dumps[0] == dumps[1] == dumps[2]

    # 첨부도 공급자 지침도 없으면 묶음 자체가 없다(전과 같음)
    stack = make_stack(agent("lead"), providers=[EchoToolProvider("t.none")])
    run = await stack.run(solo(), "x")
    (req,) = stack.requests_of("lead")
    assert req.bundle is None


async def test_two_providers_instructions_follow_resource_instructions() -> None:
    a = EchoToolProvider("t.a", tool_name="t_a", instructions=["A1", "A2"])
    b = Texts("t.b", "B1")
    stack = make_stack(agent("lead", "$bundle"), providers=[a, b])
    run = await stack.run(_with_instruction(stack, [n("lead")], "lead"), "x")
    assert run.status == "completed", run.error
    (req,) = stack.requests_of("lead")
    assert req.bundle is not None
    assert req.bundle.slots[SLOT] == ["리소스 지침", "A1", "A2", "B1"]
    assert [s.ref for s in req.bundle.sources[SLOT]] == [
        "ins",
        "tool_provider:t.a",
        "tool_provider:t.b",
    ]
    assert [t.name for t in req.host_tools] == ["t_a"]

    (prepared,) = stack.events(run, CONTEXT_PREPARED_EVENT)
    refs = {r["id"]: r for r in prepared.payload["resources"]}
    assert list(refs) == ["ins", "tool_provider:t.a", "tool_provider:t.b"]
    joined = b"A1\n\nA2"
    assert refs["tool_provider:t.a"] == {
        "id": "tool_provider:t.a",
        "kind": SLOT,
        "bytes": len(joined),
        "sha256": hashlib.sha256(joined).hexdigest(),
    }
    # 본문은 이벤트에 없다
    assert "A1" not in prepared.model_dump_json()
    # fake 백엔드도 받은 칸과 출처를 본다
    out = stack.output(run, "lead")
    assert f"{SLOT}=4 [ins, tool_provider:t.a, tool_provider:t.b]" in out


async def test_instructions_without_attachments_create_bundle() -> None:
    stack = make_stack(agent("lead"), providers=[Texts("t.only", "지침만")])
    run = await stack.run(solo(), "x")
    assert run.status == "completed", run.error
    (req,) = stack.requests_of("lead")
    assert req.bundle is not None
    assert req.bundle.slots == {SLOT: ["지침만"]}
    assert req.host_tools == []


async def test_backend_without_instructions_slot_warns_and_keeps_tools() -> None:
    stack = make_stack(
        agent("lead"), providers=[EchoToolProvider("t.a", tool_name="t_a", instructions=["A"])]
    )
    slots = [s for s in FakeBackend().descriptor.capabilities.resource_slots if s != SLOT]
    stack.backends["noins"] = Recording(
        FakeBackend(ids=SequentialIds("q"), clock=StepClock(), resource_slots=slots), "noins"
    )
    stack.registries.backends.register("noins", stack.backends["noins"])
    run = await stack.run(solo(settings={"backend": "noins"}), "x")
    assert run.status == "completed", run.error
    (req,) = stack.requests_of("lead")
    assert req.bundle is None
    assert [t.name for t in req.host_tools] == ["t_a"]
    found = [w for w in stack.warnings(run) if w["code"].startswith("tools.")]
    assert found == [
        {
            "code": ToolProviderCodes.INSTRUCTIONS_UNSUPPORTED,
            "provider": "t.a",
            "backend": "noins",
            "node": "lead",
        }
    ]


async def test_instructions_reach_backend_without_host_tools_capability() -> None:
    """도구 능력이 없는 백엔드도 지침 칸을 받으면 지침은 간다(도구만 빠진다)."""
    stack = make_stack(
        agent("lead"), providers=[EchoToolProvider("t.a", tool_name="t_a", instructions=["A"])]
    )
    run = await stack.run(solo(settings={"backend": "plain"}), "x")
    assert run.status == "completed", run.error
    (req,) = stack.requests_of("lead")
    assert req.host_tools == []
    assert req.bundle is not None
    assert req.bundle.slots[SLOT] == ["A"]
    codes = [w["code"] for w in stack.warnings(run) if w["code"].startswith("tools.")]
    assert codes == [ToolProviderCodes.BACKEND_CAPABILITY_MISSING]


async def test_host_delegate_target_and_delegator_get_own_instructions() -> None:
    class PerNode:
        id = "t.node"

        def provide(self, ctx: ToolProvisionContext) -> ToolProvision:
            return ToolProvision(instructions=(f"지침:{ctx.node_id}",))

    lead = agent("pl", "[$host_1]", **calls(("delegate", {"target": "be", "task": "$prompt"})))
    stack = make_stack(lead, agent("be", "BE($prompt)"), providers=[PerNode()])
    graph = team(
        [n("pl"), n("be")],
        [
            e("m", "you", "says", "pl", "in", "message"),
            dele("pl", "be"),
            e("r", "pl", "out", "you", "hears", "reply"),
        ],
    )
    run = await stack.run(graph, "x")
    assert run.status == "completed", run.error
    (pl_req,) = stack.requests_of("pl")
    (be_req,) = stack.requests_of("be")
    assert pl_req.bundle is not None
    assert be_req.bundle is not None
    assert pl_req.bundle.slots[SLOT] == ["지침:pl"]
    assert be_req.bundle.slots[SLOT] == ["지침:be"]
    assert [t.name for t in pl_req.host_tools] == ["delegate"]


async def test_mixed_delegation_keeps_delegator_instructions() -> None:
    stack = make_stack(
        agent("pl"), agent("be"), agent("qa"), providers=[Texts("t.only", "위임자 지침")]
    )
    graph = team(
        [n("pl"), n("be"), n("qa")],
        [
            e("m", "you", "says", "pl", "in", "message"),
            dele("pl", "be"),
            dele("pl", "qa", "subagent"),
            e("r", "pl", "out", "you", "hears", "reply"),
        ],
    )
    run = await stack.run(graph, "x")
    assert run.status == "completed", run.error
    (req,) = stack.requests_of("pl")
    assert req.bundle is not None
    assert req.bundle.slots[SLOT] == ["위임자 지침"]


async def test_child_run_gets_instructions() -> None:
    stack = make_stack(agent("lead"), agent("c1"), providers=[Texts("t.only", "공통 지침")])
    child = solo("c1", "child")
    stack.services[TEAM_LOOKUP] = lambda team_id, version: child if team_id == "child" else None
    parent = team(
        [n("lead"), n("T", type="team", team_ref="child")],
        [
            e("m", "you", "says", "lead", "in", "message"),
            e("h", "lead", "out", "T", "in", "handoff"),
            e("r", "T", "out", "you", "hears", "reply"),
        ],
        "parent",
    )
    run = await stack.run(parent, "hi")
    assert run.status == "completed", run.error
    (c1_req,) = stack.requests_of("c1")
    assert c1_req.bundle is not None
    assert c1_req.bundle.slots[SLOT] == ["공통 지침"]
