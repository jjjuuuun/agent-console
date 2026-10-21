"""예제 관측 수집기 `example.tool_count`: entry point 로딩(+ 제거), 백엔드 수집기 목록,
실행 중 수집, 설정 검증, 제거 뒤 남은 설정의 경고.

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). entry point는 `EntryPoint` 객체를 직접
만들어 로더에 넘기고, SDK는 가짜 클라이언트를 주입한다(모델 호출 없음).
"""

from __future__ import annotations

import tomllib
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_console_backend_claude_sdk import COLLECTOR_ISSUES, ClaudeSdkBackend
from agent_console_backend_claude_sdk.collectors import (
    COLLECTORS_GROUP,
    ClaudeSdkCollector,
    CollectorContext,
    discover_collectors,
)
from agent_console_backend_claude_sdk.testing import FakeSdkClient, ValidatingSink
from agent_console_contracts import Agent, AgentSettings, InteractionGrant
from agent_console_example_collector import (
    COLLECTOR_ID,
    DEFAULT_BACKEND,
    EVENT_TYPE,
    ToolCountCollector,
    count_tool_uses,
    merge_counts,
)
from agent_console_runtime import AgentRequest, CancelToken

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
VALUE = "agent_console_example_collector:ToolCountCollector"


def entry_point() -> EntryPoint:
    return EntryPoint(name=COLLECTOR_ID, value=VALUE, group=COLLECTORS_GROUP)


def _tools(*names: str) -> AssistantMessage:
    return AssistantMessage(
        content=[ToolUseBlock(id=f"t{i}", name=n, input={}) for i, n in enumerate(names)],
        model="m",
    )


def _result() -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="s1",
        result="ok",
    )


SCRIPT: list[Any] = [
    _tools("Read", "Bash"),
    UserMessage(content=[ToolResultBlock(tool_use_id="t0", content="r")]),
    _tools("Read"),
    AssistantMessage(content=[TextBlock("끝")], model="m"),
    _result(),
]


def _backend(collectors: list[ClaudeSdkCollector] | None) -> ClaudeSdkBackend:
    def factory(options: ClaudeAgentOptions) -> Any:
        return FakeSdkClient(options, SCRIPT)

    clock = iter(float(i) for i in range(100))
    return ClaudeSdkBackend(
        client_factory=factory, environ={}, clock=lambda: next(clock), collectors=collectors
    )


async def _run(backend: ClaudeSdkBackend, observe: dict[str, Any]) -> ValidatingSink:
    sink = ValidatingSink()
    agent = Agent(id="coder", name="Coder", backend=DEFAULT_BACKEND, tools=["Read", "Bash"])
    result = await backend.run(
        AgentRequest(agent=agent, prompt="p", observe=observe), sink, CancelToken()
    )
    assert result.status == "succeeded"
    return sink


def _observe(config: dict[str, Any] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"enabled": True}
    if config is not None:
        item["config"] = config
    return {"collectors": {COLLECTOR_ID: item}}


# ------------------------------------------------------------------ 등록


def test_entry_point_declared() -> None:
    eps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["entry-points"]
    assert eps[COLLECTORS_GROUP] == {COLLECTOR_ID: VALUE}


def test_installed_appears_in_collector_list_and_removed_disappears() -> None:
    found, reports = discover_collectors(DEFAULT_BACKEND, entry_points=[entry_point()])
    assert [(r.key, r.status) for r in reports] == [(COLLECTOR_ID, "loaded")]
    listed = [c.id for c in _backend(found).descriptor.collectors]
    assert COLLECTOR_ID in listed

    gone, _ = discover_collectors(DEFAULT_BACKEND, entry_points=[])  # 제거 = entry point 없음
    assert COLLECTOR_ID not in [c.id for c in _backend(gone).descriptor.collectors]


def test_other_backend_id_filters_it_out() -> None:
    found, _ = discover_collectors("another-backend", entry_points=[entry_point()])
    assert COLLECTOR_ID not in [c.descriptor.id for c in found]
    assert ToolCountCollector(backend="another-backend").descriptor.backend == "another-backend"


def test_descriptor_from_config_model() -> None:
    desc = ToolCountCollector().descriptor
    assert (desc.id, desc.backend, desc.emits) == (COLLECTOR_ID, DEFAULT_BACKEND, [EVENT_TYPE])
    assert desc.config_schema["properties"]["only"]["type"] == "array"


# ------------------------------------------------------------------ 실행 중 수집


async def test_counts_tool_calls_during_run() -> None:
    found, _ = discover_collectors(DEFAULT_BACKEND, entry_points=[entry_point()])
    sink = await _run(_backend(found), _observe())
    assert sink.of(EVENT_TYPE) == [{"total": 3, "by_tool": {"Bash": 1, "Read": 2}}]


async def test_only_setting_filters_tools() -> None:
    sink = await _run(_backend([ToolCountCollector()]), _observe({"only": ["Bash"]}))
    assert sink.of(EVENT_TYPE) == [{"total": 1, "by_tool": {"Bash": 1}}]


async def test_disabled_by_default() -> None:
    sink = await _run(_backend([ToolCountCollector()]), {})
    assert sink.of(EVENT_TYPE) == []


async def test_bad_config_does_not_break_run() -> None:
    sink = await _run(_backend([ToolCountCollector()]), _observe({"only": "Bash"}))
    assert sink.of(EVENT_TYPE) == [{"total": 0, "by_tool": {}}]  # 셀 수 없었다(예외는 경고로)
    warned = [p for p in sink.of("log.warning") if COLLECTOR_ID in str(p)]
    assert len(warned) == 1


# ------------------------------------------------------------------ 설정 검증·제거 뒤


def _settings(config: dict[str, Any]) -> AgentSettings:
    return AgentSettings.model_validate({"observe": {"collectors": {COLLECTOR_ID: config}}})


def test_invalid_config_is_validation_warning() -> None:
    issues = _backend([ToolCountCollector()]).validate_settings(
        _settings({"enabled": True, "config": {"only": "Bash", "x": 1}}), InteractionGrant()
    )
    [bad] = [i for i in issues if i.code == COLLECTOR_ISSUES.INVALID_CONFIG]
    assert (bad.severity, bad.details["collector"]) == ("warning", COLLECTOR_ID)


def test_leftover_settings_after_removal_only_warn() -> None:
    gone, _ = discover_collectors(DEFAULT_BACKEND, entry_points=[])
    issues = _backend(gone).validate_settings(_settings({"enabled": True}), InteractionGrant())
    [unknown] = [i for i in issues if i.code == COLLECTOR_ISSUES.UNKNOWN]
    assert (unknown.severity, unknown.details["collector"]) == ("warning", COLLECTOR_ID)


# ------------------------------------------------------------------ 순수 부분


def test_count_and_merge() -> None:
    assert count_tool_uses(_tools("Read", "Read", "Bash")) == {"Read": 2, "Bash": 1}
    assert count_tool_uses(_tools("Read", "Bash"), only={"Bash"}) == {"Bash": 1}
    assert count_tool_uses(_result()) == {}
    assert merge_counts({"b": 1}, {"a": 2, "b": 1}) == {"a": 2, "b": 2}


def test_state_is_per_run_context() -> None:
    collector = ToolCountCollector()
    first = CollectorContext(collector_id=COLLECTOR_ID, config={}, clock=lambda: 0.0)
    second = CollectorContext(collector_id=COLLECTOR_ID, config={}, clock=lambda: 0.0)
    collector.on_message(_tools("Read"), first)
    collector.on_message(_result(), second)  # 다른 실행: 앞 실행의 수를 섞지 않는다
    collector.on_message(_result(), first)
    assert [e.payload for e in second.drain()] == [{"total": 0, "by_tool": {}}]
    assert [e.payload for e in first.drain()] == [{"total": 1, "by_tool": {"Read": 1}}]
