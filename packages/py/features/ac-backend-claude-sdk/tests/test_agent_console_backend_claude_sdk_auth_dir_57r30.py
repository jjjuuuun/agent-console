"""5.7R.30·5.7R.30b: 구독 로그인 자격은 앱 workspace 한 곳(앱 전용 ``CLAUDE_CONFIG_DIR``)에 둔다.

- 앱 하나에 로그인 하나: 경로 해석은 ``resolve_auth_dir`` 한 곳(기본 ``<workspace>/.state/claude``,
  설정으로 바꿈). 프로젝트(작업) 폴더에는 아무것도 쓰지 않는다.
- 상태 점검은 이 폴더의 로그인 파일만 본다(빈 HOME에 ``~/.claude``가 있어도 읽지 않음).
- 실행(SDK)·연결 테스트·로그인 PTY가 같은 폴더를 ``CLAUDE_CONFIG_DIR``로 받는다.
- 폴더 700·파일 600, workspace ``.gitignore``에 ``.state/``(없을 때만).
실제 CLI·로그인·SDK 호출 없음(가짜 클라이언트·FakePty·스텁 CLI).
"""

from __future__ import annotations

import asyncio
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, SystemMessage

from agent_console_backend_claude_sdk import (
    CLI_LOGIN_METHOD_ID,
    ClaudeSdkAuthDirOptions,
    ClaudeSdkBackend,
    ClaudeSdkErrorCodes,
    PtySupport,
    ReadinessStates,
    ensure_gitignore_entry,
    gitignore_entry_for,
    prepare_auth_dir,
    resolve_auth_dir,
    secure_auth_dir,
)
from agent_console_backend_claude_sdk.testing import FakeSdkClient, ValidatingSink
from agent_console_contracts import Agent, BackendLoginSession, ErrorCodes
from agent_console_pty_session import FakePty
from agent_console_runtime import (
    AgentRequest,
    BackendCheckContext,
    BackendHostContext,
    BackendLoginContext,
    BackendLoginService,
    CancelToken,
    LoginRefusedError,
    SecretResolver,
)

STUB = str(Path(__file__).with_name("claude_cli_stub.py"))
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX 권한")


@pytest.fixture(autouse=True)
def _no_real_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """앱 workspace(앱 데이터 폴더)."""
    folder = tmp_path / "app-data"
    folder.mkdir()
    return folder


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """등록된 프로젝트(작업) 폴더 — 앱은 여기에 아무것도 쓰지 않는다."""
    folder = tmp_path / "project"
    folder.mkdir()
    return folder


def _untouched(project: Path) -> None:
    assert sorted(p.name for p in project.iterdir()) == []


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """빈 HOME에 실제 같은 ~/.claude 로그인 파일을 둔다(읽으면 안 된다)."""
    folder = tmp_path / "home"
    (folder / ".claude").mkdir(parents=True)
    (folder / ".claude" / ".credentials.json").write_text('{"home": true}', encoding="utf-8")
    return folder


def _environ(home: Path) -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", ""), "HOME": str(home)}


def _ctx() -> BackendCheckContext:
    return BackendCheckContext(backend_id="claude-agent-sdk", clock=lambda: 1.0)


def _cmd(scenario: str, verb: str) -> list[str]:
    return [sys.executable, STUB, scenario, "auth", verb]


def _backend(workspace: Path, home: Path, **kw: Any) -> ClaudeSdkBackend:
    kw.setdefault("pty_support", PtySupport(True))
    return ClaudeSdkBackend(
        environ=_environ(home),
        cli_locator=lambda _p: "/stub/claude",
        workspace=workspace,
        **kw,
    )


def _auth_dir(workspace: Path) -> Path:
    return workspace / ".state" / "claude"


# ---------------------------------------------------------------- 경로 해석(한 곳)


def test_resolve_default_relative_to_workspace(workspace: Path) -> None:
    loc = resolve_auth_dir(ClaudeSdkAuthDirOptions(), workspace=workspace, environ={})
    assert loc is not None
    assert loc.path == _auth_dir(workspace)
    assert loc.display == ".state/claude"
    assert loc.env() == {"CLAUDE_CONFIG_DIR": str(_auth_dir(workspace))}
    assert loc.login_files == (_auth_dir(workspace) / ".credentials.json",)


def test_resolve_is_configurable(workspace: Path, tmp_path: Path) -> None:
    opts = ClaudeSdkAuthDirOptions(config_dir="secrets/cc", env_var="MY_DIR")
    loc = resolve_auth_dir(opts, workspace=workspace, environ={})
    assert loc is not None
    assert (loc.path, loc.display, loc.env_var) == (
        workspace / "secrets" / "cc",
        "secrets/cc",
        "MY_DIR",
    )
    outside = ClaudeSdkAuthDirOptions(config_dir="${X}/cc")
    loc = resolve_auth_dir(outside, workspace=workspace, environ={"X": str(tmp_path / "o")})
    assert loc is not None
    assert loc.display == str(tmp_path / "o" / "cc")  # workspace 밖은 절대 경로
    assert gitignore_entry_for(loc, outside) is None  # workspace 밖이면 .gitignore를 건드리지 않음
    assert (
        resolve_auth_dir(ClaudeSdkAuthDirOptions(config_dir=None), workspace=workspace, environ={})
        is None
    )
    assert resolve_auth_dir(ClaudeSdkAuthDirOptions(), workspace=None, environ={}) is None


def test_from_options_uses_host_workspace(workspace: Path) -> None:
    b = ClaudeSdkBackend.from_options(
        {"auth_dir": {"config_dir": "x/claude"}},
        secrets=SecretResolver([]),
        environ={},
        host=BackendHostContext(workspace_dir=workspace),
    )
    assert b.auth_dir_location is not None
    assert b.auth_dir_location.path == workspace / "x" / "claude"
    b = ClaudeSdkBackend.from_options({}, secrets=SecretResolver([]), environ={})
    assert b.auth_dir_location is None  # 단독 사용(workspace 모름) — 앱 전용 폴더 없음
    with pytest.raises(ValueError, match="auth_dir"):
        ClaudeSdkBackend.from_options(
            {"auth_dir": {"nope": 1}}, secrets=SecretResolver([]), environ={}
        )


# ---------------------------------------------------------------- .gitignore


def test_gitignore_created_when_missing(workspace: Path) -> None:
    assert ensure_gitignore_entry(workspace, ".state/") is True
    assert (workspace / ".gitignore").read_text(encoding="utf-8") == ".state/\n"
    assert ensure_gitignore_entry(workspace, ".state/") is False


def test_gitignore_user_file_gets_one_line(workspace: Path) -> None:
    (workspace / ".gitignore").write_text("node_modules/\n*.log", encoding="utf-8")
    assert ensure_gitignore_entry(workspace, ".state/") is True
    assert (workspace / ".gitignore").read_text(encoding="utf-8") == (
        "node_modules/\n*.log\n.state/\n"
    )


@pytest.mark.parametrize("line", [".state", "/.state/", "  .state/  "])
def test_gitignore_existing_variants_untouched(workspace: Path, line: str) -> None:
    text = f"dist/\n{line}\n"
    (workspace / ".gitignore").write_text(text, encoding="utf-8")
    assert ensure_gitignore_entry(workspace, ".state/") is False
    assert (workspace / ".gitignore").read_text(encoding="utf-8") == text


# ---------------------------------------------------------------- 준비·권한


@posix_only
def test_prepare_creates_private_folder(workspace: Path) -> None:
    opts = ClaudeSdkAuthDirOptions()
    loc = resolve_auth_dir(opts, workspace=workspace, environ={})
    assert loc is not None
    report = prepare_auth_dir(loc, opts)
    assert report.created is True
    assert report.gitignore_added is True
    assert stat.S_IMODE(loc.path.stat().st_mode) == 0o700
    assert ".state/" in (workspace / ".gitignore").read_text(encoding="utf-8")
    again = prepare_auth_dir(loc, opts)
    assert (again.created, again.gitignore_added, again.permissions.ok) == (False, False, True)


@posix_only
def test_secure_tightens_loose_modes(workspace: Path) -> None:
    opts = ClaudeSdkAuthDirOptions()
    loc = resolve_auth_dir(opts, workspace=workspace, environ={})
    assert loc is not None
    loc.path.mkdir(parents=True)
    os.chmod(loc.path, 0o755)
    creds = loc.path / ".credentials.json"
    creds.write_text("{}", encoding="utf-8")
    os.chmod(creds, 0o644)
    report = secure_auth_dir(loc, opts)
    assert (report.checked, report.ok) == (True, True)
    assert stat.S_IMODE(loc.path.stat().st_mode) == 0o700
    assert stat.S_IMODE(creds.stat().st_mode) == 0o600


@posix_only
async def test_permission_problem_is_reported(
    workspace: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """권한을 지원하지 않는 파일 시스템: 상태 점검이 알린다(값 없음)."""
    loc_dir = _auth_dir(workspace)
    loc_dir.mkdir(parents=True)
    os.chmod(loc_dir, 0o755)
    (loc_dir / ".credentials.json").write_text("{}", encoding="utf-8")
    os.chmod(loc_dir / ".credentials.json", 0o644)
    opts = ClaudeSdkAuthDirOptions()
    loc = resolve_auth_dir(opts, workspace=workspace, environ={})
    assert loc is not None
    report = secure_auth_dir(loc, opts, chmod=lambda _p, _m: None)  # 좁혀지지 않는 파일 시스템
    assert report.ok is False
    assert set(report.loose) == {".", ".credentials.json"}

    import agent_console_backend_claude_sdk._backend as backend_mod

    monkeypatch.setattr(
        backend_mod,
        "secure_auth_dir",
        lambda loc, o: secure_auth_dir(loc, o, chmod=lambda _p, _m: None),
    )
    r = await _backend(workspace, home).status(_ctx())
    check = next(c for c in r.checks if c.id == "auth_dir_permissions")
    assert check.ok is False
    assert "좁히지 못" in r.detail
    assert r.state == ReadinessStates.SUBSCRIPTION_READY


async def test_unpreparable_folder_fails_run_and_login(workspace: Path, home: Path) -> None:
    (workspace / ".state").write_text("파일이라 폴더를 만들 수 없음", encoding="utf-8")
    clients: list[FakeSdkClient] = []
    b = _backend(workspace, home, client_factory=lambda o: clients.append(FakeSdkClient(o, [])))
    req = AgentRequest(agent=_agent(), prompt="p", cwd=str(workspace))
    result = await b.run(req, ValidatingSink(), CancelToken())
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == ClaudeSdkErrorCodes.AUTH_DIR_UNAVAILABLE
    assert clients == []  # SDK를 부르지 않는다
    b = _backend(workspace, home, pty_spawner=FakePty().spawn)
    with pytest.raises(LoginRefusedError) as info:
        await b.start_login(BackendLoginContext("claude-agent-sdk"), CLI_LOGIN_METHOD_ID)
    assert info.value.code == ErrorCodes.BACKEND_LOGIN_UNSUPPORTED


# ---------------------------------------------------------------- 상태 점검


async def test_status_login_required_when_folder_empty(workspace: Path, home: Path) -> None:
    seen: list[str] = []

    def exists(path: str) -> bool:
        seen.append(path)
        return os.path.exists(path)

    b = _backend(workspace, home, path_exists=exists)
    r = await b.status(_ctx())
    assert r.state == ReadinessStates.SUBSCRIPTION_LOGIN_REQUIRED
    assert r.short_summary == "로그인 필요"
    assert ".state/claude" in r.detail
    assert [(a.kind, a.primary) for a in r.actions] == [("login", True)]
    assert next(c for c in r.checks if c.id == "auth_dir").note == ".state/claude"
    # 빈 HOME의 ~/.claude 로그인 파일은 보지도 않는다.
    assert seen == [str(_auth_dir(workspace) / ".credentials.json")]
    assert not any(str(home) in p for p in seen)
    # 정적 점검은 폴더·.gitignore를 만들지 않는다.
    assert not (workspace / ".state").exists()
    assert not (workspace / ".gitignore").exists()


async def test_status_ready_when_folder_has_login(workspace: Path, home: Path) -> None:
    _auth_dir(workspace).mkdir(parents=True)
    (_auth_dir(workspace) / ".credentials.json").write_text('{"secret-value": 1}', encoding="utf-8")
    r = await _backend(workspace, home).status(_ctx())
    assert r.state == ReadinessStates.SUBSCRIPTION_READY
    assert r.summary.startswith("구독 준비됨")
    assert "secret-value" not in r.model_dump_json()  # 내용은 읽지도 내지도 않는다
    assert [(a.kind, a.primary) for a in r.actions] == [("login", False), ("logout", False)]


async def test_server_env_config_dir_is_ignored(
    workspace: Path, home: Path, tmp_path: Path
) -> None:
    """서버 환경의 CLAUDE_CONFIG_DIR(사용자 폴더)에 로그인이 있어도 앱 폴더만 본다."""
    other = tmp_path / "user-cfg"
    other.mkdir()
    (other / ".credentials.json").write_text("{}", encoding="utf-8")
    b = ClaudeSdkBackend(
        environ={**_environ(home), "CLAUDE_CONFIG_DIR": str(other)},
        cli_locator=lambda _p: "/stub/claude",
        workspace=workspace,
        pty_support=PtySupport(True),
    )
    assert (await b.status(_ctx())).state == ReadinessStates.SUBSCRIPTION_LOGIN_REQUIRED


# ---------------------------------------------------------------- 실행·연결 테스트 환경


def _agent() -> Agent:
    return Agent(id="a", name="A", model="m", backend="claude-agent-sdk", backend_options={})


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


async def test_run_gets_workspace_config_dir(workspace: Path, project: Path, home: Path) -> None:
    clients: list[FakeSdkClient] = []

    def factory(options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, _script())
        clients.append(client)
        return client

    b = _backend(workspace, home, client_factory=factory)
    agent = Agent(
        id="a",
        name="A",
        model="m",
        backend="claude-agent-sdk",
        backend_options={"env": {"CLAUDE_CONFIG_DIR": "/elsewhere"}},
    )
    sink = ValidatingSink()
    result = await b.run(
        AgentRequest(agent=agent, prompt="p", cwd=str(project)), sink, CancelToken()
    )
    assert result.status == "succeeded", result.error
    env = clients[0].options.env
    assert env["CLAUDE_CONFIG_DIR"] == str(_auth_dir(workspace))
    assert _auth_dir(workspace).is_dir()
    assert ".state/" in (workspace / ".gitignore").read_text(encoding="utf-8")
    warned = [e for e in sink.events if e.type == "log.warning"]
    assert any("자격 폴더" in str(e.payload) for e in warned)
    probe = b._probe_options("/stub/claude", str(project))
    assert probe.env["CLAUDE_CONFIG_DIR"] == str(_auth_dir(workspace))
    _untouched(project)  # 작업 폴더에는 자격 폴더도 .gitignore도 쓰지 않는다


async def test_standalone_backend_keeps_old_env(home: Path) -> None:
    """앱 workspace를 모르면(단독 사용) 앱 전용 폴더를 만들지 않는다."""
    clients: list[FakeSdkClient] = []

    def factory(options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, _script())
        clients.append(client)
        return client

    b = ClaudeSdkBackend(client_factory=factory, environ=_environ(home))
    result = await b.run(
        AgentRequest(agent=_agent(), prompt="p", cwd="/x"), ValidatingSink(), CancelToken()
    )
    assert result.status == "succeeded"
    assert "CLAUDE_CONFIG_DIR" not in clients[0].options.env


# ---------------------------------------------------------------- 로그인(FakePty)


async def _until(
    service: BackendLoginService, sid: str, pred: Any, timeout: float = 15.0
) -> BackendLoginSession:
    deadline = time.monotonic() + timeout
    while True:
        view = service.get(sid)
        if pred(view):
            return view
        if time.monotonic() > deadline:
            raise AssertionError(f"시간 초과: {view.phase}")
        await asyncio.sleep(0.05)


async def test_fake_pty_login_writes_into_workspace_folder(
    workspace: Path, project: Path, home: Path
) -> None:
    fake = FakePty(output="https://claude.ai/oauth/authorize?x=1\r\nPaste code here > ")

    def script(pty: FakePty, text: str) -> None:
        if text == "\r" and pty.inputs.count("\r") == 1:
            folder = Path(pty.spawns[0].env["CLAUDE_CONFIG_DIR"])  # type: ignore[index]
            (folder / ".credentials.json").write_text("{}", encoding="utf-8")
            pty.emit("Login successful\r\n")
        elif text == "\r":
            pty.exit(0)

    fake._on_input = script
    b = _backend(
        workspace,
        home,
        pty_spawner=fake.spawn,
        login={
            "status_command": _cmd("code", "status"),
            "logout_command": _cmd("code", "logout"),
            "exit_wait_s": 3.0,
            "terminate_grace_s": 0.5,
        },
    )
    method = b.descriptor.login_methods[0]
    assert method.writes[0].endswith(".state/claude/.credentials.json")
    assert not any(str(home) in line for line in method.writes)
    assert (await b.status(_ctx())).state == ReadinessStates.SUBSCRIPTION_LOGIN_REQUIRED

    service = BackendLoginService(lambda: {b.descriptor.id: b}, tick_s=0.05)
    sid = (await service.start(b.descriptor.id)).session_id
    await _until(service, sid, lambda v: v.needs_code)
    env = fake.spawns[0].env or {}
    assert env["CLAUDE_CONFIG_DIR"] == str(_auth_dir(workspace))
    assert stat.S_IMODE(_auth_dir(workspace).stat().st_mode) & 0o077 == 0 or os.name != "posix"
    await service.send_input(sid, text="abc")
    final = await _until(service, sid, lambda v: v.phase in {"succeeded", "failed"})
    assert final.phase == "succeeded", final
    assert (_auth_dir(workspace) / ".credentials.json").exists()
    assert (home / ".claude" / ".credentials.json").read_text(encoding="utf-8") == '{"home": true}'
    _untouched(project)
    assert (await b.status(_ctx())).state == ReadinessStates.SUBSCRIPTION_READY
    await service.aclose()


# ---------------------------------------------------------------- 5.7R.30b 앱 하나에 로그인 하나


def test_credential_dir_personal_and_person_template(workspace: Path) -> None:
    """개인 모드는 person_id=None 하나. 사람별 틀({person})이 주어지면 사람마다 다른 폴더."""
    b = _backend(workspace, Path("/nonexistent-home"))
    assert b.credential_dir() == _auth_dir(workspace)
    assert b.credential_dir("alice") == _auth_dir(workspace)  # 틀에 자리가 없으면 같은 폴더
    team = ClaudeSdkBackend(
        environ={},
        workspace=workspace,
        auth_dir={"config_dir": ".state/people/{person}/claude"},
    )
    alice, bob = team.credential_dir("alice"), team.credential_dir("bob")
    assert alice == workspace / ".state" / "people" / "alice" / "claude"
    assert bob == workspace / ".state" / "people" / "bob" / "claude"
    assert team.credential_dir() is None  # 틀에 사람 자리가 있는데 사람을 모르면 풀지 않는다
    for bad in ("../x", "a/b", "", ".."):
        with pytest.raises(ValueError, match="person_id"):
            team.credential_dir(bad)


async def test_projects_a_and_b_share_one_credential_dir(workspace: Path, tmp_path: Path) -> None:
    """다른 작업 폴더(프로젝트 A·B) 실행이 같은 <workspace>/.state/claude를 쓰고, 프로젝트 폴더에는
    .agent-console/·.gitignore가 생기지 않는다. HOME은 존재하지 않는 폴더(~/.claude를 읽을 수
    없음)."""
    projects = [tmp_path / "a", tmp_path / "b"]
    for folder in projects:
        folder.mkdir()
    clients: list[FakeSdkClient] = []

    def factory(options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, _script())
        clients.append(client)
        return client

    seen: list[str] = []

    def exists(path: str) -> bool:
        seen.append(path)
        return os.path.exists(path)

    b = _backend(workspace, tmp_path / "no-home", client_factory=factory, path_exists=exists)
    for folder in projects:
        result = await b.run(
            AgentRequest(agent=_agent(), prompt="p", cwd=str(folder)),
            ValidatingSink(),
            CancelToken(),
        )
        assert result.status == "succeeded", result.error
    assert {c.options.env["CLAUDE_CONFIG_DIR"] for c in clients} == {str(_auth_dir(workspace))}
    await b.status(_ctx())
    assert seen
    assert all(p.startswith(str(workspace)) for p in seen)
    for folder in projects:
        _untouched(folder)
