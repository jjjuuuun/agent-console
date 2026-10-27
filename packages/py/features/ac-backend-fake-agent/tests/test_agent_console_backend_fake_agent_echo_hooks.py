"""2R.12: fake `echo_hooks`(설치자 설정) — 묶음 hooks 칸 항목마다 hook.started·hook.finished 흉내,
명령은 실행하지 않음. 기본 칸에 skills·rules·hooks가 있다."""

from __future__ import annotations

from typing import Any

from agent_console_backend_fake_agent import FakeBackend
from agent_console_backend_fake_agent.testing import ValidatingSink
from agent_console_contracts import Agent, ResourceBundle
from agent_console_runtime import AgentRequest, CancelToken, SecretResolver

HOOKS: list[Any] = [
    {"name": "fmt", "event": "AnyEvent", "matcher": "Write", "command": "fmt secret://tok"},
    "not-an-item",
]


async def _run(backend: FakeBackend) -> ValidatingSink:
    sink = ValidatingSink()
    agent = Agent(
        id="a", name="A", backend="fake-agent", backend_options={"default": {"response": "ok"}}
    )
    req = AgentRequest(agent=agent, prompt="p", bundle=ResourceBundle(slots={"hooks": HOOKS}))
    result = await backend.run(req, sink, CancelToken())
    assert result.status == "succeeded"
    return sink


def test_default_slots_include_new_known_slots() -> None:
    slots = FakeBackend().descriptor.capabilities.resource_slots
    assert {"skills", "rules", "hooks"} <= set(slots)


async def test_echo_hooks_off_by_default() -> None:
    sink = await _run(FakeBackend(ids=lambda: "s"))
    assert not [e for e in sink.events if e.type.startswith("hook.")]


async def test_echo_hooks_emits_started_and_finished_without_running() -> None:
    backend = FakeBackend.from_options({"echo_hooks": True}, secrets=SecretResolver([]), environ={})
    sink = await _run(backend)
    hooks = [e for e in sink.events if e.type.startswith("hook.")]
    assert [e.type for e in hooks] == ["hook.started", "hook.finished"]
    finished = hooks[1].payload
    assert finished["event"] == "AnyEvent"
    assert finished["simulated"] is True
    assert finished["exit_code"] == 0
    assert finished["command_preview"] == "fmt secret://***"


async def test_echo_hooks_skipped_when_slot_not_accepted() -> None:
    sink = await _run(FakeBackend(echo_hooks=True, resource_slots=["instructions"]))
    assert not [e for e in sink.events if e.type.startswith("hook.")]
