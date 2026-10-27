"""`ClaudeSdkBackend`: Claude Agent SDK(`ClaudeSDKClient`) 실행 백엔드(X3, design §7.4)."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import os
import tempfile
import time
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookContext,
    HookInput,
    HookJSONOutput,
    HookMatcher,
)
from claude_agent_sdk.types import HookEvent
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_contracts import (
    AgentSettings,
    BackendCapabilities,
    BackendDescriptor,
    BackendLogoutResult,
    BackendProbeResult,
    BackendReadiness,
    EnforceCapabilities,
    ErrorCodes,
    ErrorInfo,
    InteractionGrant,
    Issue,
    LogWarningPayload,
    ModelInfo,
    ResourceBundle,
    Usage,
)
from agent_console_runtime import (
    AgentRequest,
    AgentResult,
    BackendCheckContext,
    BackendEventSink,
    BackendLoginContext,
    CancelToken,
    InteractivePort,
    LoginDriver,
    LoginRefusedError,
    SecretNotFoundError,
    SecretResolver,
    SessionRef,
    SubagentResultListener,
    is_secret_ref,
)

from ._bundle import (
    COMMAND_HOOK_SLOTS,
    RESOURCE_SLOTS,
    SUBAGENT_SLOTS,
    BundleMapping,
    BundleOptions,
    files_notice,
    map_bundle,
    union,
    without_disallowed,
)
from ._collector_api import ClaudeSdkCollector, CollectedEvent, resolve_collector_settings
from ._collector_run import CollectorRun
from ._env import EnvPolicy, apply_env_policy
from ._guard import ToolGuard, guard_from_limits
from ._hooks import (
    HookRunner,
    HookSpec,
    command_hook,
    hook_env,
    hook_settings_json,
    subprocess_runner,
)
from ._host_tools import (
    HostToolMapping,
    ToolServerFactory,
    build_host_tool_server,
    sdk_tool_server,
)
from ._interact import InteractionKindMap, PermissionBridge
from ._login import ClaudeSdkLoginOptions
from ._login_support import ClaudeLoginSupport, PtySupport
from ._options import (
    CLAUDE_SDK_BACKEND_ID,
    MANAGED_SDK_FIELDS,
    ClaudeSdkAuth,
    ClaudeSdkBackendOptions,
    claude_sdk_config_schema,
)
from ._probe import (
    DEFAULT_HOOK_PROBE_FOLDER,
    HookProbePlan,
    hook_probe_enabled,
    hook_probe_note,
    plan_hook_probe,
)
from ._readiness import (
    PROBE_CATEGORIES,
    ClaudeSdkReadinessOptions,
    ProbeOutcome,
    ProbeReasonCodes,
    ReadinessAssessment,
    ReadinessStates,
    api_key_ref,
    assess_readiness,
    classify_probe_error,
    classify_probe_messages,
    find_claude_cli,
    probe_fixes,
    probe_message,
)
from ._redact import DEFAULT_MAX_RAW_CHARS, RawSanitizer
from ._subagents import SubagentMapping, build_agent_definitions
from ._translate import Emission, MessageTranslator
from .collectors import default_collectors, discover_collectors, select_collectors

DEFAULT_CANCEL_GRACE_SECONDS = 5.0
"""취소 후 interrupt 응답을 기다리는 시간. 넘으면 연결을 끊는다(CLI 프로세스 종료)."""

PROBE_COST_NOTE = (
    "아주 짧은 요청 한 번을 실제로 보냅니다. API 키 방식이면 소량의 API 사용료가, 구독 방식이면 "
    "구독 사용량이 조금 듭니다."
)
"""디스크립터 ``probe_cost_note``(연결 테스트 비용 안내)."""

PROBE_DISCONNECT_SECONDS = 2.0
"""연결 테스트가 끝난 뒤 CLI 연결을 끊는 데 기다리는 최대 시간."""

type CliLocator = Callable[[str | None], str | None]
"""지정 경로(없으면 None) → Claude Code 실행 파일 경로(없으면 None). 기본 ``find_claude_cli``."""


class ClaudeSdkInstallOptions(BaseModel):
    """설치자 설정(앱 설정 `backends.claude-agent-sdk`) 형식(`ClaudeSdkBackend.from_options`)."""

    model_config = ConfigDict(extra="forbid")

    models: list[ModelInfo] = Field(default_factory=list, description="`list_models()` 목록.")
    env_policy: EnvPolicy | None = Field(
        default=None, description="하위 프로세스 환경 상속 정책. 비우면 기본 허용 목록."
    )
    max_raw_chars: int = Field(default=DEFAULT_MAX_RAW_CHARS, ge=0)
    cancel_grace: float = Field(default=DEFAULT_CANCEL_GRACE_SECONDS, ge=0)
    interaction_kinds: InteractionKindMap | None = Field(
        default=None,
        description="이 어댑터가 여는 상호작용 종류 id(question·tool_permission 자리). "
        "비우면 기본 종류 이름.",
    )
    allow_command_hooks: bool = Field(
        default=False,
        description="명령형 hook(실행 묶음 hooks 칸) 실행을 허용한다. 꺼져 있으면 hooks 칸을 받지 "
        "않는다(검증·미리보기 경고 resource.slot_unsupported). 기본 꺼짐(명령 실행은 위험).",
    )
    allow_subscription_auth: bool = Field(
        default=True,
        description="본인 구독 로그인 자격(auth.mode=subscription) 사용을 허용한다. 기본은 구독"
        "(켜짐, 본인 책임 — 켜져 있으면 검증 경고와 실행마다 경고를 낸다). API 키도 선택 가능"
        "(auth.mode=api_key). 끄면 구독 방식은 설정 검증 오류(backend.subscription_auth_disabled)"
        "이고 실행을 거부한다(Anthropic 문서상 Agent SDK 기반 앱에는 API 키 사용이 안내됨).",
    )
    hook_probe_command: list[str] | None = Field(
        default=None,
        min_length=1,
        description="observe.hook_probe가 켜졌을 때 hook 명령을 감쌀 probe 실행 인자. 비우면 "
        "[현재 파이썬, -m, agent_console_hook_probe].",
    )
    hook_probe_folder: str = Field(
        default=DEFAULT_HOOK_PROBE_FOLDER,
        min_length=1,
        pattern=r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$",
        description="노드 실행 폴더 아래 hook probe 기록 폴더 이름(로그 출처 hook-probe-jsonl의 "
        "경로 규칙과 맞춘다).",
    )
    readiness: ClaudeSdkReadinessOptions = Field(
        default_factory=ClaudeSdkReadinessOptions,
        description="상태 점검·연결 테스트가 볼 인증 방식(기본 구독 로그인, API 키도 선택 가능), "
        "실행 파일 경로, 테스트 프롬프트·모델·CLI 인자, 문구.",
    )
    login: ClaudeSdkLoginOptions = Field(
        default_factory=ClaudeSdkLoginOptions,
        description="앱 화면 구독 로그인(claude auth login을 PTY로 중계, 기본 켜짐)·로그아웃. 실행 "
        "인자·화면 글자 규칙·허용 URL 호스트·하위 프로세스 환경·문구. allow_subscription_auth가 "
        "꺼졌거나 선택 기능 login(agent-console-pty-session)이 없으면 제공하지 않는다.",
    )


HOOKS_DISABLED_NOTE = (
    "설치자 설정 backends.claude-agent-sdk.allow_command_hooks가 꺼져 있어 명령형 hook을 실행하지 "
    "않습니다"
)
"""`allow_command_hooks`가 꺼졌을 때 `capabilities.slot_notes[hooks]`."""


class INTERACTION_ISSUES:  # noqa: N801 — 문서 상수 묶음
    """`validate_settings`가 내는 이슈 코드."""

    NO_PATH = "interaction.no_path"


class COLLECTOR_ISSUES:  # noqa: N801 — 문서 상수 묶음
    """관측 수집기 설정(`observe.collectors`)에 대해 `validate_settings`가 내는 이슈 코드(X7)."""

    UNKNOWN = "observe.unknown_collector"
    """warning: 이 백엔드에 없는 수집기 id(실행 때는 무시한다)."""
    INVALID_CONFIG = "observe.collector_config_invalid"
    """warning: 수집기 설정이 수집기가 선언한 스키마와 맞지 않는다
    (실행 때 그 수집기는 경고 후 빠진다)."""


SUBSCRIPTION_AUTH_DISABLED_MESSAGE = (
    "Anthropic 문서상 Agent SDK 기반 앱에는 API 키 사용이 안내됩니다. 본인 구독 자격으로 쓰려면 "
    "설치자 설정에서 allow_subscription_auth를 켜세요(본인 책임)."
)
"""`allow_subscription_auth`가 꺼졌는데 구독 방식일 때 이유 문장(검증 오류·실행 거부)."""

SUBSCRIPTION_AUTH_WARNING = (
    "auth.mode=subscription: 설치자 설정 allow_subscription_auth에 따라 본인 Claude Code 구독 "
    "로그인 자격으로 실행합니다. Anthropic 문서상 Agent SDK 기반 앱에는 API 키 사용이 안내되며, "
    "구독 자격 사용은 본인 책임입니다."
)
"""`allow_subscription_auth`가 켜졌을 때 구독 방식 경고(검증 경고·실행마다 `log.warning`)."""


class AUTH_ISSUES:  # noqa: N801 — 문서 상수 묶음
    """인증 방식에 대해 `validate_settings`가 내는 이슈 코드(design §3R.6, E-13)."""

    SUBSCRIPTION_DISABLED = "backend.subscription_auth_disabled"
    """error: 구독 방식인데 설치자 `allow_subscription_auth`가 꺼짐(실행도 같은 코드로 거부)."""
    SUBSCRIPTION_ENABLED = "backend.subscription_auth_enabled"
    """warning: 구독 방식이 설치자 설정으로 허용됨(본인 책임 안내)."""


class ClaudeSdkErrorCodes:
    """이 백엔드가 쓰는 `ErrorInfo.code` 값."""

    INVALID_OPTIONS = ErrorCodes.VALIDATION_FAILED
    SECRET_UNRESOLVED = "secret_unresolved"
    AUTH_MISSING = "auth_missing"
    SUBSCRIPTION_AUTH_DISABLED = AUTH_ISSUES.SUBSCRIPTION_DISABLED
    BACKEND_ERROR = "backend_error"
    NO_RESULT = "backend_no_result"
    AGENT_ERROR = "agent_error"


class SdkClient(Protocol):
    """백엔드가 쓰는 `ClaudeSDKClient`의 부분. 테스트는 이 형태의 가짜를 주입한다."""

    async def connect(self) -> None: ...

    async def query(self, prompt: str) -> None: ...

    def receive_response(self) -> AsyncIterator[Any]: ...

    async def interrupt(self) -> None: ...

    async def disconnect(self) -> None: ...


type ClientFactory = Callable[[ClaudeAgentOptions], SdkClient]
"""`ClaudeAgentOptions` → 클라이언트. 기본은 `ClaudeSDKClient`."""


class AuthMissingError(ValueError):
    """`auth.mode=api_key`인데 키가 없다(값 없음, 변수 이름만)."""


@dataclass
class _Prepared:
    """실행 전 준비 결과(비밀 해석 끝난 env, 묶음·서브에이전트 매핑, 경고)."""

    env: dict[str, str]
    secrets: list[str]
    bundle: BundleMapping
    members: SubagentMapping
    warnings: list[LogWarningPayload] = field(default_factory=list)


def _default_client(options: ClaudeAgentOptions) -> SdkClient:
    return ClaudeSDKClient(options=options)


class ClaudeSdkBackend:
    """Claude Agent SDK로 에이전트를 실행하는 백엔드.

    설정은 `Agent.backend_options`(형식 `ClaudeSdkBackendOptions`), 관측은 `AgentRequest.observe`
    (`ObserveSettings` 덤프: `collectors` + 옛 키 `hooks`·`mcp`·`hook_events`, 해석은
    `collectors.resolve_collector_settings`), 실행 범위는 `AgentRequest.limits`에서 온다. 모델은
    `Agent.model`. 관측은 켜진 수집기(X7)가 한다 — 백엔드는 수집기 이름을 모른다.

    `capabilities.enforce`: 명령(commands)만 강제한다 — 모든 도구 호출(서브에이전트 포함)에 거는
    `PreToolUse` 훅이 `limits.commands`로 명령 입력을 검사한다. 디렉터리는 파일 도구 경로만
    검사하고 명령이 건드리는 파일은 막지 못하며, 네트워크는 네트워크 도구를 끄는 것뿐이고 MCP 서버·
    서버 측 도구·허용된 명령의 통신은 막지 못하므로 둘 다 false로 선언한다.

    Args:
        client_factory: SDK 클라이언트 생성기(테스트에서 가짜 주입).
        models: `list_models()`가 돌려줄 목록(설정 데이터). SDK에 모델 목록 API가 없어
            기본은 빈 목록.
        secrets: 남은 `secret://` 참조 해석과 raw 가리기에 쓸 해석기(선택).
        clock: MCP 호출 소요 시간 측정용 시각 함수.
        max_raw_chars: 이벤트 raw 하나의 최대 JSON 길이.
        cancel_grace: 취소 후 interrupt 응답 대기 시간(초).
        backend_id: 디스크립터 id(다른 이름으로 여러 번 등록할 때).
        env_policy: CLI 하위 프로세스가 물려받을 서버 환경변수 정책(`EnvPolicy`, 기본 허용 목록).
        environ: 정책을 적용할 부모 환경(기본 None = 실행 시점의 `os.environ`, SDK가 상속하는 값).
        interaction_kinds: 여는 상호작용 종류 id(데이터).
        allow_command_hooks: 명령형 hook(`hooks` 칸) 실행 허용(설치자 설정, 기본 거짓). 거짓이면
            `resource_slots`에 `hooks`가 없고 `slot_notes`로 이유를 알린다.
        allow_subscription_auth: 본인 구독 로그인 자격(`auth.mode=subscription`) 허용(설치자 설정,
            기본 참 = 구독 기본, 본인 책임). 거짓이면 구독 방식은 검증 오류이고 `run`이 비밀을
            해석하거나 SDK를 부르기 전에 거부한다. 참이면 강화된 경고
            (`SUBSCRIPTION_AUTH_WARNING`)를 낸다. 이 백엔드는 구독 자격(OAuth 토큰)을 받아 두거나
            저장하는 API가 없다 — 토큰은 사용자가 자기 비밀
            저장소에 둔 `secret://` 참조로만 읽어 CLI 하위 프로세스 env로 넘긴다.
        hook_runner: hook 명령 실행기(기본 셸 없는 하위 프로세스, 테스트에서 가짜 주입).
        collectors: 쓸 수 있는 관측 수집기(X7, 인스턴스 또는 인자 없는 클래스). None이면 이
            패키지 기본 수집기(`collectors.default_collectors`). `descriptor.backend`가 이 백엔드
            id인 것만 쓰고 id가 겹치면 앞의 것. `from_options`는 entry point
            `agent_console.collectors`에서 찾는다(`collectors.discover_collectors`).
        hook_probe_command: 유효 관측 설정 `observe.hook_probe`가 참일 때 전달하는 명령형 hook을
            감쌀 probe 실행 인자(설치자 설정, None = `agent_console_hook_probe` 기본). 기록은
            `AgentRequest.run_folder/<hook_probe_folder>`에 남는다(design §4R.7, F-16).
        hook_probe_folder: 실행 폴더 아래 기록 폴더 이름.
        tool_server_factory: 플랫폼 도구(`AgentRequest.host_tools`)를 담을 MCP 서버 생성기
            (기본 `create_sdk_mcp_server` — in-process SDK MCP 서버, 테스트에서 가짜 주입).
            서버 이름은 `backend_options.host_tool_server`, 모델이 부르는 이름
            `mcp__<서버>__<도구>`는 `allowed_tools`에 들어간다.
        readiness: 상태 점검·연결 테스트 설정(`ClaudeSdkReadinessOptions`, 설치자 설정
            `readiness`). 점검할 인증 방식·실행 파일 경로·테스트 프롬프트·문구.
        cli_locator: Claude Code 실행 파일 찾기(기본 `find_claude_cli`, 테스트에서 주입).
        path_exists: 구독 로그인 파일 존재 확인(기본 `os.path.exists`, 테스트에서 주입).
        login: 앱 화면 구독 로그인 설정(`ClaudeSdkLoginOptions`, 설치자 설정 `login`, 기본 켜짐).
            켜져 있고 `allow_subscription_auth`가 참이고 PTY(선택 추가 기능 `login`)가 있으면
            `capabilities.login/logout = true`·`login_methods = [cli-login]`.
        pty_spawner: 로그인용 PTY 어댑터(`agent_console_pty_session.PtySpawner`, 테스트 주입).
        pty_support: PTY 사용 가능 여부(None = 감지, 테스트 주입).
    """

    def __init__(
        self,
        *,
        client_factory: ClientFactory = _default_client,
        models: Iterable[ModelInfo | Mapping[str, Any]] = (),
        secrets: SecretResolver | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_raw_chars: int = DEFAULT_MAX_RAW_CHARS,
        cancel_grace: float = DEFAULT_CANCEL_GRACE_SECONDS,
        backend_id: str = CLAUDE_SDK_BACKEND_ID,
        env_policy: EnvPolicy | Mapping[str, Any] | None = None,
        environ: Mapping[str, str] | None = None,
        interaction_kinds: InteractionKindMap | Mapping[str, Any] | None = None,
        allow_command_hooks: bool = False,
        allow_subscription_auth: bool = True,
        hook_runner: HookRunner = subprocess_runner,
        collectors: Iterable[ClaudeSdkCollector | type] | None = None,
        hook_probe_command: Sequence[str] | None = None,
        hook_probe_folder: str = DEFAULT_HOOK_PROBE_FOLDER,
        tool_server_factory: ToolServerFactory = sdk_tool_server,
        readiness: ClaudeSdkReadinessOptions | Mapping[str, Any] | None = None,
        cli_locator: CliLocator = find_claude_cli,
        path_exists: Callable[[str], bool] = os.path.exists,
        login: ClaudeSdkLoginOptions | Mapping[str, Any] | None = None,
        pty_spawner: Any | None = None,
        pty_support: PtySupport | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._readiness = ClaudeSdkReadinessOptions.model_validate(readiness or {})
        self._cli_locator = cli_locator
        self._path_exists = path_exists
        self._tool_server_factory = tool_server_factory
        self._probe_command = list(hook_probe_command) if hook_probe_command else None
        self._probe_folder = hook_probe_folder
        self._allow_subscription_auth = allow_subscription_auth
        self._allow_command_hooks = allow_command_hooks
        self._hook_runner = hook_runner
        self._slots: tuple[str, ...] = RESOURCE_SLOTS + (
            COMMAND_HOOK_SLOTS if allow_command_hooks else ()
        )
        self._interaction_kinds = InteractionKindMap.model_validate(interaction_kinds or {})
        self._env_policy = EnvPolicy.model_validate(env_policy or {})
        self._environ = environ
        self._models = [ModelInfo.model_validate(m) for m in models]
        self._secrets = secrets
        self._clock = clock
        self._max_raw = max_raw_chars
        self._grace = cancel_grace
        self._collectors = select_collectors(
            default_collectors(backend_id) if collectors is None else collectors, backend_id
        )
        self._login = ClaudeLoginSupport(
            ClaudeSdkLoginOptions.model_validate(login or {}),
            allow_subscription_auth=allow_subscription_auth,
            readiness=self._readiness,
            cli_locator=cli_locator,
            env_policy=self._env_policy,
            environ=environ,
            spawner=pty_spawner,
            pty=pty_support,
        )
        self.collector_reports: list[Any] = []
        """`from_options`가 entry point를 읽은 보고서(`agent_console_registry.LoadReport`)."""
        self.descriptor = BackendDescriptor(
            id=backend_id,
            title="Claude Agent SDK",
            description="Claude Agent SDK로 Claude Code 에이전트를 실행합니다.",
            cost_note="구독 또는 API 사용량이 소모됩니다.",
            probe_cost_note=PROBE_COST_NOTE,
            config_schema=claude_sdk_config_schema(),
            capabilities=BackendCapabilities(
                streaming=True,
                tools=True,
                hooks=True,
                mcp=True,
                resume=True,
                cancel=True,
                subagents=True,
                host_tools=True,
                status=True,
                probe=True,
                login=self._login.enabled,
                logout=self._login.enabled,
                resource_slots=list(self._slots),
                subagent_slots=list(SUBAGENT_SLOTS),
                slot_notes=(
                    None
                    if allow_command_hooks
                    else dict.fromkeys(COMMAND_HOOK_SLOTS, HOOKS_DISABLED_NOTE)
                ),
                interactions=self._interaction_kinds.kinds(),
                enforce=EnforceCapabilities(directories=False, commands=True, network=False),
            ),
            collectors=[c.descriptor for c in self._collectors],
            login_methods=self._login.methods(),
        )

    @classmethod
    def from_options(
        cls,
        options: Mapping[str, Any],
        *,
        secrets: SecretResolver,
        environ: Mapping[str, str],
    ) -> ClaudeSdkBackend:
        """`ConfigurableBackend` 훅: 설치자 설정(`ClaudeSdkInstallOptions`)으로 만든다.

        `secrets`는 남은 참조 해석·raw 가리기에, `environ`은 환경 정책을 적용할 부모 환경으로 쓴다.
        관측 수집기는 entry point `agent_console.collectors`에서 찾는다(보고서는
        `collector_reports`).

        Raises:
            ValueError: 모르는 키·잘못된 값(위치와 사유만, 값은 넣지 않는다).
        """
        try:
            parsed = ClaudeSdkInstallOptions.model_validate(dict(options))
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}"
                for e in exc.errors(include_input=False, include_url=False)
            )
            raise ValueError(f"claude-agent-sdk 백엔드 설정 오류: {problems}") from None
        found, reports = discover_collectors(CLAUDE_SDK_BACKEND_ID)
        backend = cls(
            collectors=found,
            models=parsed.models,
            secrets=secrets,
            env_policy=parsed.env_policy,
            environ=environ,
            max_raw_chars=parsed.max_raw_chars,
            cancel_grace=parsed.cancel_grace,
            interaction_kinds=parsed.interaction_kinds,
            allow_command_hooks=parsed.allow_command_hooks,
            allow_subscription_auth=parsed.allow_subscription_auth,
            hook_probe_command=parsed.hook_probe_command,
            hook_probe_folder=parsed.hook_probe_folder,
            readiness=parsed.readiness,
            login=parsed.login,
        )
        backend.collector_reports = list(reports)
        return backend

    def validate_settings(self, effective: AgentSettings, grant: InteractionGrant) -> list[Issue]:
        """선택 훅(`SettingsValidator`, design §R14.8).

        - `auth.mode=subscription`: 설치자 `allow_subscription_auth`가 꺼져 있으면 error
          `backend.subscription_auth_disabled`(이유 문장), 켜져 있으면 warning
          `backend.subscription_auth_enabled`(본인 책임 안내).
        - 묻는 권한 모드인데 도구 승인 경로가 없으면 경고한다.
        - 관측 설정 `observe.collectors`에 이 백엔드에 없는 수집기 id가 있으면 warning
          `observe.unknown_collector`, 수집기 설정이 스키마와 맞지 않으면 warning
          `observe.collector_config_invalid`.

        묻는 모드 목록은 설정 데이터(`backend_options.prompting_permission_modes`)다. 실행은 되며,
        묻는 요청은 `unmatched_permission`(기본 deny)으로 자동 처리된다. 설정이 틀렸으면 이 훅은
        아무것도 내지 않는다(실행 때 `validation_failed`).
        """
        collector_issues = self._collector_issues(effective)
        try:
            opts = ClaudeSdkBackendOptions.model_validate(effective.backend_options or {})
        except ValidationError:
            return collector_issues
        issues = [*collector_issues, *self._auth_issues(opts)]
        mode = opts.sdk_options.get("permission_mode", opts.permission_mode)
        need = self._interaction_kinds.tool_permission
        if mode not in opts.prompting_permission_modes or need in grant.kinds:
            return issues
        return [
            *issues,
            Issue(
                severity="warning",
                code=INTERACTION_ISSUES.NO_PATH,
                message=f"권한 모드 {mode!r}는 실행 중 도구 승인을 묻지만 응답 경로(도구 승인 "
                "상호작용 연결)가 없어 묻는 요청은 unmatched_permission으로 자동 처리됩니다",
                details={
                    "kinds": [need],
                    "permission_mode": mode,
                    "unmatched_permission": opts.unmatched_permission,
                },
            ),
        ]

    def _collector_issues(self, effective: AgentSettings) -> list[Issue]:
        observe = effective.observe
        if observe is None or not observe.collectors:
            return []
        known = {c.descriptor.id: c for c in self._collectors}
        issues: list[Issue] = []
        for collector_id, setting in observe.collectors.items():
            collector = known.get(collector_id)
            if collector is None:
                issues.append(
                    Issue(
                        severity="warning",
                        code=COLLECTOR_ISSUES.UNKNOWN,
                        message=f"관측 수집기 {collector_id!r}는 백엔드 {self.descriptor.id!r}에 "
                        "없어 기록하지 않습니다",
                        details={
                            "collector": collector_id,
                            "backend": self.descriptor.id,
                            "known": sorted(known),
                        },
                    )
                )
                continue
            if setting.config is None:
                continue
            problems = collector.config_problems(dict(setting.config))
            if problems:
                issues.append(
                    Issue(
                        severity="warning",
                        code=COLLECTOR_ISSUES.INVALID_CONFIG,
                        message=f"관측 수집기 {collector_id!r} 설정이 올바르지 않습니다: "
                        + "; ".join(problems),
                        details={"collector": collector_id, "problems": problems},
                    )
                )
        return issues

    def _auth_issues(self, opts: ClaudeSdkBackendOptions) -> list[Issue]:
        if opts.auth is None or opts.auth.mode != "subscription":
            return []
        details: dict[str, Any] = {
            "option": "auth.mode",
            "value": "subscription",
            "install_option": "allow_subscription_auth",
        }
        if not self._allow_subscription_auth:
            return [
                Issue(
                    severity="error",
                    code=AUTH_ISSUES.SUBSCRIPTION_DISABLED,
                    message=SUBSCRIPTION_AUTH_DISABLED_MESSAGE,
                    details=details,
                )
            ]
        return [
            Issue(
                severity="warning",
                code=AUTH_ISSUES.SUBSCRIPTION_ENABLED,
                message=SUBSCRIPTION_AUTH_WARNING,
                details=details,
            )
        ]

    def preview_notes(self, effective: AgentSettings, bundle: ResourceBundle) -> list[Issue]:
        """선택 훅(`ac-teams.PreviewNotes`): 묶음 미리보기 안내.

        유효 관측 설정 `observe.hook_probe`가 참이면 info `observe.hook_probe_wrapped`("hook 감싸기
        켜짐", 감쌀 명령형 hook 수)를 낸다. 꺼져 있으면 아무것도 내지 않는다.
        """
        observe = (
            effective.observe.model_dump(mode="json", exclude_none=True)
            if effective.observe is not None
            else None
        )
        if not hook_probe_enabled(observe):
            return []
        count = sum(
            len(items)
            for slot in COMMAND_HOOK_SLOTS
            if isinstance(items := bundle.slots.get(slot), list)
        )
        return [hook_probe_note(count, delivered=self._allow_command_hooks)]

    # ------------------------------------------------------------ 준비 상태·연결 테스트

    def _assess(self, ctx: BackendCheckContext) -> tuple[ReadinessAssessment, str | None]:
        cli = self._cli_locator(self._readiness.cli_path)
        parent = self._environ if self._environ is not None else os.environ
        # CLI가 실제로 받을 환경(정책으로 가린 키 = 빈 값)으로 로그인 파일 위치를 푼다.
        child = {**parent, **apply_env_policy(parent, self._env_policy, {})}
        assessment = assess_readiness(
            self._readiness,
            allow_subscription_auth=self._allow_subscription_auth,
            has_secret=ctx.has_secret,
            cli_found=cli is not None,
            environ=child,
            path_exists=self._path_exists,
        )
        return assessment, cli

    async def status(self, ctx: BackendCheckContext) -> BackendReadiness:
        """선택 능력(정적 점검, ux-overhaul §15.8): 모델·네트워크를 부르지 않는다.

        설치자 설정 `readiness.auth`의 인증 방식을 해석해 상태를 만든다. 비밀은 이름이 있는지만
        묻고(`ctx.has_secret`) 값을 읽지 않는다. 구독 방식은 `allow_subscription_auth`(꺼짐 =
        `subscription_disabled`, 켜짐 = `subscription_ready` 본인 책임 경고)와 로그인 파일 존재로
        정한다. 실행 파일이 없으면 `cli_missing`. 상태 이름은 `ReadinessStates`.
        """
        a, _cli = self._assess(ctx)
        detail = a.detail
        note = self._login.unavailable_note
        if note and a.state == ReadinessStates.SUBSCRIPTION_UNVERIFIED:
            detail = f"{detail} {note}".strip()
        return BackendReadiness(
            backend_id=ctx.backend_id,
            state=a.state,
            tone=a.tone,
            summary=a.summary,
            short_summary=a.short_summary,
            detail=detail,
            fixes=a.fixes,
            checked_at=ctx.clock(),
            checks=a.checks,
            actions=self._login.actions(a.state, token_auth=bool(self._readiness.auth.oauth_token)),
        )

    async def start_login(self, ctx: BackendLoginContext, method_id: str) -> LoginDriver:
        """선택 능력(앱 화면 로그인, ux-overhaul §15.9): `claude auth login`을 PTY로 띄운다.

        성공 판정은 `status_command`(기본 `claude auth status`) 종료 코드 + `authMethod`다. 앱은
        로그인 자격(토큰)을 읽거나 저장하지 않는다 — CLI가 자기 위치에 쓴다.

        Raises:
            LoginRefusedError: `allow_subscription_auth`가 꺼졌거나
                (`backend.subscription_auth_disabled`)
                능력이 없다(`backend.login_unsupported`).
        """
        return await self._login.start(ctx, method_id)

    async def logout(self, ctx: BackendLoginContext, method_id: str | None) -> BackendLogoutResult:
        """선택 능력(앱 화면 로그아웃): `claude auth logout`(`login.logout_command`)."""
        return await self._login.logout(ctx)

    def login_refusal(self) -> LoginRefusedError | None:
        """능력이 꺼진 이유(`LoginRefusalAware`): `allow_subscription_auth`가 꺼졌으면
        `backend.subscription_auth_disabled`. 서비스가 `login_unsupported` 대신 이 거절을 낸다."""
        return self._login.refusal()

    async def probe(self, ctx: BackendCheckContext, timeout_s: float) -> BackendProbeResult:
        """선택 능력(연결 테스트): 도구 없는 한 턴짜리 짧은 호출 한 번.

        실행 파일이 없거나, 구독 방식이 꺼져 있거나, 키·토큰이 없으면 SDK를 부르지 않고 거부한다
        (`ProbeReasonCodes`). 호출은 `timeout_s`보다 조금 먼저 끊는다. 실패 사유는 인증
        (`auth_failed`)·네트워크(`network`)·시간 초과(`timeout`)·기타(`error`)로 나누고
        `details.category`에 분류를 싣는다. 응답 글·예외 문장·비밀 값은 결과에 넣지 않는다.
        """
        texts = self._readiness.texts
        assessment, cli = self._assess(ctx)
        started = self._clock()
        if assessment.probe_block is not None or cli is None:
            reason = assessment.probe_block or ProbeReasonCodes.CLI_MISSING
            outcome = ProbeOutcome(False, reason)
        else:
            outcome = await self._probe_call(cli, timeout_s)
        latency = max(0, round((self._clock() - started) * 1000))
        details = dict(outcome.details)
        if not outcome.ok:
            details["category"] = PROBE_CATEGORIES.get(outcome.reason or "", "other")
        return BackendProbeResult(
            backend_id=ctx.backend_id,
            ok=outcome.ok,
            latency_ms=latency,
            reason=outcome.reason,
            message=(
                assessment.probe_block_message
                if assessment.probe_block is not None
                else probe_message(outcome.reason, texts, timeout_s)
            ),
            details=details,
            fixes=probe_fixes(outcome.reason, texts),
            finished_at=ctx.clock(),
        )

    def _probe_options(self, cli: str, cwd: str) -> ClaudeAgentOptions:
        """연결 테스트용 SDK 옵션(도구·설정 파일·MCP 없음, 한 턴).

        Raises:
            SecretNotFoundError, AuthMissingError: 키·토큰을 해석할 수 없을 때.
        """
        r = self._readiness
        auth = r.auth
        if auth.mode == "api_key":
            auth = auth.model_copy(update={"api_key": api_key_ref(auth)})
        explicit, _warnings = _auth_env(auth, {}, self._lookup)
        parent = self._environ if self._environ is not None else os.environ
        return ClaudeAgentOptions(
            tools=[],
            allowed_tools=[],
            system_prompt="",
            max_turns=1,
            model=r.probe_model,
            cwd=cwd,
            cli_path=cli,
            env=apply_env_policy(parent, self._env_policy, explicit),
            setting_sources=[],
            strict_mcp_config=True,
            permission_mode="dontAsk",
            extra_args=dict(r.probe_extra_args),
            stderr=_drop_line,
        )

    async def _probe_call(self, cli: str, timeout_s: float) -> ProbeOutcome:
        budget = max(0.05, timeout_s - min(PROBE_DISCONNECT_SECONDS, timeout_s * 0.1))
        with tempfile.TemporaryDirectory(prefix="ac-probe-") as cwd:
            try:
                options = self._probe_options(cli, cwd)
            except (SecretNotFoundError, AuthMissingError):
                return ProbeOutcome(False, ProbeReasonCodes.AUTH_MISSING)
            client = self._client_factory(options)
            messages: list[Any] = []
            try:
                async with asyncio.timeout(budget):
                    await client.connect()
                    await client.query(self._readiness.probe_prompt)
                    async for msg in client.receive_response():
                        messages.append(msg)
            except TimeoutError:
                return ProbeOutcome(
                    False, ProbeReasonCodes.TIMEOUT, {"timeout_s": round(timeout_s, 3)}
                )
            except Exception as exc:  # 문장은 버리고 형식 이름만(비밀이 섞일 수 있음)
                return classify_probe_error(exc)
            finally:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(client.disconnect(), PROBE_DISCONNECT_SECONDS)
            return classify_probe_messages(messages)

    async def list_models(self) -> list[ModelInfo]:
        """생성 시 받은 모델 목록(복사본)."""
        return list(self._models)

    # ------------------------------------------------------------ 실행

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        """에이전트를 한 번 실행한다. 설정·SDK 오류는 `failed` 결과로 돌려준다(예외 없음).

        `req.subagents`가 있으면 SDK 서브에이전트(`agents`)로 같은 세션에서 실행하고, 대상 이벤트는
        `actor`=대상 에이전트, `node_path`=`sink.child_path(대상)`로 낸다.
        sink가 `SubagentResultListener`면 대상 결과마다 알린다.
        """
        try:
            opts = ClaudeSdkBackendOptions.model_validate(req.agent.backend_options or {})
        except ValidationError as exc:
            return _failed(
                ClaudeSdkErrorCodes.INVALID_OPTIONS,
                "claude-sdk 백엔드 설정(backend_options)이 올바르지 않습니다",
                # 입력값은 싣지 않는다(잘못된 필드에 넣은 비밀이 오류 상세로 새지 않게).
                {
                    "errors": exc.errors(
                        include_url=False, include_context=False, include_input=False
                    )
                },
            )
        if (
            opts.auth is not None
            and opts.auth.mode == "subscription"
            and not self._allow_subscription_auth
        ):
            # 비밀(oauth_token)을 해석하기 전, SDK를 부르기 전에 거부한다.
            return _failed(
                ClaudeSdkErrorCodes.SUBSCRIPTION_AUTH_DISABLED,
                SUBSCRIPTION_AUTH_DISABLED_MESSAGE,
                {"option": "auth.mode", "install_option": "allow_subscription_auth"},
            )
        try:
            prepared = self._prepare(req, opts)
        except SecretNotFoundError as exc:
            return _failed(
                ClaudeSdkErrorCodes.SECRET_UNRESOLVED,
                f"비밀 {exc.name!r}를 해석할 수 없습니다",
            )
        except AuthMissingError as exc:
            return _failed(ClaudeSdkErrorCodes.AUTH_MISSING, str(exc))
        except ValueError as exc:
            # 묶음·서브에이전트 모양 오류(메시지에 값은 없다).
            return _failed(ClaudeSdkErrorCodes.INVALID_OPTIONS, str(exc))
        try:
            host_tools = build_host_tool_server(
                req.host_tools,
                server=opts.host_tool_server,
                cancel=cancel,
                reserved=[*opts.mcp_servers, *prepared.bundle.mcp_servers],
                factory=self._tool_server_factory,
            )
        except ValueError as exc:
            return _failed(ClaudeSdkErrorCodes.INVALID_OPTIONS, str(exc))
        if host_tools is not None:
            prepared.warnings.extend(host_tools.warnings)
            prepared.warnings.extend(_host_tool_override_warnings(opts))
        sanitizer = RawSanitizer(
            secrets=prepared.secrets,
            redact=self._secrets.redact if self._secrets is not None else None,
            max_chars=self._max_raw,
        )
        guard = _guard_for(req, opts, prepared)
        hook_specs = [*prepared.bundle.hooks, *prepared.members.hooks]
        translator = MessageTranslator(
            backend_id=self.descriptor.id,
            model=req.agent.model,
            scrub=sanitizer.scrub,
            subagent_names=frozenset(prepared.members.agents),
            delegation_tools=frozenset(opts.delegation_tool_names),
        )
        bridge = PermissionBridge(
            guard=guard,
            unmatched=opts.unmatched_permission,
            port=sink if isinstance(sink, InteractivePort) else None,
            kinds=self._interaction_kinds,
            granted=frozenset(req.interactions.kinds if req.interactions else ()),
            question_tool=opts.question_tool,
            scrub=sanitizer.scrub,
            attribute=translator.target_for_agent,
            child_path=sink.child_path,
            actors=prepared.members.actors,
        )
        emitter = _Emitter(sink, sanitizer, prepared.members.actors)
        observers = CollectorRun(
            self._collectors,
            resolve_collector_settings(req.observe),
            clock=self._clock,
            redact=sanitizer.scrub,
            out=lambda event: emitter.emit_collected(event, translator.target_of),
            warn=lambda warning: sink.emit("log.warning", warning),
        )
        try:
            sdk_options, hook_warnings = self._build_options(
                req,
                opts,
                prepared,
                guard,
                observers,
                sink,
                sanitizer,
                bridge,
                hook_specs,
                host_tools,
            )
        except (TypeError, ValueError) as exc:
            return _failed(ClaudeSdkErrorCodes.INVALID_OPTIONS, sanitizer.mask_text(str(exc)))

        warnings = [
            *risky_option_warnings(sdk_options, self._env_policy, opts.sdk_options),
            *prepared.warnings,
            *hook_warnings,
        ]
        for warning in warnings:
            await sink.emit("log.warning", warning)
        await observers.flush_warnings()
        client = self._client_factory(sdk_options)
        cancelled = False
        try:
            await client.connect()
            await client.query(req.prompt)
            cancelled = await self._pump(client, translator, emitter, observers, cancel)
            for item in translator.finish(cancelled=cancelled):
                await emitter.emit(item, None)
        except Exception as exc:
            return _failed(
                ClaudeSdkErrorCodes.BACKEND_ERROR,
                sanitizer.mask_text(f"{type(exc).__name__}: {exc}"),
                usage=translator.usage,
                session=self._session(translator),
            )
        finally:
            with contextlib.suppress(Exception):
                await client.disconnect()
        return self._result(translator, cancelled)

    async def _pump(
        self,
        client: SdkClient,
        translator: MessageTranslator,
        emitter: _Emitter,
        observers: CollectorRun,
        cancel: CancelToken,
    ) -> bool:
        """응답을 끝(ResultMessage)까지 이벤트로 옮긴다. 도중에 취소되면 True."""

        async def consume() -> None:
            async for msg in client.receive_response():
                for item in translator.translate(msg):
                    await emitter.emit(item, msg)
                await observers.on_message(msg)
                for outcome in translator.take_subagent_results():
                    await emitter.subagent_result(outcome)

        consumer = asyncio.ensure_future(consume())
        waiter = asyncio.ensure_future(cancel.wait())
        try:
            await asyncio.wait({consumer, waiter}, return_when=asyncio.FIRST_COMPLETED)
            if consumer.done():
                consumer.result()
                return False
            # 취소: interrupt를 보내고 grace 안에 끝나기를 기다린다. 넘으면 끊는다(finally).
            with contextlib.suppress(Exception):
                await asyncio.wait_for(client.interrupt(), self._grace)
            done, _ = await asyncio.wait({consumer}, timeout=self._grace)
            if consumer in done and not consumer.cancelled():
                with contextlib.suppress(Exception):
                    consumer.result()
            return True
        finally:
            for task in (consumer, waiter):
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(BaseException):
                        await task

    def _result(self, translator: MessageTranslator, cancelled: bool) -> AgentResult:
        session = self._session(translator)
        usage = translator.usage or Usage()
        result = translator.result
        if cancelled:
            return AgentResult(
                status="cancelled", text=translator.final_text, usage=usage, session=session
            )
        if result is None:
            return _failed(
                ClaudeSdkErrorCodes.NO_RESULT,
                "SDK 응답이 결과 메시지 없이 끝났습니다",
                usage=translator.usage,
                session=session,
            )
        if result.is_error:
            message = "; ".join(result.errors or []) or result.result or result.subtype
            details = {
                "subtype": result.subtype,
                "stop_reason": result.stop_reason,
                "terminal_reason": result.terminal_reason,
                "api_error_status": result.api_error_status,
            }
            return _failed(
                ClaudeSdkErrorCodes.AGENT_ERROR,
                message,
                {k: v for k, v in details.items() if v is not None},
                usage=usage,
                session=session,
                text=translator.final_text,
            )
        return AgentResult(
            status="succeeded",
            text=translator.final_text,
            structured=result.structured_output,
            usage=usage,
            session=session,
        )

    def _session(self, translator: MessageTranslator) -> SessionRef | None:
        if not translator.session_id:
            return None
        return SessionRef(backend=self.descriptor.id, session_id=translator.session_id)

    # ------------------------------------------------------------ 옵션 매핑

    def _lookup(self, value: str) -> str:
        """`secret://` 참조면 해석하고, 아니면 그대로(노드가 이미 해석한 값)."""
        if not is_secret_ref(value):
            return value
        if self._secrets is None:
            raise SecretNotFoundError(value.removeprefix("secret://"))
        return self._secrets.resolve(value)

    def _prepare(self, req: AgentRequest, opts: ClaudeSdkBackendOptions) -> _Prepared:
        """비밀 해석·인증·묶음·서브에이전트 매핑(실행 전, I/O 없음)."""
        user_env = {key: self._lookup(value) for key, value in opts.env.items()}
        auth_env, warnings = _auth_env(opts.auth, user_env, self._lookup)
        bundle_options = BundleOptions(
            skill_name_template=opts.skill_name_template, rule_delivery=opts.rule_delivery
        )
        bundle = map_bundle(
            req.bundle, resolve=self._lookup, slots=self._slots, options=bundle_options
        )
        members = build_agent_definitions(
            req.subagents,
            resolve=self._lookup,
            files_template=opts.files_notice,
            slots=self._slots,
            options=bundle_options,
            skill_tool=opts.skill_tool,
        )
        rule_env = opts.rule_files_env if (bundle.rule_dirs or members.rule_dirs) else {}
        env = {
            **rule_env,
            **(opts.subagent_env if members.agents else {}),
            **user_env,
            **auth_env,
        }
        secrets = [
            *user_env.values(),
            *(v for v in auth_env.values() if v),
            *bundle.secret_values,
            *members.secret_values,
        ]
        warnings = [*warnings, *bundle.warnings, *members.warnings]
        extra = union(bundle.commands, members.commands)
        limit = list(req.limits.commands or []) if req.limits else []
        widened = [c for c in extra if c not in limit]
        if widened:
            warnings.append(
                LogWarningPayload(
                    message="실행 묶음(tools 칸)이 명령 허용 목록을 넓힙니다",
                    details={"option": "limits.commands", "added": widened},
                )
            )
        warnings.extend(_subagent_rule_warnings(req, opts, bundle, members))
        return _Prepared(
            env=env, secrets=secrets, bundle=bundle, members=members, warnings=warnings
        )

    def _build_options(
        self,
        req: AgentRequest,
        opts: ClaudeSdkBackendOptions,
        prepared: _Prepared,
        guard: ToolGuard,
        observers: CollectorRun,
        sink: BackendEventSink,
        sanitizer: RawSanitizer,
        bridge: PermissionBridge,
        hook_specs: list[HookSpec],
        host_tools: HostToolMapping | None = None,
    ) -> tuple[ClaudeAgentOptions, list[LogWarningPayload]]:
        """`AgentRequest` + 설정 → `ClaudeAgentOptions` (design §4.7·§R12.5·§R14.8·§2R.8 매핑).

        명령형 hook: 설치자가 허용하지 않았으면 걸지 않는다(묶음 변환이 이미 경고했다).
        `hook_delivery=callback`이면 훅 콜백으로, `settings`면 인라인 settings JSON으로 넘긴다.
        `observe.hook_probe`가 참이면 두 경로 모두 명령을 hook probe로 감싼다(실행 범위 검사는
        원래 명령으로). 꺼져 있으면(기본) 명령은 그대로다.
        """
        parent = self._environ if self._environ is not None else os.environ
        warnings: list[LogWarningPayload] = []
        callbacks: list[HookSpec] = []
        settings_json: str | None = None
        probe: HookProbePlan | None = None
        if hook_specs and self._allow_command_hooks:
            probe, found = plan_hook_probe(
                req.observe,
                run_folder=req.run_folder,
                run_context=req.run_context,
                probe_command=self._probe_command,
                folder_name=self._probe_folder,
            )
            warnings.extend(found)
            if opts.hook_delivery == "callback":
                callbacks = hook_specs
            else:
                settings_json, found = hook_settings_json(
                    hook_specs,
                    guard=guard,
                    default_timeout=opts.hook_timeout_seconds,
                    wrap_line=probe.line if probe is not None else None,
                )
                warnings.extend(found)
                if settings_json is not None and "settings" in opts.sdk_options:
                    warnings.append(
                        LogWarningPayload(
                            message="sdk_options.settings가 있어 hook settings를 덮어씁니다"
                            "(hook이 전달되지 않습니다)",
                            details={"option": "hook_delivery", "value": "settings"},
                        )
                    )
        hooks = self._hooks(guard, observers)
        if callbacks:
            env = hook_env(parent, self._env_policy.allows, req.cwd)
            for spec in callbacks:
                hooks.setdefault(cast("HookEvent", spec.event), []).append(
                    HookMatcher(
                        matcher=spec.matcher,
                        hooks=[
                            cast(
                                "Any",
                                command_hook(
                                    spec,
                                    guard=guard,
                                    runner=self._hook_runner,
                                    sink=sink,
                                    mask=sanitizer.mask_text,
                                    env=env,
                                    cwd=req.cwd,
                                    default_timeout=opts.hook_timeout_seconds,
                                    clock=self._clock,
                                    wrap=probe.argv if probe is not None else None,
                                ),
                            )
                        ],
                        timeout=spec.timeout_seconds or opts.hook_timeout_seconds,
                    )
                )
        options = build_sdk_options(
            req,
            opts,
            env=apply_env_policy(parent, self._env_policy, prepared.env),
            hooks=hooks,
            include_hook_events=observers.include_hook_events,
            can_use_tool=bridge,
            backend_id=self.descriptor.id,
            bundle=prepared.bundle,
            subagents=prepared.members,
            interactive=bridge.asks_questions or bridge.asks_permissions,
            ask_question=bridge.asks_questions,
            settings=settings_json,
            host_tools=host_tools,
        )
        return options, warnings

    def _hooks(
        self, guard: ToolGuard, observers: CollectorRun
    ) -> dict[HookEvent, list[HookMatcher]]:
        hooks: dict[HookEvent, list[HookMatcher]] = {
            "PreToolUse": [HookMatcher(matcher=None, hooks=[_guard_hook(guard)])]
        }
        for event in observers.hook_events():
            hooks.setdefault(cast("HookEvent", event), []).append(
                HookMatcher(matcher=None, hooks=[cast("Any", observers.hook_callback(event))])
            )
        return hooks


def build_sdk_options(
    req: AgentRequest,
    opts: ClaudeSdkBackendOptions,
    *,
    env: Mapping[str, str],
    hooks: Mapping[HookEvent, list[HookMatcher]] | None,
    can_use_tool: Any,
    include_hook_events: bool = False,
    backend_id: str = CLAUDE_SDK_BACKEND_ID,
    bundle: BundleMapping | None = None,
    subagents: SubagentMapping | None = None,
    interactive: bool = False,
    ask_question: bool = False,
    settings: str | None = None,
    host_tools: HostToolMapping | None = None,
) -> ClaudeAgentOptions:
    """요청·설정을 `ClaudeAgentOptions`로 옮긴다(I/O 없음).

    - `cwd` ← `req.cwd`, `add_dirs` ← `limits.directories`(cwd 제외) + `add_dirs` + 묶음 파일 폴더
    - `tools` ← 설정 `tools` 또는 `Agent.tools`의 도구 이름(괄호 규칙·`mcp__` 제외,
      비면 내장 도구 없음) + 묶음 `tools`, 묶음 금지 도구는 뺀다
    - `allowed_tools`(사전 승인) ← 설정 또는 `Agent.tools` + 묶음 + 서브에이전트 도구 규칙
      (금지가 우선), `disallowed_tools` ← 설정 + 묶음 + (네트워크가 allow가 아니면) `network_tools`
    - `system_prompt` ← `Agent.system_prompt` + 묶음 `instructions` + 파일 안내(문자열, 또는
      `system_prompt_mode=claude_code_append`면 preset + append)
    - `mcp_servers` ← 설정 + 묶음(같은 이름은 묶음이 이긴다)
    - `agents` ← 서브에이전트(`AgentDefinition`), 있으면 위임 도구(`delegation_tool`)를 허용
    - `permission_mode`, `setting_sources`, `strict_mcp_config`, `env`, `model`,
      `resume`(같은 백엔드의 `req.session`), `include_hook_events`(켜진 수집기가 원할 때),
      `forward_subagent_text`, `sdk_options` 덮어쓰기
    - 되묻기 도구(`question_tool`): `ask_question`이면 `tools`에 더하고(사전 승인은 하지 않는다 —
      콜백을 거쳐야 답이 들어간다), 아니면 `disallowed_tools`에 넣는다
    - `can_use_tool`: 권한 모드가 bypass가 아니고, `prompting_permission_modes`에 들거나
      `interactive`(상호작용 grant가 있음)일 때만 건다
    - skill(design §2R.8): `plugins` ← 묶음·서브에이전트의 플러그인 폴더(`{type: local, path}`),
      `skills` ← 묶음 skill 이름(플러그인 폴더가 있으면 빈 목록이어도 넘긴다 — 대상 skill이
      위임자 목록에 보이지 않게), 묶음 skill이 있으면 `skill_tool`을 `tools`에 더한다
    - 규칙 파일(`rule_delivery=files`): 규칙 폴더를 `add_dirs`에(환경변수는 `_prepare`가 넣는다)
    - `settings` ← 명령형 hook 인라인 JSON(`hook_delivery=settings`, 주면)
    - 플랫폼 도구(`host_tools`, design §5R.6): `mcp_servers[<서버>]` ← in-process SDK MCP 서버,
      `allowed_tools` ← `mcp__<서버>__<도구>`(금지 목록에 있으면 뺀다)

    Args:
        bundle: `map_bundle` 결과. None이면 `req.bundle`을 비밀 해석 없이 바꾼다.
        subagents: `build_agent_definitions` 결과. None이면 `req.subagents`를 비밀 해석 없이 바꾼다.
        interactive: 이 세션이 상호작용(되묻기·승인)을 열 수 있다.
        ask_question: 되묻기(질문) 상호작용을 열 수 있다.
    """
    agent = req.agent
    limits = req.limits
    if bundle is None:
        bundle = map_bundle(req.bundle)
    if subagents is None:
        subagents = build_agent_definitions(req.subagents, files_template=opts.files_notice)
    blocked = union(opts.disallowed_tools, bundle.disallowed_tools)
    delegation = (
        [opts.delegation_tool]
        if subagents.agents and without_disallowed([opts.delegation_tool], blocked)
        else []
    )
    if opts.tools == "claude_code":
        tools: Any = {"type": "preset", "preset": "claude_code"}
    else:
        base = list(opts.tools) if opts.tools is not None else _tool_names(agent.tools or [])
        asked = [opts.question_tool] if ask_question else []
        skill_tool = [opts.skill_tool] if bundle.skills and opts.skill_tool else []
        names = without_disallowed(
            union(base, _tool_names(bundle.tools), delegation, asked, skill_tool), blocked
        )
        tools = names
    allowed_base = opts.allowed_tools if opts.allowed_tools is not None else (agent.tools or [])
    allowed = without_disallowed(
        union(
            allowed_base,
            bundle.tools,
            subagents.allowed_rules if opts.subagent_tools_preapprove else [],
            delegation,
            host_tools.rules if host_tools is not None else [],
        ),
        blocked,
    )
    disallowed = list(blocked)
    if not ask_question and opts.question_tool not in disallowed:
        disallowed.append(opts.question_tool)
    if not (limits and limits.network == "allow"):
        disallowed += [t for t in opts.network_tools if t not in disallowed]
    add_dirs: list[str | Any] = [
        d for d in ((limits.directories or []) if limits else []) if d != req.cwd
    ]
    add_dirs += [
        d
        for d in union(
            opts.add_dirs,
            bundle.file_dirs,
            subagents.file_dirs,
            bundle.rule_dirs,
            subagents.rule_dirs,
        )
        if d not in add_dirs and d != req.cwd
    ]
    prompt_text = "\n\n".join(
        part
        for part in (
            agent.system_prompt,
            *bundle.instructions,
            files_notice(opts.files_notice, bundle.files),
        )
        if part
    )
    if opts.system_prompt_mode == "claude_code_append":
        system_prompt: Any = {"type": "preset", "preset": "claude_code"}
        if prompt_text:
            system_prompt["append"] = prompt_text
    else:
        system_prompt = prompt_text or None
    resume = (
        req.session.session_id
        if req.session is not None and req.session.backend == backend_id
        else None
    )
    permission_mode = opts.permission_mode
    effective_mode = opts.sdk_options.get("permission_mode", permission_mode)
    register = effective_mode != "bypassPermissions" and (
        interactive or effective_mode in opts.prompting_permission_modes
    )
    kwargs: dict[str, Any] = {
        "cwd": req.cwd,
        "model": agent.model,
        "system_prompt": system_prompt,
        "tools": tools,
        "allowed_tools": allowed,
        "disallowed_tools": disallowed,
        "permission_mode": permission_mode,
        "setting_sources": list(opts.setting_sources),
        "strict_mcp_config": opts.strict_mcp_config,
        "mcp_servers": {
            **opts.mcp_servers,
            **bundle.mcp_servers,
            **({host_tools.server: host_tools.config} if host_tools is not None else {}),
        },
        "agents": dict(subagents.agents) or None,
        "forward_subagent_text": opts.forward_subagent_text,
        "add_dirs": add_dirs,
        "env": dict(env),
        "include_partial_messages": opts.include_partial_messages,
        "include_hook_events": include_hook_events,
        "resume": resume,
        "hooks": dict(hooks) if hooks else None,
        "can_use_tool": can_use_tool if register else None,
    }
    optional = {
        "max_turns": opts.max_turns,
        "max_budget_usd": opts.max_budget_usd,
        "fallback_model": opts.fallback_model,
        "effort": opts.effort,
        "cli_path": opts.cli_path,
        "sandbox": opts.sandbox,
    }
    kwargs.update({k: v for k, v in optional.items() if v is not None})
    plugin_dirs = union(bundle.plugin_dirs, subagents.plugin_dirs)
    if plugin_dirs:
        kwargs["plugins"] = [{"type": "local", "path": d} for d in plugin_dirs]
        kwargs["skills"] = list(bundle.skills)
    if settings is not None:
        kwargs["settings"] = settings
    known = {f.name for f in dataclasses.fields(ClaudeAgentOptions)}
    for key, value in opts.sdk_options.items():
        if key in MANAGED_SDK_FIELDS:
            raise ValueError(f"sdk_options.{key}는 백엔드가 관리하므로 지정할 수 없습니다")
        if key not in known:
            raise ValueError(f"sdk_options.{key}는 ClaudeAgentOptions 필드가 아닙니다")
        kwargs[key] = value
    return ClaudeAgentOptions(**kwargs)


def risky_option_warnings(
    options: ClaudeAgentOptions,
    env_policy: EnvPolicy,
    sdk_options: Mapping[str, Any] | None = None,
) -> list[LogWarningPayload]:
    """안전 기본값을 뒤집는 설정에 대한 경고(실행은 막지 않는다 — 사용자의 명시적 선택이다)."""
    out: list[LogWarningPayload] = []
    if options.permission_mode == "bypassPermissions":
        out.append(
            LogWarningPayload(
                message="permission_mode=bypassPermissions: Claude Code 권한 검사와 can_use_tool이 "
                "꺼집니다(실행 범위 PreToolUse 검사는 유지)",
                details={"option": "permission_mode", "value": options.permission_mode},
            )
        )
    sources = list(options.setting_sources or [])
    if options.setting_sources is None or "user" in sources or "local" in sources:
        out.append(
            LogWarningPayload(
                message="setting_sources가 사용자/로컬 설정을 읽습니다(사용자 설정 격리 해제)",
                details={"option": "setting_sources", "value": options.setting_sources},
            )
        )
    if not options.strict_mcp_config:
        out.append(
            LogWarningPayload(
                message="strict_mcp_config=false: 지정하지 않은 MCP 서버 설정도 읽습니다",
                details={"option": "strict_mcp_config", "value": False},
            )
        )
    if env_policy.inherit == "all":
        out.append(
            LogWarningPayload(
                message="env_policy.inherit=all: 서버 환경변수 전체가 에이전트 프로세스로 "
                "전달됩니다",
                details={"option": "env_policy.inherit", "value": "all"},
            )
        )
    override_env = (sdk_options or {}).get("env")
    if isinstance(override_env, Mapping):
        out.append(
            LogWarningPayload(
                message="sdk_options.env가 환경 정책 결과를 통째로 대체합니다"
                "(허용 목록 밖 서버 환경변수가 다시 상속될 수 있음)",
                # 값은 싣지 않고 키 이름만.
                details={"option": "sdk_options.env", "keys": sorted(map(str, override_env))},
            )
        )
    return out


def _auth_env(
    auth: ClaudeSdkAuth | None,
    user_env: Mapping[str, str],
    lookup: Callable[[str], str],
) -> tuple[dict[str, str], list[LogWarningPayload]]:
    """인증 방식 → 명시 env. 값은 경고에 싣지 않는다."""
    if auth is None:
        return {}, []
    if auth.mode == "api_key":
        key = lookup(auth.api_key) if auth.api_key else user_env.get(auth.api_key_env, "")
        if not key:
            raise AuthMissingError(
                f"auth.mode=api_key인데 API 키가 없습니다(auth.api_key 또는 env.{auth.api_key_env})"
            )
        return {auth.api_key_env: key, auth.oauth_token_env: ""}, []
    env = {auth.api_key_env: ""}
    if auth.oauth_token:
        env[auth.oauth_token_env] = lookup(auth.oauth_token)
    warning = LogWarningPayload(
        message=SUBSCRIPTION_AUTH_WARNING,
        details={"option": "auth.mode", "value": "subscription"},
    )
    return env, [warning]


def _host_tool_override_warnings(opts: ClaudeSdkBackendOptions) -> list[LogWarningPayload]:
    """`sdk_options`가 플랫폼 도구 서버·사전 승인을 덮어쓰면 경고한다(덮어쓰기는 사용자 선택)."""
    keys = [k for k in ("mcp_servers", "allowed_tools") if k in opts.sdk_options]
    if not keys:
        return []
    return [
        LogWarningPayload(
            message="sdk_options가 플랫폼 도구 서버나 사전 승인을 덮어씁니다"
            "(위임 도구 등을 모델이 쓰지 못할 수 있습니다)",
            details={"option": "sdk_options", "keys": keys},
        )
    ]


def _subagent_rule_warnings(
    req: AgentRequest,
    opts: ClaudeSdkBackendOptions,
    bundle: BundleMapping,
    members: SubagentMapping,
) -> list[LogWarningPayload]:
    """서브에이전트 도구 규칙과 위임자 세션 사전 승인(`allowed_tools`)의 관계를 경고로 알린다.

    - `subagent_tools_preapprove=true`: 위임자 사전 승인을 넓히는 규칙(위임자에게도 적용됨).
    - 끔(기본): 위임자 사전 승인에 없는 대상 규칙
      (묻지 않는 모드에서 거부될 수 있음, SDK 동작 미확인).
    """
    base = opts.allowed_tools if opts.allowed_tools is not None else (req.agent.tools or [])
    extra = [r for r in members.allowed_rules if r not in union(base, bundle.tools)]
    if not extra:
        return []
    if opts.subagent_tools_preapprove:
        return [
            LogWarningPayload(
                message="서브에이전트 도구 규칙이 위임자 세션의 사전 승인(allowed_tools)을 넓힙니다"
                "(세션 하나라 위임자에게도 적용됨)",
                details={"option": "subagent_tools_preapprove", "added": extra},
            )
        ]
    return [
        LogWarningPayload(
            message="서브에이전트 도구 규칙을 위임자 세션 사전 승인에 넣지 않았습니다. "
            "묻지 않는 권한 모드(dontAsk 등)에서는 대상의 호출이 거부될 수 있습니다",
            details={"option": "subagent_tools_preapprove", "not_preapproved": extra},
        )
    ]


def _guard_for(req: AgentRequest, opts: ClaudeSdkBackendOptions, prepared: _Prepared) -> ToolGuard:
    """실행 범위 검사기: `limits` + 묶음의 명령(합집합) + 묶음 파일 폴더(검사 중일 때만 추가)."""
    limits = req.limits
    commands: list[str] | None = (
        list(limits.commands) if limits and limits.commands is not None else None
    )
    extra = union(prepared.bundle.commands, prepared.members.commands)
    if extra:
        commands = union(commands or [], extra)
    directories: list[str] | None
    if limits is not None and limits.directories is not None:
        directories = list(limits.directories)
    else:
        directories = [req.cwd] if req.cwd else None
    if directories is not None:
        directories = union(directories, prepared.bundle.file_dirs, prepared.members.file_dirs)
    return guard_from_limits(
        commands=commands,
        directories=directories,
        cwd=req.cwd,
        command_keys=opts.command_input_keys,
        path_keys=opts.path_input_keys,
    )


class _Emitter:
    """번역 결과를 sink로 낸다: 서브에이전트 대상이면 actor·하위 node_path를 붙인다."""

    def __init__(
        self,
        sink: BackendEventSink,
        sanitizer: RawSanitizer,
        actors: Mapping[str, str | None],
    ) -> None:
        self._sink = sink
        self._sanitizer = sanitizer
        self._actors = actors
        self._listener: SubagentResultListener | None = (
            sink if isinstance(sink, SubagentResultListener) else None
        )

    async def emit(self, item: Emission, msg: Any) -> None:
        raw = self._sanitizer(msg) if item.raw and msg is not None else None
        if item.target is None:
            await self._sink.emit(item.type, item.payload, raw=raw)
            return
        await self._sink.emit(
            item.type,
            item.payload,
            raw=raw,
            actor=self._actors.get(item.target),
            node_path=list(self._sink.child_path(item.target)),
        )

    async def emit_collected(
        self, event: CollectedEvent, target_of: Callable[[str | None], str | None]
    ) -> None:
        """관측 수집기 이벤트: raw를 정제하고 `parent_tool_use_id`로 서브에이전트에 귀속한다."""
        await self.emit(
            Emission(
                event.type,
                event.payload,
                raw=event.raw is not None,
                target=target_of(event.parent_tool_use_id),
            ),
            event.raw,
        )

    async def subagent_result(self, outcome: Any) -> None:
        if self._listener is None:
            return
        try:
            await self._listener.on_subagent_result(
                outcome.name,
                text=outcome.text,
                status=outcome.status,
                actor=self._actors.get(outcome.name),
                tool_use_id=outcome.tool_use_id,
            )
        except Exception as exc:
            await self._sink.emit(
                "log.warning",
                LogWarningPayload(
                    message="서브에이전트 결과를 전달하지 못했습니다",
                    details={"subagent": outcome.name, "error": type(exc).__name__},
                ),
            )


def _tool_names(rules: Iterable[str]) -> list[str]:
    """`["Read", "Bash(git:*)", "mcp__s__t"]` → `["Bash", "Read"]` (괄호 규칙 제거, MCP 제외)."""
    names = {r.split("(", 1)[0].strip() for r in rules}
    return sorted(n for n in names if n and not n.startswith("mcp__"))


def _guard_hook(guard: ToolGuard) -> Any:
    async def hook(
        input_data: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        data = cast("Mapping[str, Any]", input_data)
        tool_input = data.get("tool_input")
        reason = guard.check(
            str(data.get("tool_name", "")),
            tool_input if isinstance(tool_input, Mapping) else {},
        )
        if reason is None:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"실행 범위 제한: {reason}",
            }
        }

    return hook


def _drop_line(_line: str) -> None:
    """연결 테스트 CLI stderr를 버린다(서버 로그에 원문이 남지 않게)."""


def _failed(
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
    *,
    usage: Usage | None = None,
    session: SessionRef | None = None,
    text: str = "",
) -> AgentResult:
    return AgentResult(
        status="failed",
        text=text,
        usage=usage or Usage(),
        session=session,
        error=ErrorInfo(code=code, message=message, details=dict(details or {})),
    )
