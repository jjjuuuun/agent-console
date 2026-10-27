"""Claude 구독 로그인(``cli-login``) 설정·부품(ux-overhaul §15.9, F14, 5.2R.82).

``claude auth login``을 PTY 하위 프로세스로 띄워 앱 화면으로 중계하는 로그인 방법의 **데이터**와
PTY 없이 쓸 수 있는 부품을 둔다. 드라이버(PTY 사용)는 ``_login_driver``에 있고 선택 추가 기능
``login``(``agent-console-pty-session``)이 있을 때만 불러온다.

- ``ClaudeSdkLoginOptions``: 설치자 설정 ``login``(실행 인자, 화면 글자 규칙, 허용 URL 호스트, 하위
  프로세스 환경, 쓰기 범위 안내, 시간, 문구). 전부 데이터다.
- ``ClaudeSdkLoginRules``: 화면 글자 규칙(정규식 목록). 저장 전에
  ``agent-console-secret-rules``의 안전
  정규식 검사를 거친다(``safe_rule_compile``).
- 부품: ``login_env``(하위 프로세스 환경), ``allowed_open_url``(https + 허용 호스트),
  ``resolve_writes``(쓰기 범위 경로), ``run_command``·``parse_auth_method``·``verify_login``
  (``status_command`` 종료 코드 + ``authMethod`` 판정).

이 모듈은 로그인 자격(토큰)을 읽거나 저장하지 않는다. 로그인 결과는 Claude Code CLI가 자기 위치
(``CLAUDE_CONFIG_DIR`` 또는 ``~/.claude``)에 쓴다.
"""

from __future__ import annotations

import asyncio
import contextlib
import fnmatch
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_console_secret_rules import check_extra_rules

from ._env import EnvPolicy
from ._readiness import FixLink, expand_path

CLI_LOGIN_METHOD_ID = "cli-login"
"""로그인 방법 id(디스크립터 ``login_methods[].id``)."""

DEFAULT_LOGIN_RULES: Mapping[str, tuple[str, ...]] = {
    "open_url": (r"https://\S+/oauth/authorize\S*",),
    "needs_code": (r"(?i)paste code",),
    "success": (r"(?i)login successful",),
    "failure": (r"(?i)(error|failed)",),
}
"""화면 글자 규칙 기본값(§15.9-4). 규칙이 깨져도 최종 판정은 ``status_command``라 거짓 성공이
없다."""

DEFAULT_ALLOWED_URL_HOSTS: tuple[str, ...] = (
    "claude.ai",
    "claude.com",
    "console.anthropic.com",
    "platform.claude.com",
)
"""``open_url``로 넘길 호스트(https만, 하위 도메인 포함)."""

DEFAULT_LOGIN_ENV_CLEAR: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
)
"""하위 프로세스에 늘 빈 값으로 넘기는 변수(키·토큰이 로그인 판정에 끼어들지 않게)."""

DEFAULT_LOGIN_ENV_INHERIT: tuple[str, ...] = (
    "CLAUDE_CONFIG_DIR",
    "BROWSER",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XDG_*",
    "WSL_DISTRO_NAME",
    "WSL_INTEROP",
    "WSLENV",
)
"""환경 정책 허용 목록에 더해 물려줄 변수(로그인 위치·브라우저 열기에 필요, ``*`` 글롭)."""

DEFAULT_LOGIN_ENV: Mapping[str, str] = {"TERM": "xterm-256color"}
"""하위 프로세스에 명시로 줄 값(대화형 화면이 터미널 종류를 알아야 한다)."""

DEFAULT_LOGIN_WRITES: tuple[str, ...] = (
    "${CLAUDE_CONFIG_DIR}/.credentials.json",
    "~/.claude/.credentials.json",
)
"""시작 확인 창에 보일 쓰기 범위 후보(앞에서부터 처음 풀리는 하나만 보인다)."""


class LoginReasonCodes:
    """이 방법이 내는 실패 사유(``BackendLoginSession.reason``, 열린 어휘)."""

    CLI_MISSING = "cli_missing"
    """Claude Code 실행 파일이 없다."""
    PTY_UNAVAILABLE = "pty_unavailable"
    """이 환경에서 PTY를 쓸 수 없다(``details.pty_reason``)."""
    EXITED = "exited"
    """로그인 과정이 성공 문구 없이 0이 아닌 코드로 끝났고 확인도 실패했다."""
    VERIFY_FAILED = "verify_failed"
    """``status_command``가 로그인됨을 확인하지 못했다(종료 코드·``authMethod``)."""
    START_FAILED = "start_failed"
    """하위 프로세스를 띄우지 못했다(``details.error`` = 예외 형식 이름)."""
    LOGOUT_FAILED = "logout_failed"
    """``logout_command``가 0이 아닌 코드로 끝났다."""
    TIMEOUT = "timeout"
    """로그아웃이 시간 안에 끝나지 않았다."""


def safe_rule_compile(pattern: str) -> re.Pattern[str]:
    """안전 정규식 검사(``agent-console-secret-rules`` → ``ac-safe-regex``)를 거쳐 컴파일한다.

    ``agent_console_pty_session.ExpectRules(compile=...)``에 넘기는 컴파일 함수다.

    Raises:
        ValueError: 위험하거나 잘못된 정규식(문장에 패턴 원문은 없다).

    Example:
        >>> safe_rule_compile(r"(?i)paste code").pattern
        '(?i)paste code'
        >>> safe_rule_compile(r"(a+)+$")  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
        ValueError: 위험한 정규식
    """
    problems = check_extra_rules(extra_value_patterns=[pattern])
    if problems:
        raise ValueError(problems[0].message)
    return re.compile(pattern)


class ClaudeSdkLoginRules(BaseModel):
    """화면 글자 규칙(신호 이름 → 정규식 목록). 한 줄 안에서 찾는다.

    - ``open_url``: 브라우저에서 열 주소(맞은 글자 전체, 허용 호스트만 넘긴다).
    - ``needs_code``: 코드 붙여 넣기를 기다린다.
    - ``success``: 성공 문구(뒤이어 ``on_success_keys``를 보낸다). 판정은 ``status_command``.
    - ``failure``: 오류 문구(안내만 바꾼다, 판정에 쓰지 않는다).
    """

    model_config = ConfigDict(extra="forbid")

    open_url: list[str] = Field(
        default_factory=lambda: list(DEFAULT_LOGIN_RULES["open_url"]),
        description="브라우저 로그인 주소를 찾는 정규식(맞은 글자 전체가 주소).",
    )
    needs_code: list[str] = Field(
        default_factory=lambda: list(DEFAULT_LOGIN_RULES["needs_code"]),
        description="코드 붙여 넣기 요청을 알아보는 정규식.",
    )
    success: list[str] = Field(
        default_factory=lambda: list(DEFAULT_LOGIN_RULES["success"]),
        description="성공 문구를 알아보는 정규식(최종 판정은 status_command).",
    )
    failure: list[str] = Field(
        default_factory=lambda: list(DEFAULT_LOGIN_RULES["failure"]),
        description="오류 문구를 알아보는 정규식(안내 문구만 바꾼다).",
    )

    @field_validator("open_url", "needs_code", "success", "failure")
    @classmethod
    def _safe(cls, patterns: list[str]) -> list[str]:
        problems = check_extra_rules(extra_value_patterns=patterns)
        if problems:
            raise ValueError("; ".join(f"[{p.index}] {p.message}" for p in problems))
        return patterns

    def named(self) -> list[tuple[str, str]]:
        """``(신호 이름, 정규식)`` 목록(규칙 순서)."""
        out: list[tuple[str, str]] = []
        for name in ("open_url", "needs_code", "success", "failure"):
            out.extend((name, pattern) for pattern in getattr(self, name))
        return out


class PtySize(BaseModel):
    """PTY 크기. 긴 URL이 하위 프로세스 쪽에서 줄바꿈되지 않게 넓게 둔다."""

    model_config = ConfigDict(extra="forbid")

    cols: int = Field(default=400, ge=40, le=4000, description="열 수.")
    rows: int = Field(default=40, ge=5, le=500, description="줄 수.")


class ClaudeSdkLoginTexts(BaseModel):
    """로그인 방법·단계·사유 문구(데이터). ``{name}`` = 변수 이름, ``{path}`` = 경로."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="구독으로 로그인", min_length=1)
    relogin_label: str = Field(default="다시 로그인", min_length=1)
    logout_label: str = Field(default="로그아웃(연결 해제)", min_length=1)
    description: str = (
        "Claude Code의 구독 로그인(claude auth login)을 앱 화면에서 진행합니다. 로그인 정보는 "
        "Claude Code가 자기 위치에 저장하고 앱은 보관하지 않습니다."
    )
    notice: str = (
        "본인 구독, 본인 책임: Anthropic 문서상 Agent SDK 기반 앱에는 API 키 사용이 안내되며, "
        "구독 로그인 사용은 본인 책임입니다. 로그아웃은 상태 카드의 … 메뉴 또는 터미널에서 "
        "claude auth logout으로 합니다."
    )
    writes_credentials: str = "Claude Code 로그인 정보: {path}"
    writes_shared: str = "터미널의 Claude Code도 같은 로그인을 씁니다"

    starting: str = "Claude Code 로그인을 시작하고 있습니다."
    waiting_browser: str = (
        "브라우저에서 로그인하세요. 창이 열리지 않았으면 [로그인 페이지 열기]를 누르세요."
    )
    waiting_code: str = "브라우저에 코드가 보이면 붙여 넣으세요."
    code_label: str = "인증 코드"
    code_sent: str = "코드를 보냈습니다. 확인을 기다리고 있습니다."
    failure_seen: str = "Claude Code가 오류를 알렸습니다. 아래 CLI 화면을 확인하고 다시 시도하세요."
    verifying: str = "로그인을 확인하고 있습니다."
    succeeded: str = "로그인됨 — Claude 구독"
    failed_cli_missing: str = "Claude Code 실행 파일을 찾지 못했습니다."
    failed_pty_unavailable: str = "이 환경에서는 앱 화면 로그인을 쓸 수 없습니다(터미널 연결 불가)."
    failed_exited: str = "로그인이 끝나기 전에 Claude Code가 종료됐습니다."
    failed_verify: str = "로그인을 확인하지 못했습니다. 다시 시도하세요."
    failed_start: str = "로그인을 시작하지 못했습니다."
    warning_env: str = (
        "서버 환경에 {name}이(가) 설정돼 있습니다. 앱 실행에는 쓰지 않지만 터미널의 "
        "Claude Code에서는 "
        "그 값이 이 로그인보다 우선합니다."
    )
    unavailable_detail: str = (
        "앱 화면 로그인을 쓰려면 선택 기능을 설치하세요: "
        "pip install 'agent-console-backend-claude-sdk[login]'. 그 전에는 터미널에서 claude auth "
        "login으로 로그인합니다."
    )

    logout_ok: str = "로그아웃했습니다. 이 PC의 Claude Code 로그인이 지워졌습니다."
    logout_failed: str = "로그아웃하지 못했습니다(종료 코드 {code})."
    logout_timeout: str = "로그아웃이 {seconds:g}초 안에 끝나지 않았습니다."
    logout_cli_missing: str = "Claude Code 실행 파일을 찾지 못해 로그아웃하지 못했습니다."

    fix_cli: FixLink = Field(default_factory=lambda: FixLink(label="실행 파일 경로 설정 보기"))
    fix_settings: FixLink = Field(default_factory=lambda: FixLink(label="설치자 설정 보기"))


class ClaudeSdkLoginOptions(BaseModel):
    """설치자 설정 ``login``(``backends.claude-agent-sdk.login``): 앱 화면 구독 로그인.

    실행 인자는 이 설정에서만 온다(요청으로 바꿀 수 없다). 기본은 켜짐(2026-10-23 사용자 결정).
    ``allow_subscription_auth``가 꺼져 있거나 ``agent-console-pty-session``이 없으면 능력을
    선언하지 않는다.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=True, description="앱 화면 구독 로그인·로그아웃을 제공한다. 끄면 버튼이 없다."
    )
    command: list[str] | None = Field(
        default=None,
        min_length=1,
        description="로그인 실행 인자. 비우면 [Claude Code 실행 파일, auth, login].",
    )
    status_command: list[str] | None = Field(
        default=None,
        min_length=1,
        description="성공 판정 실행 인자(종료 코드 0 + authMethod). 비우면 "
        "[실행 파일, auth, status].",
    )
    logout_command: list[str] | None = Field(
        default=None,
        min_length=1,
        description="로그아웃 실행 인자. 비우면 [실행 파일, auth, logout].",
    )
    success_auth_methods: list[str] = Field(
        default_factory=lambda: ["claude.ai"],
        description="성공으로 볼 authMethod 값. 비우면 종료 코드만 본다. 출력이 JSON이 아니면 "
        "종료 코드만 본다.",
    )
    rules: ClaudeSdkLoginRules = Field(
        default_factory=ClaudeSdkLoginRules, description="화면 글자 규칙(정규식, 안전 검사)."
    )
    allowed_url_hosts: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_URL_HOSTS),
        description="open_url로 넘길 호스트(https만, 하위 도메인 포함).",
    )
    on_success_keys: list[str] = Field(
        default_factory=lambda: ["enter"], description="성공 문구 뒤 자동으로 보낼 키."
    )
    submit_keys: list[str] = Field(
        default_factory=lambda: ["enter"], description="붙여 넣은 코드 뒤에 보낼 키."
    )
    pty_size: PtySize = Field(default_factory=PtySize, description="PTY 크기.")
    cwd: str | None = Field(default=None, description="작업 폴더. 비우면 서버 작업 폴더.")
    env: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_LOGIN_ENV),
        description="하위 프로세스에 명시로 줄 값(비밀이 아닌 값만).",
    )
    env_inherit: list[str] = Field(
        default_factory=lambda: list(DEFAULT_LOGIN_ENV_INHERIT),
        description="환경 정책 허용 목록에 더해 물려줄 변수(* 글롭).",
    )
    env_clear: list[str] = Field(
        default_factory=lambda: list(DEFAULT_LOGIN_ENV_CLEAR),
        description="늘 빈 값으로 넘길 변수(API 키·토큰).",
    )
    writes: list[str] = Field(
        default_factory=lambda: list(DEFAULT_LOGIN_WRITES),
        description="시작 확인 창에 보일 쓰기 경로 후보(처음 풀리는 하나). ~ = 홈, "
        "${이름} = 환경 변수.",
    )
    status_timeout_s: float = Field(default=20.0, gt=0, le=300, description="확인 명령 시간(초).")
    logout_timeout_s: float = Field(default=20.0, gt=0, le=300, description="로그아웃 시간(초).")
    exit_wait_s: float = Field(
        default=10.0, gt=0, le=300, description="성공 문구 뒤 CLI가 끝나기를 기다리는 시간(초)."
    )
    terminate_grace_s: float = Field(
        default=2.0, ge=0, le=60, description="종료 신호 뒤 강제 종료까지 기다리는 시간(초)."
    )
    screen_lines: int = Field(default=40, ge=0, le=500, description="진행에 싣는 화면 줄 수.")
    texts: ClaudeSdkLoginTexts = Field(
        default_factory=ClaudeSdkLoginTexts, description="방법·단계·사유 문구."
    )


# ---------------------------------------------------------------- 부품


def login_env(
    parent: Mapping[str, str], policy: EnvPolicy, options: ClaudeSdkLoginOptions
) -> dict[str, str]:
    """하위 프로세스 환경 전체(PTY는 상속하지 않으므로 이 사전이 전부다).

    정책 허용 목록과 ``env_inherit``에 맞는 부모 값만 물려주고, ``env_clear``는 늘 빈 값,
    ``env``는 명시 값으로 덮는다.

    Example:
        >>> env = login_env(
        ...     {"PATH": "/bin", "ANTHROPIC_API_KEY": "k", "CLAUDE_CONFIG_DIR": "/c", "OTHER": "x"},
        ...     EnvPolicy(),
        ...     ClaudeSdkLoginOptions(),
        ... )
        >>> sorted(env.items())  # doctest: +NORMALIZE_WHITESPACE
        [('ANTHROPIC_API_KEY', ''), ('ANTHROPIC_AUTH_TOKEN', ''), ('CLAUDE_CODE_OAUTH_TOKEN', ''),
         ('CLAUDE_CONFIG_DIR', '/c'), ('PATH', '/bin'), ('TERM', 'xterm-256color')]
    """
    clear = {name.upper() for name in options.env_clear}
    extra = [pattern.upper() for pattern in options.env_inherit]
    out: dict[str, str] = {}
    for key, value in parent.items():
        upper = key.upper()
        if upper in clear:
            continue
        if policy.allows(key) or any(fnmatch.fnmatchcase(upper, p) for p in extra):
            out[key] = value
    out.update(dict.fromkeys(options.env_clear, ""))
    out.update(options.env)
    return out


def env_warnings(parent: Mapping[str, str], options: ClaudeSdkLoginOptions) -> list[str]:
    """``env_clear`` 변수가 서버 환경에 값이 있으면 안내 문장(이름만, 값 없음)."""
    return [
        options.texts.warning_env.format(name=name)
        for name in options.env_clear
        if parent.get(name)
    ]


def allowed_open_url(url: str, hosts: Sequence[str]) -> str | None:
    """https이고 호스트가 허용 목록(또는 그 하위 도메인)이면 ``url``, 아니면 None.

    Example:
        >>> allowed_open_url("https://claude.ai/oauth/authorize?x=1", ["claude.ai"])
        'https://claude.ai/oauth/authorize?x=1'
        >>> allowed_open_url("http://claude.ai/oauth/authorize", ["claude.ai"]) is None
        True
        >>> allowed_open_url("https://evil.example/claude.ai", ["claude.ai"]) is None
        True
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        return None
    for allowed in hosts:
        a = allowed.lower().strip(".")
        if host == a or host.endswith("." + a):
            return url
    return None


def resolve_writes(templates: Sequence[str], environ: Mapping[str, str]) -> str | None:
    """쓰기 범위 후보 중 처음 풀리는 경로(없으면 None)."""
    for template in templates:
        path = expand_path(template, environ)
        if path:
            return path
    return None


def writes_lines(options: ClaudeSdkLoginOptions, environ: Mapping[str, str]) -> list[str]:
    """시작 확인 창의 "이 PC에서 바뀌는 것" 줄."""
    t = options.texts
    path = resolve_writes(options.writes, environ)
    lines = [t.writes_credentials.format(path=path)] if path else []
    if t.writes_shared:
        lines.append(t.writes_shared)
    return lines


@dataclass(frozen=True)
class CommandResult:
    """짧은 명령 실행 결과.

    Attributes:
        exit_code: 종료 코드(시간 초과면 None).
        stdout: 표준 출력(한도 안). 표준 오류는 버린다(로그에 남기지 않는다).
    """

    exit_code: int | None
    stdout: str = ""


async def run_command(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: str | None,
    timeout_s: float,
    max_stdout: int = 65_536,
) -> CommandResult:
    """셸 없이 짧은 명령을 실행한다(입력 없음, 표준 오류 버림, 시간 초과면 강제 종료).

    Raises:
        FileNotFoundError: 실행 파일이 없다.
        OSError: 그 밖의 시작 실패.
    """
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=dict(env),
        cwd=cwd,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout_s)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), 5.0)
        return CommandResult(None)
    return CommandResult(proc.returncode, out[:max_stdout].decode("utf-8", "replace"))


def parse_auth_method(stdout: str) -> str | None:
    """``claude auth status`` 출력(JSON)의 ``authMethod``. JSON이 아니면 None.

    Example:
        >>> parse_auth_method('{"loggedIn": true, "authMethod": "claude.ai"}')
        'claude.ai'
        >>> parse_auth_method("Logged in") is None
        True
    """
    text = stdout.strip()
    start = text.find("{")
    if start < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    value = data.get("authMethod") if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


@dataclass(frozen=True)
class VerifyOutcome:
    """로그인 확인 결과(값 없음)."""

    ok: bool
    details: dict[str, Any] = field(default_factory=dict)


async def verify_login(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: str | None,
    timeout_s: float,
    success_auth_methods: Sequence[str],
) -> VerifyOutcome:
    """``status_command``로 로그인됨을 확인한다.

    종료 코드 0이어야 하고, ``success_auth_methods``가 있고 출력에서 ``authMethod``를 읽었으면 그
    값이 목록에 있어야 한다(출력이 JSON이 아니면 종료 코드만 본다 — CLI 출력 형식 변화에 견딘다).

    Raises:
        FileNotFoundError: 실행 파일이 없다.
    """
    result = await run_command(argv, env=env, cwd=cwd, timeout_s=timeout_s)
    method = parse_auth_method(result.stdout)
    details: dict[str, Any] = {"status_exit_code": result.exit_code}
    if method is not None:
        details["auth_method"] = method
    if result.exit_code is None:
        details["status_timeout"] = True
        return VerifyOutcome(False, details)
    if result.exit_code != 0:
        return VerifyOutcome(False, details)
    if success_auth_methods and method is not None and method not in success_auth_methods:
        return VerifyOutcome(False, details)
    return VerifyOutcome(True, details)


__all__ = [
    "CLI_LOGIN_METHOD_ID",
    "DEFAULT_ALLOWED_URL_HOSTS",
    "DEFAULT_LOGIN_ENV",
    "DEFAULT_LOGIN_ENV_CLEAR",
    "DEFAULT_LOGIN_ENV_INHERIT",
    "DEFAULT_LOGIN_RULES",
    "DEFAULT_LOGIN_WRITES",
    "ClaudeSdkLoginOptions",
    "ClaudeSdkLoginRules",
    "ClaudeSdkLoginTexts",
    "CommandResult",
    "LoginReasonCodes",
    "PtySize",
    "VerifyOutcome",
    "allowed_open_url",
    "env_warnings",
    "login_env",
    "parse_auth_method",
    "resolve_writes",
    "run_command",
    "safe_rule_compile",
    "verify_login",
    "writes_lines",
]
