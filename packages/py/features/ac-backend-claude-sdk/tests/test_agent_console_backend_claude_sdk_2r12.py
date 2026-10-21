"""2R.12: skill·rule·hook 칸 전달(가짜 SDK 클라이언트, 실호출 없음 — C1 막힘).

- skills → `plugins=[{type: local, path}]` + `skills=[plugin:skill]` + `Skill` 도구, 서브에이전트는
  `AgentDefinition.skills`.
- rules → 기본 지침(머리말 포함), `rule_delivery=files`면 규칙 폴더를 추가 폴더 + 환경변수.
- hooks → 설치자 `allow_command_hooks`(기본 꺼짐)일 때만. callback = 실행 범위 검사 후 하위 프로세스
  (stdin JSON / stdout JSON, 종료 코드 2 = 막기), `hook.started/finished`. settings = 인라인 JSON.
- 사용자 프로젝트(cwd)·HOME(`~/.claude`)에 아무것도 쓰지 않는다.
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
    HOOKS_DISABLED_NOTE,
    ClaudeSdkBackend,
    HookProcess,
    HookSpec,
    ToolGuard,
    command_hook,
    hook_settings_json,
    subprocess_runner,
)
from agent_console_backend_claude_sdk.testing import FakeSdkClient, ValidatingSink
from agent_console_contracts import Agent, Limits, ResourceBundle
from agent_console_runtime import AgentRequest, CancelToken, SecretResolver, SubagentSpec

# ---------------------------------------------------------------- 도우미


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


def _script() -> list[Any]:
    return [
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


def _capture(
    **kw: Any,
) -> tuple[list[FakeSdkClient], Callable[[ClaudeAgentOptions], Any]]:
    clients: list[FakeSdkClient] = []

    def factory(options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, _script(), **kw)
        clients.append(client)
        return client

    return clients, factory


class _Runner:
    """가짜 hook 실행기: 호출을 기록하고 정해 둔 결과를 돌려준다."""

    def __init__(self, result: HookProcess) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: bytes,
        cwd: str | None,
        env: Mapping[str, str],
        timeout: float,
    ) -> HookProcess:
        self.calls.append(
            {"argv": list(argv), "stdin": stdin, "cwd": cwd, "env": dict(env), "timeout": timeout}
        )
        return self.result


def _skill_item(tree: Path, name: str) -> dict[str, Any]:
    root = tree / "skills" / name
    return {
        "name": name,
        "root": str(root),
        "tree_root": str(tree),
        "files": [{"name": "SKILL.md", "path": str(root / "SKILL.md")}],
    }


def _rule_item(tree: Path) -> dict[str, Any]:
    return {
        "name": "api",
        "paths": ["src/**"],
        "text": "검증 먼저",
        "instruction": "다음 경로: src/**\n\n검증 먼저",
        "root": str(tree / "rules" / "api"),
        "tree_root": str(tree),
        "files": [],
    }


HOOK = {"name": "fmt", "event": "PostToolUse", "matcher": "Write", "command": "fmt --check"}


async def _run(
    backend: ClaudeSdkBackend, bundle: dict[str, Any], **kw: Any
) -> tuple[ValidatingSink, Any]:
    sink = ValidatingSink()
    req = AgentRequest(
        agent=kw.pop("agent", _agent()),
        prompt="p",
        cwd=kw.pop("cwd", "/proj"),
        bundle=ResourceBundle(slots=bundle),
        **kw,
    )
    result = await backend.run(req, sink, CancelToken())
    assert result.status == "succeeded", result.error
    return sink, result


# ---------------------------------------------------------------- skills


async def test_skills_become_local_plugin_and_qualified_names(tmp_path: Path) -> None:
    clients, factory = _capture()
    tree = tmp_path / "run" / "lead" / "_bundle" / "lead"
    await _run(
        ClaudeSdkBackend(client_factory=factory, environ={}),
        {"skills": [_skill_item(tree, "review"), _skill_item(tree, "deploy")]},
    )
    options = clients[0].options
    assert options.plugins == [{"type": "local", "path": str(tree)}]
    assert options.skills == ["lead:review", "lead:deploy"]
    assert "Skill" in options.tools
    assert options.setting_sources == ["project"]  # 사용자 설정 격리 유지


async def test_skill_name_template_and_bad_layout_warning(tmp_path: Path) -> None:
    clients, factory = _capture()
    tree = tmp_path / "t"
    odd = {**_skill_item(tree, "x"), "root": str(tmp_path / "elsewhere" / "x")}
    sink, _ = await _run(
        ClaudeSdkBackend(client_factory=factory, environ={}),
        {"skills": [_skill_item(tree, "a"), odd, {"name": "nopath"}]},
        agent=_agent(skill_name_template="{skill}"),
    )
    assert clients[0].options.skills == ["a"]
    warnings = [e for e in sink.events if e.type == "log.warning"]
    assert sum(1 for w in warnings if w.payload.get("details", {}).get("slot") == "skills") == 2


async def test_subagent_skills_go_to_agent_definition(tmp_path: Path) -> None:
    clients, factory = _capture()
    member_tree = tmp_path / "dev" / "_bundle" / "dev"
    spec = SubagentSpec(
        name="dev",
        description="개발",
        prompt="you dev",
        tools=["Read"],
        bundle=ResourceBundle(slots={"skills": [_skill_item(member_tree, "lint")]}),
    )
    await _run(ClaudeSdkBackend(client_factory=factory, environ={}), {}, subagents=[spec])
    options = clients[0].options
    assert options.plugins == [{"type": "local", "path": str(member_tree)}]
    assert options.skills == []  # 위임자 목록에는 대상 skill을 보이지 않는다
    definition = options.agents["dev"]
    assert definition.skills == ["dev:lint"]
    assert definition.tools is not None
    assert "Skill" in definition.tools


async def test_no_skills_leaves_plugins_and_skills_untouched() -> None:
    clients, factory = _capture()
    await _run(ClaudeSdkBackend(client_factory=factory, environ={}), {})
    options = clients[0].options
    assert options.plugins == []
    assert options.skills is None
    assert "Skill" not in options.tools


# ---------------------------------------------------------------- rules


async def test_rules_default_to_instructions(tmp_path: Path) -> None:
    clients, factory = _capture()
    await _run(
        ClaudeSdkBackend(client_factory=factory, environ={}), {"rules": [_rule_item(tmp_path)]}
    )
    options = clients[0].options
    assert "다음 경로: src/**\n\n검증 먼저" in options.system_prompt
    assert str(tmp_path / "rules" / "api") not in [str(d) for d in options.add_dirs]
    assert "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD" not in options.env


async def test_rules_files_mode_adds_dir_and_env(tmp_path: Path) -> None:
    clients, factory = _capture()
    await _run(
        ClaudeSdkBackend(client_factory=factory, environ={}),
        {"rules": [_rule_item(tmp_path)]},
        agent=_agent(rule_delivery="files"),
    )
    options = clients[0].options
    assert str(tmp_path / "rules" / "api") in [str(d) for d in options.add_dirs]
    assert options.env["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"] == "1"
    assert "검증 먼저" not in (options.system_prompt or "")


# ---------------------------------------------------------------- hooks


async def test_hooks_off_by_default_and_capability_explains() -> None:
    runner = _Runner(HookProcess(exit_code=0))
    clients, factory = _capture(hook_calls=[("PostToolUse", {"hook_event_name": "PostToolUse"})])
    backend = ClaudeSdkBackend(client_factory=factory, environ={}, hook_runner=runner)
    caps = backend.descriptor.capabilities
    assert "hooks" not in caps.resource_slots
    assert caps.slot_notes == {"hooks": HOOKS_DISABLED_NOTE}
    sink, _ = await _run(backend, {"hooks": [HOOK]})
    assert runner.calls == []
    assert "PostToolUse" not in (clients[0].options.hooks or {})
    assert any(
        e.type == "log.warning" and e.payload["details"].get("slot") == "hooks" for e in sink.events
    )


def test_install_option_enables_hooks_slot() -> None:
    backend = ClaudeSdkBackend.from_options(
        {"allow_command_hooks": True}, secrets=SecretResolver([]), environ={}
    )
    caps = backend.descriptor.capabilities
    assert "hooks" in caps.resource_slots
    assert caps.slot_notes is None


async def test_callback_hook_runs_after_guard_with_json_io() -> None:
    out = json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse"}}).encode()
    runner = _Runner(HookProcess(exit_code=0, stdout=out))
    data = {"hook_event_name": "PostToolUse", "tool_name": "Write", "session_id": "s1"}
    clients, factory = _capture(hook_calls=[("PostToolUse", data)])
    backend = ClaudeSdkBackend(
        client_factory=factory,
        environ={"PATH": "/bin", "ANTHROPIC_API_KEY": "nope"},
        allow_command_hooks=True,
        hook_runner=runner,
    )
    sink, _ = await _run(backend, {"hooks": [HOOK]}, limits=Limits(commands=["fmt"]))
    (call,) = runner.calls
    assert call["argv"] == ["fmt", "--check"]
    assert json.loads(call["stdin"]) == data
    assert call["cwd"] == "/proj"
    assert call["env"] == {"PATH": "/bin", "CLAUDE_PROJECT_DIR": "/proj"}  # 키는 정책대로만
    matchers = clients[0].options.hooks["PostToolUse"]
    assert any(m.matcher == "Write" for m in matchers)
    assert {"hookSpecificOutput": {"hookEventName": "PostToolUse"}} in clients[0].hook_outputs
    types = [e.type for e in sink.events if e.type.startswith("hook.")]
    assert types == ["hook.started", "hook.finished"]
    finished = next(e for e in sink.events if e.type == "hook.finished")
    assert finished.payload["exit_code"] == 0
    assert finished.payload["event"] == "PostToolUse"
    assert finished.payload["command_preview"] == "fmt --check"
    assert "duration_ms" in finished.payload


async def test_callback_hook_blocked_by_limits_does_not_run() -> None:
    runner = _Runner(HookProcess(exit_code=0))
    clients, factory = _capture(hook_calls=[("PostToolUse", {"hook_event_name": "PostToolUse"})])
    backend = ClaudeSdkBackend(
        client_factory=factory, environ={}, allow_command_hooks=True, hook_runner=runner
    )
    sink, _ = await _run(backend, {"hooks": [HOOK]}, limits=Limits(commands=["git status"]))
    assert runner.calls == []
    finished = next(e for e in sink.events if e.type == "hook.finished")
    assert finished.payload["error"] == "limits"
    assert clients[0].hook_outputs[-1] == {}


async def test_callback_exit_two_blocks_with_reason() -> None:
    runner = _Runner(HookProcess(exit_code=2, stderr=b"bad edit"))
    clients, factory = _capture(hook_calls=[("PostToolUse", {"hook_event_name": "PostToolUse"})])
    backend = ClaudeSdkBackend(
        client_factory=factory, environ={}, allow_command_hooks=True, hook_runner=runner
    )
    sink, _ = await _run(backend, {"hooks": [HOOK]}, limits=Limits(commands=["*"]))
    assert {"decision": "block", "reason": "bad edit"} in clients[0].hook_outputs
    finished = next(e for e in sink.events if e.type == "hook.finished")
    assert finished.payload["decision"] == "block"
    assert finished.payload["exit_code"] == 2


async def test_settings_delivery_builds_inline_json_and_filters_by_limits() -> None:
    runner = _Runner(HookProcess(exit_code=0))
    clients, factory = _capture()
    backend = ClaudeSdkBackend(
        client_factory=factory, environ={}, allow_command_hooks=True, hook_runner=runner
    )
    other = {**HOOK, "name": "rm", "command": "rm -rf x"}
    sink, _ = await _run(
        backend,
        {"hooks": [HOOK, other]},
        agent=_agent(hook_delivery="settings"),
        limits=Limits(commands=["fmt"]),
    )
    settings = json.loads(clients[0].options.settings)
    (entry,) = settings["hooks"]["PostToolUse"]
    assert entry["matcher"] == "Write"
    assert entry["hooks"] == [{"type": "command", "command": "fmt --check", "timeout": 60.0}]
    assert any(e.type == "log.warning" and "rm" in str(e.payload) for e in sink.events)
    assert runner.calls == []


async def test_subagent_hooks_are_merged_into_session_with_warning() -> None:
    runner = _Runner(HookProcess(exit_code=0))
    clients, factory = _capture()
    backend = ClaudeSdkBackend(
        client_factory=factory, environ={}, allow_command_hooks=True, hook_runner=runner
    )
    spec = SubagentSpec(
        name="dev", description="d", prompt="p", bundle=ResourceBundle(slots={"hooks": [HOOK]})
    )
    sink, _ = await _run(backend, {}, subagents=[spec], limits=Limits(commands=["fmt"]))
    assert "PostToolUse" in clients[0].options.hooks
    assert any(
        e.type == "log.warning" and e.payload["details"].get("slot") == "hooks" for e in sink.events
    )


async def test_default_subprocess_runner_runs_without_shell(tmp_path: Path) -> None:
    script = "import sys, json; d = json.load(sys.stdin); print(json.dumps({'got': d['x']}))"
    done = await subprocess_runner(
        [sys.executable, "-c", script], stdin=b'{"x": 1}', cwd=str(tmp_path), env={}, timeout=30
    )
    assert done.exit_code == 0
    assert json.loads(done.stdout) == {"got": 1}
    slow = await subprocess_runner(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        stdin=b"",
        cwd=str(tmp_path),
        env={},
        timeout=0.2,
    )
    assert slow.timed_out
    assert slow.exit_code is None


def test_hook_settings_json_none_when_all_filtered() -> None:
    guard = ToolGuard(commands=[], directories=None)
    text, warnings = hook_settings_json(
        [HookSpec(name="a", event="Stop", command="x")], guard=guard, default_timeout=5
    )
    assert text is None
    assert len(warnings) == 1


async def test_command_hook_masks_secret_in_preview() -> None:
    sink = ValidatingSink()
    callback = command_hook(
        HookSpec(name="a", event="Stop", command="notify SECRETVALUE"),
        guard=ToolGuard(commands=["*"], directories=None),
        runner=_Runner(HookProcess(exit_code=0)),
        sink=sink,
        mask=lambda t: t.replace("SECRETVALUE", "***"),
        env={},
        cwd=None,
    )
    assert await callback({"hook_event_name": "Stop"}, None, None) == {}
    assert "SECRETVALUE" not in json.dumps([e.payload for e in sink.events])


# ---------------------------------------------------------------- 사용자 폴더 무변경


@pytest.mark.parametrize("delivery", ["callback", "settings"])
async def test_backend_writes_nothing_in_project_or_home(tmp_path: Path, delivery: str) -> None:
    project, home = tmp_path / "project", tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    project.mkdir()
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    tree = tmp_path / "runs" / "r" / "lead" / "_bundle" / "lead"
    clients, factory = _capture(hook_calls=[("PostToolUse", {"hook_event_name": "PostToolUse"})])
    backend = ClaudeSdkBackend(
        client_factory=factory,
        environ={"HOME": str(home)},
        allow_command_hooks=True,
        hook_runner=_Runner(HookProcess(exit_code=0)),
    )
    await _run(
        backend,
        {
            "skills": [_skill_item(tree, "s")],
            "rules": [_rule_item(tree)],
            "hooks": [HOOK],
        },
        agent=_agent(rule_delivery="files", hook_delivery=delivery),
        cwd=str(project),
        limits=Limits(commands=["fmt"]),
    )
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before
    assert (home / ".claude" / "settings.json").read_text(encoding="utf-8") == "{}"
    assert clients[0].options.setting_sources == ["project"]
