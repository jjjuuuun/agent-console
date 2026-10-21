"""4R.9: hook probe 감싸기(가짜 SDK 클라이언트, 실호출 없음).

- `observe.hook_probe`가 참이면 전달하는 명령형 hook(callback·settings 두 경로)을 probe로 감싼다.
  기록 폴더 = `AgentRequest.run_folder/hook-probe`, 맥락 = `run_context`.
- 꺼짐(기본)이면 명령이 그대로다. 실행 범위 검사는 원래 명령으로 한다.
- 설치자 옵션 `hook_probe_command`·`hook_probe_folder`를 따른다.
- 묶음 미리보기 훅 `preview_notes`가 "hook 감싸기 켜짐" 안내를 낸다.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, SystemMessage

from agent_console_backend_claude_sdk import (
    DEFAULT_HOOK_PROBE_FOLDER,
    HOOK_PROBE_ISSUES,
    ClaudeSdkBackend,
    HookProcess,
    plan_hook_probe,
    subprocess_runner,
)
from agent_console_backend_claude_sdk.testing import FakeSdkClient, ValidatingSink
from agent_console_contracts import Agent, AgentSettings, Limits, ObserveSettings, ResourceBundle
from agent_console_hook_probe import default_probe_command, wrap_command, wrap_command_line
from agent_console_runtime import AgentRequest, CancelToken, SecretResolver

HOOK = {"name": "fmt", "event": "PostToolUse", "matcher": "Write", "command": "fmt --check"}
CONTEXT = {"run_id": "r1", "node_path": "lead"}


def _agent(**options: Any) -> Agent:
    return Agent(
        id="lead",
        name="Lead",
        model="m",
        tools=["Read"],
        system_prompt="you lead",
        backend="claude-agent-sdk",
        backend_options=options,
    )


def _capture(
    **kw: Any,
) -> tuple[list[FakeSdkClient], Callable[[ClaudeAgentOptions], Any]]:
    clients: list[FakeSdkClient] = []

    def factory(options: ClaudeAgentOptions) -> Any:
        script = [
            SystemMessage(subtype="init", data={"session_id": "s1", "model": "m"}),
            ResultMessage(
                subtype="success",
                duration_ms=1,
                duration_api_ms=1,
                is_error=False,
                num_turns=1,
                session_id="s1",
                result="done",
            ),
        ]
        client = FakeSdkClient(options, script, **kw)
        clients.append(client)
        return client

    return clients, factory


class _Runner:
    def __init__(self, result: HookProcess | None = None) -> None:
        self.result = result or HookProcess(exit_code=0)
        self.calls: list[list[str]] = []

    async def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: bytes,
        cwd: str | None,
        env: Mapping[str, str],
        timeout: float,
    ) -> HookProcess:
        self.calls.append(list(argv))
        return self.result


async def _run(
    backend: ClaudeSdkBackend,
    *,
    observe: dict[str, Any] | None = None,
    run_folder: str | None = None,
    agent: Agent | None = None,
    limits: Limits | None = None,
    hooks: list[dict[str, Any]] | None = None,
    cwd: str = "/proj",
) -> ValidatingSink:
    sink = ValidatingSink()
    req = AgentRequest(
        agent=agent or _agent(),
        prompt="p",
        cwd=cwd,
        bundle=ResourceBundle(slots={"hooks": hooks if hooks is not None else [HOOK]}),
        observe=observe or {},
        run_folder=run_folder,
        run_context=dict(CONTEXT),
        limits=limits or Limits(commands=["fmt"]),
    )
    result = await backend.run(req, sink, CancelToken())
    assert result.status == "succeeded", result.error
    return sink


def _backend(
    factory: Callable[[ClaudeAgentOptions], Any], runner: _Runner, **kw: Any
) -> ClaudeSdkBackend:
    return ClaudeSdkBackend(
        client_factory=factory, environ={}, allow_command_hooks=True, hook_runner=runner, **kw
    )


def _warned(sink: ValidatingSink, text: str) -> bool:
    return any(e.type == "log.warning" and text in e.payload["message"] for e in sink.events)


# ---------------------------------------------------------------- 꺼짐(기본)


@pytest.mark.parametrize("observe", [None, {"hook_probe": False}, {"hooks": True}])
async def test_off_by_default_leaves_command_unchanged(tmp_path: Path, observe: Any) -> None:
    runner = _Runner()
    _, factory = _capture(hook_calls=[("PostToolUse", {"hook_event_name": "PostToolUse"})])
    sink = await _run(_backend(factory, runner), observe=observe, run_folder=str(tmp_path / "f"))
    assert runner.calls == [["fmt", "--check"]]
    finished = next(e for e in sink.events if e.type == "hook.finished")
    assert "hook_probe" not in finished.payload
    assert not (tmp_path / "f").exists()


async def test_off_settings_delivery_keeps_original_command(tmp_path: Path) -> None:
    clients, factory = _capture()
    await _run(
        _backend(factory, _Runner()),
        agent=_agent(hook_delivery="settings"),
        run_folder=str(tmp_path),
    )
    settings = json.loads(clients[0].options.settings)
    (entry,) = settings["hooks"]["PostToolUse"]
    assert entry["hooks"][0]["command"] == "fmt --check"


# ---------------------------------------------------------------- 켜짐


async def test_callback_wraps_with_default_probe(tmp_path: Path) -> None:
    runner = _Runner()
    _, factory = _capture(hook_calls=[("PostToolUse", {"hook_event_name": "PostToolUse"})])
    folder = tmp_path / "runs" / "r1" / "lead"
    sink = await _run(
        _backend(factory, runner), observe={"hook_probe": True}, run_folder=str(folder)
    )
    (argv,) = runner.calls
    assert argv == wrap_command(
        ["fmt", "--check"],
        out=folder / DEFAULT_HOOK_PROBE_FOLDER,
        matcher="Write",
        context=CONTEXT,
    )
    assert argv[:3] == default_probe_command()
    assert argv[-3:] == ["--", "fmt", "--check"]
    finished = next(e for e in sink.events if e.type == "hook.finished")
    assert finished.payload["hook_probe"] is True
    assert finished.payload["command_preview"] == "fmt --check"  # 미리보기는 원래 명령


async def test_limits_checked_against_original_command(tmp_path: Path) -> None:
    runner = _Runner()
    _, factory = _capture(hook_calls=[("PostToolUse", {"hook_event_name": "PostToolUse"})])
    sink = await _run(
        _backend(factory, runner),
        observe={"hook_probe": True},
        run_folder=str(tmp_path),
        limits=Limits(commands=["git status"]),
    )
    assert runner.calls == []  # 감싼 명령(python …)이 아니라 원래 명령으로 검사해 막는다
    finished = next(e for e in sink.events if e.type == "hook.finished")
    assert finished.payload["error"] == "limits"


async def test_install_options_probe_command_and_folder(tmp_path: Path) -> None:
    runner = _Runner()
    _, factory = _capture(hook_calls=[("PostToolUse", {"hook_event_name": "PostToolUse"})])
    backend = ClaudeSdkBackend.from_options(
        {
            "allow_command_hooks": True,
            "hook_probe_command": ["/opt/probe", "--quiet"],
            "hook_probe_folder": "probe-records",
        },
        secrets=SecretResolver([]),
        environ={},
    )
    backend._client_factory = factory
    backend._hook_runner = runner
    await _run(backend, observe={"hook_probe": True}, run_folder=str(tmp_path))
    (argv,) = runner.calls
    assert argv[:4] == ["/opt/probe", "--quiet", "--out", str(tmp_path / "probe-records")]


@pytest.mark.parametrize("folder", ["../x", "a/b", ".", ""])
def test_install_option_folder_must_be_plain_name(folder: str) -> None:
    with pytest.raises(ValueError, match="hook_probe_folder"):
        ClaudeSdkBackend.from_options(
            {"hook_probe_folder": folder}, secrets=SecretResolver([]), environ={}
        )


async def test_settings_delivery_wraps_command_line(tmp_path: Path) -> None:
    clients, factory = _capture()
    await _run(
        _backend(factory, _Runner()),
        agent=_agent(hook_delivery="settings"),
        observe={"hook_probe": True},
        run_folder=str(tmp_path),
    )
    settings = json.loads(clients[0].options.settings)
    (entry,) = settings["hooks"]["PostToolUse"]
    assert entry["hooks"][0]["command"] == wrap_command_line(
        "fmt --check", out=tmp_path / "hook-probe", matcher="Write", context=CONTEXT
    )


async def test_without_run_folder_warns_and_does_not_wrap() -> None:
    runner = _Runner()
    _, factory = _capture(hook_calls=[("PostToolUse", {"hook_event_name": "PostToolUse"})])
    sink = await _run(_backend(factory, runner), observe={"hook_probe": True})
    assert runner.calls == [["fmt", "--check"]]
    assert _warned(sink, "실행 폴더가 없어")


async def test_missing_probe_package_warns_and_does_not_wrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "agent_console_hook_probe", None)
    runner = _Runner()
    _, factory = _capture(hook_calls=[("PostToolUse", {"hook_event_name": "PostToolUse"})])
    sink = await _run(
        _backend(factory, runner), observe={"hook_probe": True}, run_folder=str(tmp_path)
    )
    assert runner.calls == [["fmt", "--check"]]
    assert _warned(sink, "agent-console-hook-probe")


def test_plan_ignores_empty_context_values(tmp_path: Path) -> None:
    plan, warnings = plan_hook_probe(
        {"hook_probe": True},
        run_folder=str(tmp_path),
        run_context={"run_id": "r", "node_path": "", "a=b": "x"},
        probe_command=None,
    )
    assert warnings == []
    assert plan is not None
    assert plan.context == {"run_id": "r"}
    assert plan_hook_probe({}, run_folder=str(tmp_path), run_context={}, probe_command=None) == (
        None,
        [],
    )


async def test_real_probe_records_hook_run(tmp_path: Path) -> None:
    """실제 probe(하위 프로세스)로 감싸 돌리면 원래 hook 출력이 그대로 돌아오고 기록이 남는다."""
    script = tmp_path / "hook.py"
    script.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'decision': 'block', 'reason': 'lint'}))\n",
        encoding="utf-8",
    )
    command = f"{Path(sys.executable).as_posix()} {script.as_posix()}"
    data = {"hook_event_name": "PostToolUse", "tool_name": "Write", "session_id": "s1"}
    clients, factory = _capture(hook_calls=[("PostToolUse", data)])
    folder = tmp_path / "runs" / "r1" / "lead"
    backend = ClaudeSdkBackend(
        client_factory=factory,
        environ={"PATH": "/usr/bin:/bin", "SYSTEMROOT": "C:\\Windows"},
        allow_command_hooks=True,
        hook_runner=subprocess_runner,
    )
    await _run(
        backend,
        cwd=str(tmp_path),
        observe={"hook_probe": True},
        run_folder=str(folder),
        hooks=[{**HOOK, "command": command}],
        limits=Limits(commands=["*"]),
    )
    assert {"decision": "block", "reason": "lint"} in clients[0].hook_outputs
    record = json.loads((folder / "hook-probe" / "s1.jsonl").read_text(encoding="utf-8"))
    assert record["format"] == "hook-probe/1"
    assert record["event"] == "PostToolUse"
    assert record["matcher"] == "Write"
    assert record["context"] == CONTEXT
    assert record["decision"]["value"] == "block"


# ---------------------------------------------------------------- 묶음 미리보기


def test_preview_notes_off_and_on() -> None:
    backend = ClaudeSdkBackend(environ={}, allow_command_hooks=True)
    bundle = ResourceBundle(slots={"hooks": [HOOK, HOOK]})
    assert backend.preview_notes(AgentSettings(), bundle) == []
    off = AgentSettings(observe=ObserveSettings(hook_probe=False))
    assert backend.preview_notes(off, bundle) == []
    on = AgentSettings(observe=ObserveSettings(hook_probe=True))
    (note,) = backend.preview_notes(on, bundle)
    assert note.severity == "info"
    assert note.code == HOOK_PROBE_ISSUES.WRAPPED == "observe.hook_probe_wrapped"
    assert note.details["hooks"] == 2
    assert "hook 감싸기 켜짐" in note.message


def test_preview_notes_when_command_hooks_not_delivered() -> None:
    backend = ClaudeSdkBackend(environ={})
    (note,) = backend.preview_notes(
        AgentSettings(observe=ObserveSettings(hook_probe=True)),
        ResourceBundle(slots={"hooks": [HOOK]}),
    )
    assert note.details["hooks"] == 0
    assert "allow_command_hooks" in note.message
