"""4R.9: fake 관측 스위치의 `observe.collectors` 해석과 hook probe 기록 흉내(규칙 데이터).

- 관측 규칙 스위치: `observe.collectors[<수집기 id>].enabled`가 옛 키(`hooks`·`mcp`)를 이긴다
  (claude-sdk `LEGACY_OBSERVE_KEYS`와 같은 규칙, 대응표는 데이터).
- 규칙 `hook_probe`: `observe.hook_probe`가 켜졌고 `run_folder`가 있으면 `hook-probe/1` 줄을 남긴다.
  실제 출처·분류기(`hook-probe-jsonl`·`hook-probe`)가 그대로 읽는다.
- 꺼짐(기본)이면 아무것도 쓰지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_console_backend_fake_agent import (
    DEFAULT_OBSERVE_COLLECTORS,
    HOOK_PROBE_NOTE_CODE,
    FakeBackend,
    FakeBackendOptions,
    observe_switch_on,
)
from agent_console_backend_fake_agent.testing import ValidatingSink
from agent_console_contracts import Agent, AgentSettings, ObserveSettings, ResourceBundle
from agent_console_runtime import AgentRequest, CancelToken, SecretResolver

PROBE: list[dict[str, Any]] = [
    {
        "event": "PreToolUse",
        "matcher": "Bash",
        "tool": "Bash",
        "tool_use_id": "$session_id:tool0",
        "input": {"tool_input": {"command": "ls"}, "prompt": "$prompt"},
        "decision": "allow",
        "duration_ms": 25,
    },
    {"event": "Stop", "after": "end", "exit_code": 2, "decision": "block", "reason": "no"},
]
CONTEXT = {"run_id": "r1", "node_path": "lead"}


def _agent(**rule: Any) -> Agent:
    return Agent(
        id="a",
        name="A",
        backend="fake-agent",
        backend_options={
            "default": {
                "response": "ok",
                "observe": [{"type": "hook.invoked", "payload": {"event": "PreToolUse"}}],
                "hook_probe": PROBE,
                **rule,
            }
        },
    )


async def _run(
    observe: dict[str, Any],
    *,
    run_folder: Path | None = None,
    backend: FakeBackend | None = None,
    bundle: ResourceBundle | None = None,
) -> ValidatingSink:
    sink = ValidatingSink()
    req = AgentRequest(
        agent=_agent(),
        prompt="go",
        cwd="/proj",
        observe=observe,
        run_folder=str(run_folder) if run_folder else None,
        run_context=dict(CONTEXT),
        bundle=bundle,
    )
    fake = backend or FakeBackend(ids=lambda: "s1", clock=lambda: 1000.0)
    result = await fake.run(req, sink, CancelToken())
    assert result.status == "succeeded"
    return sink


def _records(folder: Path, session: str = "s1") -> list[dict[str, Any]]:
    path = folder / "hook-probe" / f"{session}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ---------------------------------------------------------------- 관측 스위치


@pytest.mark.parametrize(
    ("observe", "expected"),
    [
        ({}, False),
        ({"hooks": True}, True),
        ({"collectors": {"sdk-hooks": {"enabled": True}}}, True),
        (
            {"hooks": True, "collectors": {"sdk-hooks": {"enabled": False}}},
            False,
        ),  # collectors 우선
        (
            {"hooks": True, "collectors": {"sdk-hooks": {"config": {}}}},
            True,
        ),  # enabled 없음 → 옛 키
        ({"collectors": {"sdk-hooks": "yes"}}, False),  # 모양이 틀린 항목은 무시
    ],
)
def test_switch_reads_collectors_with_legacy_rule(observe: dict[str, Any], expected: bool) -> None:
    assert observe_switch_on(observe, "hooks") is expected


def test_switch_unknown_to_table_uses_switch_as_collector_id() -> None:
    observe = {"collectors": {"example.tool_count": {"enabled": True}}}
    assert observe_switch_on(observe, "example.tool_count")
    assert DEFAULT_OBSERVE_COLLECTORS == {"hooks": "sdk-hooks", "mcp": "mcp-calls"}
    assert not observe_switch_on({"collectors": {"x": {"enabled": True}}}, "hooks", {"hooks": "y"})


async def test_observe_rules_follow_collectors_setting() -> None:
    on = await _run({"collectors": {"sdk-hooks": {"enabled": True}}})
    assert any(e.type == "hook.invoked" for e in on.events)
    off = await _run({"hooks": True, "collectors": {"sdk-hooks": {"enabled": False}}})
    assert not any(e.type == "hook.invoked" for e in off.events)


async def test_install_option_observe_collectors_table() -> None:
    backend = FakeBackend.from_options(
        {"observe_collectors": {"hooks": "my-hooks"}}, secrets=SecretResolver([]), environ={}
    )
    sink = await _run({"collectors": {"my-hooks": {"enabled": True}}}, backend=backend)
    assert any(e.type == "hook.invoked" for e in sink.events)


# ---------------------------------------------------------------- hook probe 기록 흉내


async def test_probe_records_off_by_default(tmp_path: Path) -> None:
    await _run({"hooks": True}, run_folder=tmp_path)
    await _run({"hook_probe": False}, run_folder=tmp_path)
    assert list(tmp_path.iterdir()) == []


async def test_probe_records_follow_rule_data(tmp_path: Path) -> None:
    sink = await _run({"hook_probe": True}, run_folder=tmp_path)
    first, second = _records(tmp_path)
    assert first == {
        "format": "hook-probe/1",
        "probe_id": "s1:probe1",
        "event": "PreToolUse",
        "session_id": "s1",
        "tool_use_id": "s1:tool0",
        "tool": "Bash",
        "matcher": "Bash",
        "context": CONTEXT,
        "started_at": 1000.0,
        "ended_at": 1000.025,
        "duration_ms": 25,
        "exit_code": 0,
        "error": None,
        "decision": {"value": "allow", "source": "fake-agent", "reason": None},
        "input": {"tool_input": {"command": "ls"}, "prompt": "go"},
        "agent_id": None,
        "agent_type": None,
        "cwd": "/proj",
        "simulated": True,
    }
    assert (second["event"], second["exit_code"], second["decision"]["value"]) == (
        "Stop",
        2,
        "block",
    )
    assert not any(e.type == "log.warning" for e in sink.events)


async def test_probe_records_custom_folder(tmp_path: Path) -> None:
    backend = FakeBackend.from_options(
        {"hook_probe_folder": "probe-x"}, secrets=SecretResolver([]), environ={}
    )
    await _run({"hook_probe": True}, run_folder=tmp_path, backend=backend)
    assert (tmp_path / "probe-x").is_dir()


async def test_probe_without_run_folder_warns() -> None:
    sink = await _run({"hook_probe": True})
    assert any(e.type == "log.warning" and "실행 폴더" in e.payload["message"] for e in sink.events)


async def test_echo_hooks_also_write_probe_records(tmp_path: Path) -> None:
    backend = FakeBackend(ids=lambda: "s1", clock=lambda: 5.0, echo_hooks=True)
    hooks = [{"name": "fmt", "event": "PostToolUse", "matcher": "Write", "command": "fmt"}]
    sink = await _run(
        {"hook_probe": True},
        run_folder=tmp_path,
        backend=backend,
        bundle=ResourceBundle(slots={"hooks": hooks}),
    )
    records = _records(tmp_path)
    assert (records[0]["event"], records[0]["matcher"]) == ("PostToolUse", "Write")
    finished = next(e for e in sink.events if e.type == "hook.finished")
    assert finished.payload["hook_probe"] is True


async def test_probe_record_is_read_by_real_hook_probe_plugins(tmp_path: Path) -> None:
    """흉내 기록을 실제 출처·분류기(`agent-console-hook-probe`)가 읽는다(형식 일치)."""
    pytest.importorskip("agent_console_hook_probe.plugins")
    from agent_console_contracts.logs import LogSettings
    from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context
    from agent_console_logs.testing import MemoryLogIndex

    runs = tmp_path / "runs"
    await _run({"hook_probe": True}, run_folder=runs / "r1" / "lead")
    registries = LogRegistries()
    registries.load(enabled_sources={"hook-probe-jsonl"}, enabled_classifiers={"hook-probe"})
    index = MemoryLogIndex()
    settings = LogSettings.model_validate(
        {"sources": [{"id": "hook-probe-jsonl", "config": {"roots": [str(runs)]}}]}
    )
    assert LogIngestor(index, registries).scan(settings).new_events == 4
    events = index.query_events(LogFilter(), query_context(settings)).items
    assert {e.run_id for e in events} == {"r1"}
    assert any(e.title == "Stop → block (exit 2)" for e in events)


# ---------------------------------------------------------------- 미리보기 안내


def test_preview_notes_simulate_hook_probe_note() -> None:
    backend = FakeBackend()
    bundle = ResourceBundle(slots={"hooks": [{"event": "Stop", "command": "x"}]})
    assert backend.preview_notes(AgentSettings(), bundle) == []
    (note,) = backend.preview_notes(AgentSettings(observe=ObserveSettings(hook_probe=True)), bundle)
    assert (note.severity, note.code) == ("info", HOOK_PROBE_NOTE_CODE)
    assert note.details == {"hooks": 1, "option": "observe.hook_probe", "simulated": True}


def test_hook_probe_rule_is_in_config_schema() -> None:
    schema = FakeBackendOptions.model_json_schema()
    assert "FakeHookProbe" in schema["$defs"]
