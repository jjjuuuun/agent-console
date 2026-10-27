"""Claude SDK 백엔드의 준비 상태(정적 점검)와 연결 테스트 재료(ux-overhaul §15.8, 5.2R.68).

이 모듈은 SDK를 부르지 않는다. 백엔드(``ClaudeSdkBackend.status``·``probe``)가 쓰는 부품이다.

- ``ClaudeSdkReadinessOptions``: 설치자 설정 ``readiness``(점검할 인증 방식, CLI 경로, 구독 로그인
  확인 파일, 연결 테스트 프롬프트·모델·CLI 인자, 문구).
- ``assess_readiness``: 인증 해석 결과 → 상태(``ReadinessAssessment``). 값을 읽지 않고 비밀 이름이
  있는지만 묻는다(``has_secret``). 파일은 있는지만 본다.
- ``classify_probe_messages``·``classify_probe_error``: SDK 응답·예외 → 실패 사유(인증·네트워크·
  기타). 시간 초과는 백엔드가 직접 판단한다.
- ``find_claude_cli``: SDK가 쓸 Claude Code 실행 파일 위치(번들 → PATH).

상태 이름(열린 어휘, 화면은 비교하지 않는다): ``ReadinessStates``. 실패 사유: ``ProbeReasonCodes``.
"""

from __future__ import annotations

import dataclasses
import os
import platform
import re
import shutil
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import FixAction, FixTarget, ReadinessCheck
from agent_console_runtime import SECRET_REF_PREFIX, is_secret_ref

from ._options import ClaudeSdkAuth

DEFAULT_READINESS_KEY_REF = "secret://anthropic_api_key"
"""점검할 인증 방식의 기본 API 키 참조(README 권장 설정과 같은 이름). 설치자 설정으로 바꾼다."""

DEFAULT_SUBSCRIPTION_FILES: tuple[str, ...] = (
    "${CLAUDE_CONFIG_DIR}/.credentials.json",
    "~/.claude/.credentials.json",
)
"""구독 로그인 확인 파일 후보(있는지만 본다, 읽지 않음). ``~`` = HOME(없으면 USERPROFILE),
``${이름}`` = 환경 변수(비어 있으면 풀 수 없음). **처음 풀리는 하나만** 본다: Claude Code CLI는
``CLAUDE_CONFIG_DIR``가 있으면 그 폴더만 보고 없을 때만 ``~/.claude``를 보기 때문이다."""

DEFAULT_PROBE_PROMPT = "Reply with the single word OK."
"""연결 테스트 프롬프트(가장 짧은 응답을 바라는 한 줄)."""

DEFAULT_PROBE_EXTRA_ARGS: dict[str, str | None] = {"no-session-persistence": None}
"""연결 테스트 CLI 추가 인자. 기본은 세션 기록을 남기지 않는다(사용자 대화 로그에 섞이지 않게)."""


class ReadinessStates:
    """``BackendReadiness.state`` 값(이 백엔드가 정하는 열린 어휘)."""

    AUTH_READY = "auth_ready"
    AUTH_MISSING = "auth_missing"
    SUBSCRIPTION_DISABLED = "subscription_disabled"
    SUBSCRIPTION_READY = "subscription_ready"
    SUBSCRIPTION_UNVERIFIED = "subscription_unverified"
    """구독 방식이 켜져 있으나 로그인 파일을 찾지 못함(키체인 등 파일 밖에 둔 경우일 수 있다)."""
    SUBSCRIPTION_TOKEN_MISSING = "subscription_token_missing"
    CLI_MISSING = "cli_missing"


class ProbeReasonCodes:
    """``BackendProbeResult.reason`` 값(열린 어휘). 시간 초과는 서비스와 같은 ``timeout``."""

    AUTH_MISSING = "auth_missing"
    """키·토큰이 없어 호출하지 않았다."""
    SUBSCRIPTION_DISABLED = "backend.subscription_auth_disabled"
    """구독 방식이 설치자 설정으로 꺼져 있어 호출하지 않았다."""
    CLI_MISSING = "cli_missing"
    """Claude Code 실행 파일이 없어 호출하지 않았다."""
    AUTH_FAILED = "auth_failed"
    NETWORK = "network"
    TIMEOUT = "timeout"
    ERROR = "error"
    """그 밖의 실패(``details.category`` = ``other``)."""


PROBE_CATEGORIES: Mapping[str, str] = {
    ProbeReasonCodes.AUTH_MISSING: "auth",
    ProbeReasonCodes.SUBSCRIPTION_DISABLED: "auth",
    ProbeReasonCodes.AUTH_FAILED: "auth",
    ProbeReasonCodes.NETWORK: "network",
    ProbeReasonCodes.TIMEOUT: "timeout",
    ProbeReasonCodes.CLI_MISSING: "other",
    ProbeReasonCodes.ERROR: "other",
}
"""실패 사유 → 분류(``auth``·``network``·``timeout``·``other``). ``details.category``에 싣는다."""


class FixLink(BaseModel):
    """해결 버튼 데이터(문구 + 웹 라우트 역할·섹션)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, description="버튼 문구.")
    role: str = Field(default="settings", min_length=1, description="웹 라우트 역할.")
    section: str | None = Field(default="modules", description="화면 안 위치(설정 섹션 id).")

    def action(self) -> FixAction:
        """계약 ``FixAction``으로."""
        return FixAction(label=self.label, target=FixTarget(role=self.role, section=self.section))


class ClaudeSdkReadinessTexts(BaseModel):
    """상태·연결 테스트 문구(데이터). ``{name}`` = 비밀 이름, ``{seconds}`` = 초."""

    model_config = ConfigDict(extra="forbid")

    auth_ready_summary: str = "인증 설정됨 (API 키)"
    auth_ready_short: str = "준비됨"
    auth_missing_summary: str = "키 없음 — API 키가 설정되지 않았습니다"
    auth_missing_short: str = "키 없음"
    auth_missing_detail: str = (
        "비밀 '{name}'을(를) 찾지 못했습니다. 환경 변수나 비밀 저장소에 키를 넣은 뒤 "
        "다시 확인하세요."
    )
    subscription_disabled_summary: str = "구독 방식 꺼짐 — 설치자 설정에서 켜야 합니다"
    subscription_disabled_short: str = "구독 꺼짐"
    subscription_disabled_detail: str = (
        "Anthropic 문서는 Agent SDK 기반 앱에 API 키 사용을 안내합니다. 본인 구독 로그인으로 "
        "쓰려면 설치자 설정에서 구독 방식 허용(allow_subscription_auth)을 켜세요(본인 책임)."
    )
    subscription_ready_summary: str = "구독 방식으로 인증됨 (본인 책임)"
    subscription_ready_short: str = "본인 책임"
    subscription_ready_detail: str = (
        "본인 Claude Code 구독 로그인으로 실행합니다. Anthropic 문서는 Agent SDK 기반 앱에 API 키 "
        "사용을 안내하며, 구독 로그인 사용은 본인 책임입니다."
    )
    subscription_unverified_summary: str = "구독 로그인 정보를 찾지 못함"
    subscription_unverified_short: str = "로그인 확인"
    subscription_unverified_detail: str = (
        "로그인 파일을 찾지 못했습니다. 터미널에서 claude를 실행해 로그인했는지 확인하세요. "
        "운영체제 보관함(키체인 등)에 저장했다면 파일이 없어도 동작할 수 있습니다."
    )
    subscription_token_missing_summary: str = "구독 토큰 없음 — 토큰이 설정되지 않았습니다"
    subscription_token_missing_short: str = "토큰 없음"
    cli_missing_summary: str = "Claude Code 실행 파일 없음"
    cli_missing_short: str = "설치 필요"
    cli_missing_detail: str = (
        "Claude Agent SDK가 쓸 Claude Code 실행 파일을 찾지 못했습니다. Claude Code를 설치하거나 "
        "설치자 설정에서 실행 파일 경로(readiness.cli_path)를 지정하세요."
    )

    check_cli: str = "Claude Code 실행 파일"
    check_mode: str = "인증 방식"
    check_key: str = "API 키"
    check_subscription_allowed: str = "구독 방식 허용(설치자 설정)"
    check_token: str = "구독 토큰"
    check_login_file: str = "구독 로그인 파일"
    note_found: str = "있음"
    note_missing: str = "없음"
    note_secret: str = "비밀 '{name}': {state}"
    note_inline: str = "설정 값에 직접 적힘(비밀 참조를 권장합니다)"
    note_on: str = "켜짐"
    note_off: str = "꺼짐"
    note_files: str = "확인한 파일 {count}개 중 {found}개 있음"
    mode_api_key: str = "API 키"
    mode_subscription: str = "구독 로그인"

    probe_ok: str = "연결됨"
    probe_auth_missing: str = "키가 설정되지 않아 테스트하지 않았습니다."
    probe_subscription_disabled: str = "구독 방식이 꺼져 있어 테스트하지 않았습니다."
    probe_cli_missing: str = "Claude Code 실행 파일을 찾지 못해 테스트하지 않았습니다."
    probe_auth_failed: str = "인증에 실패했습니다. API 키나 로그인 정보를 확인하세요."
    probe_network: str = "Claude에 연결하지 못했습니다. 네트워크 연결을 확인하세요."
    probe_timeout: str = "{seconds:g}초 안에 응답이 없었습니다."
    probe_error: str = "연결 테스트 중 오류가 났습니다."

    fix_key: FixLink = Field(default_factory=lambda: FixLink(label="API 키 넣는 곳 보기"))
    fix_subscription: FixLink = Field(default_factory=lambda: FixLink(label="설치자 설정 보기"))
    fix_cli: FixLink = Field(default_factory=lambda: FixLink(label="실행 파일 경로 설정 보기"))


def _default_auth() -> ClaudeSdkAuth:
    return ClaudeSdkAuth(mode="subscription")


class ClaudeSdkReadinessOptions(BaseModel):
    """설치자 설정 ``readiness``: 상태 점검·연결 테스트가 볼 인증 방식과 테스트 호출 모양."""

    model_config = ConfigDict(extra="forbid")

    auth: ClaudeSdkAuth = Field(
        default_factory=_default_auth,
        description="점검·테스트할 인증 방식(에이전트 설정과 같은 형식). 키·토큰은 "
        "secret://이름으로 적는다. 기본은 구독 로그인(본인 책임). API 키도 선택 가능"
        "({mode: api_key, api_key: secret://anthropic_api_key}).",
    )
    cli_path: str | None = Field(
        default=None,
        description="Claude Code 실행 파일 경로. 비우면 SDK 번들 → PATH의 claude 순으로 찾는다.",
    )
    subscription_files: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SUBSCRIPTION_FILES),
        description="구독 로그인 확인 파일 후보(있는지만 본다). ~ = 홈, ${이름} = 환경 변수. "
        "위에서부터 처음 풀리는 하나만 본다(CLI처럼 CLAUDE_CONFIG_DIR가 있으면 그 폴더만).",
    )
    probe_prompt: str = Field(
        default=DEFAULT_PROBE_PROMPT, min_length=1, description="연결 테스트 프롬프트 한 줄."
    )
    probe_model: str | None = Field(
        default=None, description="연결 테스트 모델 id. 비우면 Claude Code 기본 모델."
    )
    probe_extra_args: dict[str, str | None] = Field(
        default_factory=lambda: dict(DEFAULT_PROBE_EXTRA_ARGS),
        description="연결 테스트 CLI 추가 인자(값 null = 값 없는 플래그). 기본은 세션 기록 끔.",
    )
    texts: ClaudeSdkReadinessTexts = Field(
        default_factory=ClaudeSdkReadinessTexts, description="상태·결과 문구."
    )


type Tone = Literal["ok", "warn", "error", "unknown"]


@dataclass(frozen=True)
class ReadinessAssessment:
    """정적 점검 결과(계약 ``BackendReadiness``의 재료, 값 없음).

    Attributes:
        probe_block: 연결 테스트를 호출 없이 거부할 사유(None = 호출해도 된다).
        probe_block_message: 그때 결과 문장.
    """

    state: str
    tone: Tone
    summary: str
    short_summary: str
    detail: str = ""
    fixes: list[FixAction] = field(default_factory=list)
    checks: list[ReadinessCheck] = field(default_factory=list)
    probe_block: str | None = None
    probe_block_message: str = ""


def secret_name(ref: str) -> str:
    """``secret://이름`` → ``이름``."""
    return ref.removeprefix(SECRET_REF_PREFIX)


def api_key_ref(auth: ClaudeSdkAuth) -> str:
    """API 키 방식에서 볼 키: ``auth.api_key``, 없으면 ``secret://<api_key_env>``."""
    return auth.api_key or SECRET_REF_PREFIX + auth.api_key_env


_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_path(template: str, environ: Mapping[str, str]) -> str | None:
    """``~``·``${이름}``을 주입한 환경으로 푼다. 풀 수 없으면 None."""
    missing = False

    def sub(match: re.Match[str]) -> str:
        nonlocal missing
        value = environ.get(match.group(1))
        if not value:
            missing = True
            return ""
        return value

    text = _VAR.sub(sub, template)
    if missing:
        return None
    if text == "~" or text.startswith(("~/", "~\\")):
        home = environ.get("HOME") or environ.get("USERPROFILE")
        if not home:
            return None
        text = home + text[1:]
    return text


def find_claude_cli(cli_path: str | None = None) -> str | None:
    """SDK가 쓸 Claude Code 실행 파일. 지정 경로 → SDK 번들 → PATH 순. 없으면 None.

    SDK(0.2.166)의 찾기 순서를 따른다(번들 폴더 ``claude_agent_sdk/_bundled``). 실행하지 않는다.
    """
    if cli_path:
        return cli_path if Path(cli_path).is_file() else None
    try:
        import claude_agent_sdk
    except ImportError:  # 하드 의존이지만 설치가 깨졌을 때도 상태로 알린다
        return None
    name = "claude.exe" if platform.system() == "Windows" else "claude"
    bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / name
    if bundled.is_file():
        return str(bundled)
    return shutil.which("claude")


def _secret_check(
    check_id: str, title: str, ref: str, has_secret: Callable[[str], bool], t: Any
) -> ReadinessCheck:
    if not is_secret_ref(ref):
        return ReadinessCheck(id=check_id, title=title, ok=True, note=t.note_inline)
    name = secret_name(ref)
    found = has_secret(name)
    state = t.note_found if found else t.note_missing
    return ReadinessCheck(
        id=check_id, title=title, ok=found, note=t.note_secret.format(name=name, state=state)
    )


def assess_readiness(
    options: ClaudeSdkReadinessOptions,
    *,
    allow_subscription_auth: bool,
    has_secret: Callable[[str], bool],
    cli_found: bool,
    environ: Mapping[str, str],
    path_exists: Callable[[str], bool] = os.path.exists,
) -> ReadinessAssessment:
    """인증 해석 결과 → 상태. 모델·네트워크를 부르지 않고 비밀 값을 읽지 않는다.

    순서: CLI 없음(error) → 구독 방식(꺼짐 warn / 토큰 없음 error / 로그인 파일 없음 warn /
    준비 warn) → API 키(없음 error / 있음 ok).

    Args:
        options: 설치자 설정 ``readiness``.
        allow_subscription_auth: 설치자 설정(구독 방식 허용).
        has_secret: 비밀 이름이 있는지만 묻는 함수.
        cli_found: Claude Code 실행 파일을 찾았는지.
        environ: 로그인 확인 파일 경로를 풀 환경. CLI 하위 프로세스가 **실제로 받을** 환경을
            넘긴다(환경 정책으로 가려진 키는 빈 값 = 없음).
        path_exists: 파일 존재 확인(주입).
    """
    t = options.texts
    auth = options.auth
    checks = [
        ReadinessCheck(
            id="cli",
            title=t.check_cli,
            ok=cli_found,
            note=t.note_found if cli_found else t.note_missing,
        ),
        ReadinessCheck(
            id="auth_mode",
            title=t.check_mode,
            ok=True,
            note=t.mode_subscription if auth.mode == "subscription" else t.mode_api_key,
        ),
    ]
    blocked: ReadinessAssessment | None = None
    if not cli_found:
        blocked = ReadinessAssessment(
            state=ReadinessStates.CLI_MISSING,
            tone="error",
            summary=t.cli_missing_summary,
            short_summary=t.cli_missing_short,
            detail=t.cli_missing_detail,
            fixes=[t.fix_cli.action()],
            probe_block=ProbeReasonCodes.CLI_MISSING,
            probe_block_message=t.probe_cli_missing,
        )
    if auth.mode == "subscription":
        result = _assess_subscription(
            options, allow_subscription_auth, has_secret, environ, path_exists, checks
        )
    else:
        result = _assess_api_key(auth, has_secret, t, checks)
    chosen = blocked or result
    return dataclasses.replace(chosen, checks=checks)


def _assess_api_key(
    auth: ClaudeSdkAuth,
    has_secret: Callable[[str], bool],
    t: ClaudeSdkReadinessTexts,
    checks: list[ReadinessCheck],
) -> ReadinessAssessment:
    ref = api_key_ref(auth)
    check = _secret_check("api_key", t.check_key, ref, has_secret, t)
    checks.append(check)
    if check.ok:
        return ReadinessAssessment(
            state=ReadinessStates.AUTH_READY,
            tone="ok",
            summary=t.auth_ready_summary,
            short_summary=t.auth_ready_short,
        )
    return ReadinessAssessment(
        state=ReadinessStates.AUTH_MISSING,
        tone="error",
        summary=t.auth_missing_summary,
        short_summary=t.auth_missing_short,
        detail=t.auth_missing_detail.format(name=secret_name(ref)),
        fixes=[t.fix_key.action()],
        probe_block=ProbeReasonCodes.AUTH_MISSING,
        probe_block_message=t.probe_auth_missing,
    )


def _assess_subscription(
    options: ClaudeSdkReadinessOptions,
    allowed: bool,
    has_secret: Callable[[str], bool],
    environ: Mapping[str, str],
    path_exists: Callable[[str], bool],
    checks: list[ReadinessCheck],
) -> ReadinessAssessment:
    t = options.texts
    auth = options.auth
    checks.append(
        ReadinessCheck(
            id="subscription_allowed",
            title=t.check_subscription_allowed,
            ok=allowed,
            note=t.note_on if allowed else t.note_off,
        )
    )
    if not allowed:
        return ReadinessAssessment(
            state=ReadinessStates.SUBSCRIPTION_DISABLED,
            tone="warn",
            summary=t.subscription_disabled_summary,
            short_summary=t.subscription_disabled_short,
            detail=t.subscription_disabled_detail,
            fixes=[t.fix_subscription.action()],
            probe_block=ProbeReasonCodes.SUBSCRIPTION_DISABLED,
            probe_block_message=t.probe_subscription_disabled,
        )
    ready = ReadinessAssessment(
        state=ReadinessStates.SUBSCRIPTION_READY,
        tone="warn",
        summary=t.subscription_ready_summary,
        short_summary=t.subscription_ready_short,
        detail=t.subscription_ready_detail,
    )
    if auth.oauth_token:
        check = _secret_check("subscription_token", t.check_token, auth.oauth_token, has_secret, t)
        checks.append(check)
        if check.ok:
            return ready
        return ReadinessAssessment(
            state=ReadinessStates.SUBSCRIPTION_TOKEN_MISSING,
            tone="error",
            summary=t.subscription_token_missing_summary,
            short_summary=t.subscription_token_missing_short,
            detail=t.auth_missing_detail.format(name=secret_name(auth.oauth_token)),
            fixes=[t.fix_key.action()],
            probe_block=ProbeReasonCodes.AUTH_MISSING,
            probe_block_message=t.probe_auth_missing,
        )
    path = login_file(options.subscription_files, environ)
    paths = [path] if path else []
    found = sum(1 for p in paths if path_exists(p))
    checks.append(
        ReadinessCheck(
            id="subscription_file",
            title=t.check_login_file,
            ok=found > 0,
            note=t.note_files.format(count=len(paths), found=found),
        )
    )
    if found:
        return ready
    return ReadinessAssessment(
        state=ReadinessStates.SUBSCRIPTION_UNVERIFIED,
        tone="warn",
        summary=t.subscription_unverified_summary,
        short_summary=t.subscription_unverified_short,
        detail=f"{t.subscription_unverified_detail} {t.subscription_ready_detail}",
    )


def login_file(templates: Iterable[str], environ: Mapping[str, str]) -> str | None:
    """구독 로그인 확인 파일: 후보 중 처음 풀리는 경로(없으면 None). 파일은 보지 않는다.

    CLI 규칙과 같다. ``CLAUDE_CONFIG_DIR``가 비어 있지 않으면 그 폴더만, 아니면 ``~/.claude``.

    >>> files = ["${CLAUDE_CONFIG_DIR}/.credentials.json", "~/.claude/.credentials.json"]
    >>> login_file(files, {"HOME": "/h", "CLAUDE_CONFIG_DIR": "/cfg"})
    '/cfg/.credentials.json'
    >>> login_file(files, {"HOME": "/h", "CLAUDE_CONFIG_DIR": ""})
    '/h/.claude/.credentials.json'
    """
    for template in templates:
        path = expand_path(template, environ)
        if path:
            return path
    return None


# ---------------------------------------------------------------- 연결 테스트 결과 분류


AUTH_ERROR_KINDS = frozenset({"authentication_failed"})
"""``AssistantMessage.error`` 중 인증 실패로 볼 값."""

AUTH_HTTP_STATUSES = frozenset({401, 403})
"""``ResultMessage.api_error_status`` 중 인증 실패로 볼 값."""


@dataclass(frozen=True)
class ProbeOutcome:
    """SDK 응답 분류 결과(문장 원문 없음)."""

    ok: bool
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def classify_probe_messages(messages: Iterable[Any]) -> ProbeOutcome:
    """SDK 메시지(``AssistantMessage``·``ResultMessage``) → 성공·실패 사유.

    응답 글(모델 출력·오류 문장)은 담지 않는다. 확인 정보는 모델 id·오류 종류·HTTP 코드뿐이다.
    """
    model: str | None = None
    error_kind: str | None = None
    result: Any = None
    for msg in messages:
        kind = type(msg).__name__
        if kind == "AssistantMessage":
            model = getattr(msg, "model", None) or model
            error_kind = getattr(msg, "error", None) or error_kind
        elif kind == "ResultMessage":
            result = msg
    details: dict[str, Any] = {}
    if model:
        details["model"] = model
    if error_kind:
        details["sdk_error"] = error_kind
    status = getattr(result, "api_error_status", None) if result is not None else None
    if isinstance(status, int):
        details["http_status"] = status
    if result is None:
        return ProbeOutcome(False, ProbeReasonCodes.ERROR, {**details, "error": "no_result"})
    if error_kind in AUTH_ERROR_KINDS or status in AUTH_HTTP_STATUSES:
        return ProbeOutcome(False, ProbeReasonCodes.AUTH_FAILED, details)
    if bool(getattr(result, "is_error", False)) or error_kind:
        subtype = getattr(result, "subtype", None)
        if isinstance(subtype, str):
            details["subtype"] = subtype
        return ProbeOutcome(False, ProbeReasonCodes.ERROR, details)
    return ProbeOutcome(True, None, details)


NETWORK_ERROR_NAMES = frozenset({"CLIConnectionError"})
"""네트워크(연결)로 볼 SDK 예외 이름(``CLINotFoundError``는 CLI 없음)."""


def classify_probe_error(exc: BaseException) -> ProbeOutcome:
    """연결 테스트 중 예외 → 사유. 예외 문장은 담지 않고 형식 이름만."""
    names = {cls.__name__ for cls in type(exc).__mro__}
    details = {"error": type(exc).__name__}
    if "CLINotFoundError" in names:
        return ProbeOutcome(False, ProbeReasonCodes.CLI_MISSING, details)
    if names & NETWORK_ERROR_NAMES or isinstance(exc, ConnectionError):
        return ProbeOutcome(False, ProbeReasonCodes.NETWORK, details)
    return ProbeOutcome(False, ProbeReasonCodes.ERROR, details)


def probe_message(reason: str | None, texts: ClaudeSdkReadinessTexts, timeout_s: float) -> str:
    """사유 → 결과 문장(데이터 문구)."""
    return {
        None: texts.probe_ok,
        ProbeReasonCodes.AUTH_FAILED: texts.probe_auth_failed,
        ProbeReasonCodes.NETWORK: texts.probe_network,
        ProbeReasonCodes.TIMEOUT: texts.probe_timeout.format(seconds=timeout_s),
        ProbeReasonCodes.CLI_MISSING: texts.probe_cli_missing,
        ProbeReasonCodes.AUTH_MISSING: texts.probe_auth_missing,
        ProbeReasonCodes.SUBSCRIPTION_DISABLED: texts.probe_subscription_disabled,
    }.get(reason, texts.probe_error)


def probe_fixes(reason: str | None, texts: ClaudeSdkReadinessTexts) -> list[FixAction]:
    """사유 → 해결 버튼."""
    links = {
        ProbeReasonCodes.AUTH_FAILED: texts.fix_key,
        ProbeReasonCodes.AUTH_MISSING: texts.fix_key,
        ProbeReasonCodes.SUBSCRIPTION_DISABLED: texts.fix_subscription,
        ProbeReasonCodes.CLI_MISSING: texts.fix_cli,
    }
    link = links.get(reason) if reason else None
    return [link.action()] if link is not None else []


__all__ = [
    "AUTH_ERROR_KINDS",
    "AUTH_HTTP_STATUSES",
    "DEFAULT_PROBE_EXTRA_ARGS",
    "DEFAULT_PROBE_PROMPT",
    "DEFAULT_READINESS_KEY_REF",
    "DEFAULT_SUBSCRIPTION_FILES",
    "NETWORK_ERROR_NAMES",
    "PROBE_CATEGORIES",
    "ClaudeSdkReadinessOptions",
    "ClaudeSdkReadinessTexts",
    "FixLink",
    "ProbeOutcome",
    "ProbeReasonCodes",
    "ReadinessAssessment",
    "ReadinessStates",
    "api_key_ref",
    "assess_readiness",
    "classify_probe_error",
    "classify_probe_messages",
    "expand_path",
    "find_claude_cli",
    "login_file",
    "probe_fixes",
    "probe_message",
    "secret_name",
]
