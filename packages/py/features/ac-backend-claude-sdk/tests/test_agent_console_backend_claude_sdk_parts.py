"""단독 부품: ToolGuard(실행 범위), RawSanitizer(raw 정제), build_sdk_options, 이름·사용량."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_backend_claude_sdk import (
    ClaudeSdkBackendOptions,
    EnvPolicy,
    RawSanitizer,
    ToolGuard,
    apply_env_policy,
    build_sdk_options,
    guard_from_limits,
    split_mcp_name,
    usage_from_sdk,
)
from agent_console_contracts import Agent, Limits
from agent_console_runtime import REDACTED, AgentRequest


@pytest.mark.parametrize(
    ("commands", "command", "allowed"),
    [
        (None, "ls", False),
        ([], "ls", False),
        (["*"], "rm -rf / && echo", True),
        (["git status"], "git status -s", True),
        (["git status"], "git push", False),
        (["git"], "git push origin main", True),
        (["git"], "git log | head", False),
        (["git"], "git log $(whoami)", False),
        (["git"], "FOO=1 git log", False),
        (["pytest"], "pytest 'unterminated", False),
    ],
)
def test_command_guard(commands: list[str] | None, command: str, allowed: bool) -> None:
    guard = ToolGuard(commands=commands, directories=None)
    assert (guard.check("Bash", {"command": command}) is None) is allowed


def test_command_guard_applies_to_any_tool_with_command_key() -> None:
    guard = ToolGuard(commands=["git"], directories=None)
    assert guard.check("PowerShell", {"command": "del x"}) is not None
    assert guard.check("Read", {"file_path": "x"}) is None


def test_directory_guard(tmp_path: Any) -> None:
    inside = tmp_path / "ws"
    inside.mkdir()
    guard = guard_from_limits(commands=["*"], directories=None, cwd=str(inside))
    assert guard.check("Read", {"file_path": "notes.md"}) is None
    assert guard.check("Read", {"file_path": str(inside / "a" / "b")}) is None
    assert guard.check("Read", {"file_path": "../escape.md"}) is not None
    assert guard.check("Glob", {"path": "/"}) is not None
    other = tmp_path / "shared"
    guard2 = guard_from_limits(
        commands=None, directories=[str(inside), str(other)], cwd=str(inside)
    )
    assert guard2.check("Edit", {"file_path": str(other / "x")}) is None


def test_no_cwd_no_directories_means_no_path_check() -> None:
    guard = guard_from_limits(commands=["*"], directories=None, cwd=None)
    assert guard.check("Read", {"file_path": "/anything"}) is None


def test_sanitizer_masks_keys_values_and_patterns() -> None:
    sanitizer = RawSanitizer(secrets=["hunter2-secret"], redact=lambda v: v)
    raw = sanitizer(
        {
            "headers": {"Authorization": "Bearer abc.def.ghijkl"},
            "api_key": "xyz",
            "usage": {"input_tokens": 3, "output_tokens": 4},
            "text": "pw=hunter2-secret and sk-ant-api03-ABCDEFGHIJ",
            "note": "Bearer abcdefghijkl123",
        }
    )
    assert raw["headers"]["Authorization"] == REDACTED
    assert raw["api_key"] == REDACTED
    assert raw["usage"] == {"input_tokens": 3, "output_tokens": 4}
    assert "hunter2" not in raw["text"]
    assert "sk-ant" not in raw["text"]
    assert "abcdefghijkl123" not in raw["note"]


def test_sanitizer_truncates_large_raw() -> None:
    raw = RawSanitizer(max_chars=50)({"text": "x" * 500})
    assert raw["truncated"] is True
    assert len(raw["preview"]) == 50


def test_build_sdk_options_variants() -> None:
    agent = Agent(id="a", name="A", tools=["Read", "mcp__wiki__search"], system_prompt="sp")
    opts = ClaudeSdkBackendOptions.model_validate(
        {
            "tools": "claude_code",
            "system_prompt_mode": "claude_code_append",
            "setting_sources": [],
            "sdk_options": {"max_thinking_tokens": 100},
        }
    )
    req = AgentRequest(agent=agent, prompt="p", limits=Limits(network="allow"))
    out = build_sdk_options(req, opts, env={}, hooks=None, can_use_tool=None)
    assert out.tools == {"type": "preset", "preset": "claude_code"}
    assert out.system_prompt == {"type": "preset", "preset": "claude_code", "append": "sp"}
    assert out.setting_sources == []
    # 되묻기 grant가 없으면 질문 도구는 금지(1R.30)
    assert out.disallowed_tools == ["AskUserQuestion"]
    assert out.allowed_tools == ["Read", "mcp__wiki__search"]
    assert out.max_thinking_tokens == 100
    assert out.resume is None
    assert out.model is None

    plain = build_sdk_options(
        AgentRequest(agent=Agent(id="b", name="B"), prompt="p"),
        ClaudeSdkBackendOptions(),
        env={},
        hooks=None,
        can_use_tool=None,
    )
    assert plain.tools == []  # 도구를 정하지 않으면 내장 도구 없음(안전한 기본값)
    assert plain.system_prompt is None


def test_split_mcp_name_and_usage() -> None:
    assert split_mcp_name("mcp__wiki__search_pages") == ("wiki", "search_pages")
    assert split_mcp_name("Read") is None
    assert split_mcp_name("mcp__broken") is None
    usage = usage_from_sdk({"input_tokens": 1, "cache_creation_input_tokens": 2, "x": "y"}, 0.5)
    assert usage.input_tokens == 1
    assert usage.cache_creation_tokens == 2
    assert usage.cost_usd == 0.5


@pytest.mark.parametrize(
    "command",
    [
        "git status\nrm -rf /",
        "git status\r\nrm -rf /",
        "git status && rm -rf /",
        "git status; rm -rf /",
        "git status | sh",
        "git status $(rm -rf /)",
        "git status `rm -rf /`",
        "git status > /etc/passwd",
        "git status < /dev/zero",
        "GIT_DIR=/x git status",
        "/usr/bin/git status",
        "./git status",
        "",
        "   ",
    ],
)
def test_command_guard_rejects_bypass_attempts(command: str) -> None:
    guard = ToolGuard(commands=["git status"], directories=None)
    assert guard.check("Bash", {"command": command}) is not None


@pytest.mark.parametrize(
    ("key", "masked"),
    [
        ("GITHUB_TOKEN", True),
        ("AWS_SECRET_ACCESS_KEY", True),
        ("SECRET_TOKEN", True),
        ("access_token", True),
        ("db_password", True),
        ("PRIVATE_KEY", True),
        ("google_credentials", True),
        ("x-api-key", True),
        ("input_tokens", False),
        ("output_tokens", False),
        ("cache_read_input_tokens", False),
        ("total_tokens", False),
        ("tool_use_id", False),
    ],
)
def test_secret_key_pattern(key: str, masked: bool) -> None:
    out = RawSanitizer()({key: "value-1234"})
    assert (out[key] == REDACTED) is masked


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_" + "a" * 36,
        "gho_" + "B" * 36,
        "github_pat_" + "c1" * 20,
        "xoxb-1234567890-abcdef",
        "xoxp-1234567890-abcdef",
        "AKIA" + "ABCDEFGHIJKLMNOP",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----",
    ],
)
def test_secret_value_patterns(secret: str) -> None:
    out = RawSanitizer()({"text": f"before {secret} after"})
    assert secret not in out["text"]
    assert out["text"].startswith("before ")


def test_apply_env_policy() -> None:
    policy = EnvPolicy()
    env = apply_env_policy({"PATH": "/b", "lc_ctype": "C", "SECRET": "s"}, policy, {"K": "v"})
    assert env == {"SECRET": "", "K": "v"}
    assert apply_env_policy({"X": "1"}, EnvPolicy(inherit="all"), {}) == {}
