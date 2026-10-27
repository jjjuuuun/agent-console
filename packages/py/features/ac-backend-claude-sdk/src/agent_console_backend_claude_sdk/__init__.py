"""agent-console-backend-claude-sdk: Claude Agent SDK 실행 백엔드 어댑터(X3, design §7.4).

공개 API:
    - ``ClaudeSdkBackend``: X3 `ExecutionBackend` 구현(entry point
      `agent_console.backends:claude-agent-sdk`). SDK 클라이언트는 ``client_factory``로 주입한다.
    - ``SdkClient``·``ClientFactory``: 주입 인터페이스(테스트 가짜용)
    - 설정: ``ClaudeSdkBackendOptions``(`Agent.backend_options`), ``ObserveOptions``
      (`AgentRequest.observe`의 옛 키 형식, 읽기 호환), ``claude_sdk_config_schema``,
      ``build_sdk_options``
    - 관측 수집기(X7, 4R.8): 하위 모듈 ``agent_console_backend_claude_sdk.collectors``
      (``ClaudeSdkCollector`` 프로토콜, ``CollectorContext``, 기본 수집기 `sdk-hooks`·`mcp-calls`,
      entry point `agent_console.collectors` 로딩, ``resolve_collector_settings``). 이슈 코드
      ``COLLECTOR_ISSUES``
    - sink가 ``agent_console_runtime.SubagentResultListener``(`on_subagent_result`)를 만족하면
      서브에이전트 결과를 알린다(위임 방식이 대상 답변을 내는 데 쓴다). 하위 node_path는
      `BackendEventSink.child_path`
    - 부품(단독 사용 가능): ``MessageTranslator``·``Emission``·``SubagentOutcome``·
      ``delegation_result_text``·``usage_from_sdk``·``split_mcp_name`` (SDK 메시지 → 이벤트),
      ``map_bundle``·``BundleMapping``·``BundleError``(실행 묶음 칸 → SDK 재료),
      ``build_agent_definitions``·``SubagentMapping``(서브에이전트 → ``AgentDefinition``),
      ``ToolGuard``·``guard_from_limits``(실행 범위 검사),
      ``RawSanitizer``·``to_jsonable``(raw 정제),
      ``EnvPolicy``·``apply_env_policy``(하위 프로세스 환경 정책), ``risky_option_warnings``
    - 상호작용(1R.30, design §R14.8): ``PermissionBridge``(`can_use_tool` ↔ `request_input`),
      ``InteractionKindMap``(여는 종류 이름 = 데이터), ``ClaudeSdkBackend.validate_settings``
      (선택 훅, `interaction.no_path`), 상수 ``DEFAULT_QUESTION_TOOL``·
      ``DEFAULT_PROMPTING_PERMISSION_MODES``, ``INTERACTION_ISSUES``
    - 설정 형식: ``ClaudeSdkAuth``(인증 방식: 기본 subscription(본인 책임, 설치자
      ``allow_subscription_auth`` 기본 켜짐) / api_key도 선택 가능). 이슈 코드 ``AUTH_ISSUES``,
      문장 ``SUBSCRIPTION_AUTH_DISABLED_MESSAGE``·``SUBSCRIPTION_AUTH_WARNING``(3R.29, E-13)
    - 상수: ``CLAUDE_SDK_BACKEND_ID``, ``ClaudeSdkErrorCodes``, ``DEFAULT_OBSERVED_HOOK_EVENTS``,
      ``RESOURCE_SLOTS``, ``DEFAULT_SUBAGENT_ENV``, ``DEFAULT_DELEGATION_TOOL(_NAMES)``,
      ``DEFAULT_FILES_NOTICE``, ``COMMAND_HOOK_SLOTS``, ``SUBAGENT_SLOTS``, ``HOOKS_DISABLED_NOTE``
    - skill·rule·hook 전달(2R.12, design §2R.8): ``BundleOptions``(skill 이름 형식·규칙 전달 방식),
      ``HookSpec``·``HookRunner``·``HookProcess``·``subprocess_runner``·``command_hook``·
      ``hook_settings_json``·``hook_env``·``hook_decision``·``parse_hooks``
      (명령형 hook 콜백·settings),
      설치자 설정 ``allow_command_hooks``(기본 꺼짐)
    - hook probe 감싸기(4R.9, design §4R.7, F-16): 유효 관측 설정 `observe.hook_probe`가 참이면
      전달하는 명령형 hook을 `agent-console-hook-probe`로 감싼다(선택 의존, 추가 기능 `hook-probe`).
      설치자 설정 ``hook_probe_command``·``hook_probe_folder``, 기록 폴더
      `AgentRequest.run_folder/hook-probe`. 부품 ``plan_hook_probe``·``HookProbePlan``·
      ``hook_probe_enabled``·``hook_probe_note``, 묶음 미리보기 훅
      ``ClaudeSdkBackend.preview_notes``(info ``HOOK_PROBE_ISSUES.WRAPPED``),
      상수 ``DEFAULT_HOOK_PROBE_FOLDER``
    - 플랫폼 도구(5R.10, design §5R.6): `AgentRequest.host_tools`를 in-process SDK MCP 서버
      (`create_sdk_mcp_server`)로 모델에게 준다(`capabilities.host_tools = true`). 서버 이름은
      `backend_options.host_tool_server`(기본 ``DEFAULT_HOST_TOOL_SERVER``), 모델이 부르는 이름
      ``host_tool_rule``(`mcp__<서버>__<도구>`)은 `allowed_tools`에 들어간다. 부품
      ``build_host_tool_server``·``HostToolMapping``·``sdk_tool_handler``·``sdk_tool_server``·
      ``ToolServerFactory``(생성자 ``tool_server_factory``로 주입), 상수
      ``HOST_TOOL_NAME_PATTERN``·``MODEL_TOOL_NAME_LIMIT``
    - 준비 상태·연결 테스트(5.2R.68, ux-overhaul §15.8): ``ClaudeSdkBackend.status``(정적 점검,
      모델 호출 없음)·``probe``(짧은 실제 호출, 막힌 경우 호출 없이 거부). 디스크립터
      ``capabilities.status/probe = true``·``probe_cost_note``(``PROBE_COST_NOTE``). 설치자
      설정 ``readiness``(``ClaudeSdkReadinessOptions``·문구 ``ClaudeSdkReadinessTexts``·
      ``FixLink``), 상태 이름 ``ReadinessStates``, 실패 사유 ``ProbeReasonCodes``·분류
      ``PROBE_CATEGORIES``. 부품(단독 사용): ``assess_readiness``·``ReadinessAssessment``·
      ``classify_probe_messages``·``classify_probe_error``·``ProbeOutcome``·``find_claude_cli``·
      ``expand_path``
    - 구독 로그인(5.2R.82, ux-overhaul §15.9): ``ClaudeSdkBackend.start_login``·``logout``
      (선택 능력, ``capabilities.login/logout``, 방법 ``CLI_LOGIN_METHOD_ID`` = ``cli-login``).
      `claude auth login`을 PTY로 중계하고 `claude auth status` 종료 코드로 판정한다.
      설치자 설정 ``login``
      (``ClaudeSdkLoginOptions``·규칙 ``ClaudeSdkLoginRules``·문구 ``ClaudeSdkLoginTexts``·
      ``PtySize``), 사유 ``LoginReasonCodes``. PTY는 선택 추가 기능 ``login``
      (`agent-console-pty-session`), 없으면 능력 없음. 부품: ``login_env``·``allowed_open_url``·
      ``safe_rule_compile``·``verify_login``·``parse_auth_method``·``run_command``·
      ``resolve_writes``·``writes_lines``·``env_warnings``, ``ClaudeLoginSupport``·``PtySupport``·
      ``detect_pty``. 드라이버 ``ClaudeCliLoginDriver``는 하위 모듈
      ``agent_console_backend_claude_sdk.login_driver``(PTY 필요)
"""

from agent_console_backend_claude_sdk._backend import (
    AUTH_ISSUES,
    COLLECTOR_ISSUES,
    DEFAULT_CANCEL_GRACE_SECONDS,
    HOOKS_DISABLED_NOTE,
    INTERACTION_ISSUES,
    PROBE_COST_NOTE,
    SUBSCRIPTION_AUTH_DISABLED_MESSAGE,
    SUBSCRIPTION_AUTH_WARNING,
    AuthMissingError,
    ClaudeSdkBackend,
    ClaudeSdkErrorCodes,
    ClaudeSdkInstallOptions,
    ClientFactory,
    SdkClient,
    build_sdk_options,
    risky_option_warnings,
)
from agent_console_backend_claude_sdk._bundle import (
    COMMAND_HOOK_SLOTS,
    RESOURCE_SLOTS,
    SUBAGENT_SLOTS,
    BundleError,
    BundleMapping,
    BundleOptions,
    map_bundle,
)
from agent_console_backend_claude_sdk._env import (
    DEFAULT_ENV_ALLOW,
    EnvPolicy,
    apply_env_policy,
)
from agent_console_backend_claude_sdk._guard import ALLOW_ALL, ToolGuard, guard_from_limits
from agent_console_backend_claude_sdk._hooks import (
    BLOCK_EXIT_CODE,
    DEFAULT_HOOK_TIMEOUT_SECONDS,
    HookProcess,
    HookRunner,
    HookSpec,
    command_hook,
    hook_decision,
    hook_env,
    hook_settings_json,
    parse_hooks,
    subprocess_runner,
)
from agent_console_backend_claude_sdk._host_tools import (
    HOST_TOOL_NAME_PATTERN,
    MODEL_TOOL_NAME_LIMIT,
    HostToolMapping,
    ToolServerFactory,
    build_host_tool_server,
    host_tool_rule,
    sdk_tool_handler,
    sdk_tool_server,
)
from agent_console_backend_claude_sdk._interact import (
    DEFAULT_PROMPTING_PERMISSION_MODES,
    DEFAULT_QUESTION_TOOL,
    InteractionKindMap,
    PermissionBridge,
)
from agent_console_backend_claude_sdk._login import (
    CLI_LOGIN_METHOD_ID,
    DEFAULT_ALLOWED_URL_HOSTS,
    DEFAULT_LOGIN_ENV_CLEAR,
    DEFAULT_LOGIN_ENV_INHERIT,
    DEFAULT_LOGIN_RULES,
    DEFAULT_LOGIN_WRITES,
    ClaudeSdkLoginOptions,
    ClaudeSdkLoginRules,
    ClaudeSdkLoginTexts,
    CommandResult,
    LoginReasonCodes,
    PtySize,
    VerifyOutcome,
    allowed_open_url,
    env_warnings,
    login_env,
    parse_auth_method,
    resolve_writes,
    run_command,
    safe_rule_compile,
    verify_login,
    writes_lines,
)
from agent_console_backend_claude_sdk._login_support import (
    ClaudeLoginSupport,
    PtySupport,
    detect_pty,
)
from agent_console_backend_claude_sdk._options import (
    CLAUDE_SDK_BACKEND_ID,
    DEFAULT_DELEGATION_TOOL,
    DEFAULT_DELEGATION_TOOL_NAMES,
    DEFAULT_FILES_NOTICE,
    DEFAULT_HOST_TOOL_SERVER,
    DEFAULT_OBSERVED_HOOK_EVENTS,
    DEFAULT_SUBAGENT_ENV,
    ClaudeSdkAuth,
    ClaudeSdkBackendOptions,
    ObserveOptions,
    claude_sdk_config_schema,
)
from agent_console_backend_claude_sdk._probe import (
    DEFAULT_HOOK_PROBE_FOLDER,
    HOOK_PROBE_ISSUES,
    HookProbePlan,
    hook_probe_enabled,
    hook_probe_note,
    plan_hook_probe,
)
from agent_console_backend_claude_sdk._readiness import (
    PROBE_CATEGORIES,
    ClaudeSdkReadinessOptions,
    ClaudeSdkReadinessTexts,
    FixLink,
    ProbeOutcome,
    ProbeReasonCodes,
    ReadinessAssessment,
    ReadinessStates,
    assess_readiness,
    classify_probe_error,
    classify_probe_messages,
    expand_path,
    find_claude_cli,
)
from agent_console_backend_claude_sdk._redact import (
    DEFAULT_MAX_RAW_CHARS,
    RawSanitizer,
    to_jsonable,
)
from agent_console_backend_claude_sdk._subagents import (
    SubagentMapping,
    build_agent_definitions,
)
from agent_console_backend_claude_sdk._translate import (
    Emission,
    MessageTranslator,
    SubagentOutcome,
    delegation_result_text,
    split_mcp_name,
    usage_from_sdk,
)

__all__ = [
    "ALLOW_ALL",
    "AUTH_ISSUES",
    "BLOCK_EXIT_CODE",
    "CLAUDE_SDK_BACKEND_ID",
    "CLI_LOGIN_METHOD_ID",
    "COLLECTOR_ISSUES",
    "COMMAND_HOOK_SLOTS",
    "DEFAULT_ALLOWED_URL_HOSTS",
    "DEFAULT_CANCEL_GRACE_SECONDS",
    "DEFAULT_DELEGATION_TOOL",
    "DEFAULT_DELEGATION_TOOL_NAMES",
    "DEFAULT_ENV_ALLOW",
    "DEFAULT_FILES_NOTICE",
    "DEFAULT_HOOK_PROBE_FOLDER",
    "DEFAULT_HOOK_TIMEOUT_SECONDS",
    "DEFAULT_HOST_TOOL_SERVER",
    "DEFAULT_LOGIN_ENV_CLEAR",
    "DEFAULT_LOGIN_ENV_INHERIT",
    "DEFAULT_LOGIN_RULES",
    "DEFAULT_LOGIN_WRITES",
    "DEFAULT_MAX_RAW_CHARS",
    "DEFAULT_OBSERVED_HOOK_EVENTS",
    "DEFAULT_PROMPTING_PERMISSION_MODES",
    "DEFAULT_QUESTION_TOOL",
    "DEFAULT_SUBAGENT_ENV",
    "HOOKS_DISABLED_NOTE",
    "HOOK_PROBE_ISSUES",
    "HOST_TOOL_NAME_PATTERN",
    "INTERACTION_ISSUES",
    "MODEL_TOOL_NAME_LIMIT",
    "PROBE_CATEGORIES",
    "PROBE_COST_NOTE",
    "RESOURCE_SLOTS",
    "SUBAGENT_SLOTS",
    "SUBSCRIPTION_AUTH_DISABLED_MESSAGE",
    "SUBSCRIPTION_AUTH_WARNING",
    "AuthMissingError",
    "BundleError",
    "BundleMapping",
    "BundleOptions",
    "ClaudeLoginSupport",
    "ClaudeSdkAuth",
    "ClaudeSdkBackend",
    "ClaudeSdkBackendOptions",
    "ClaudeSdkErrorCodes",
    "ClaudeSdkInstallOptions",
    "ClaudeSdkLoginOptions",
    "ClaudeSdkLoginRules",
    "ClaudeSdkLoginTexts",
    "ClaudeSdkReadinessOptions",
    "ClaudeSdkReadinessTexts",
    "ClientFactory",
    "CommandResult",
    "Emission",
    "EnvPolicy",
    "FixLink",
    "HookProbePlan",
    "HookProcess",
    "HookRunner",
    "HookSpec",
    "HostToolMapping",
    "InteractionKindMap",
    "LoginReasonCodes",
    "MessageTranslator",
    "ObserveOptions",
    "PermissionBridge",
    "ProbeOutcome",
    "ProbeReasonCodes",
    "PtySize",
    "PtySupport",
    "RawSanitizer",
    "ReadinessAssessment",
    "ReadinessStates",
    "SdkClient",
    "SubagentMapping",
    "SubagentOutcome",
    "ToolGuard",
    "ToolServerFactory",
    "VerifyOutcome",
    "allowed_open_url",
    "apply_env_policy",
    "assess_readiness",
    "build_agent_definitions",
    "build_host_tool_server",
    "build_sdk_options",
    "classify_probe_error",
    "classify_probe_messages",
    "claude_sdk_config_schema",
    "command_hook",
    "delegation_result_text",
    "detect_pty",
    "env_warnings",
    "expand_path",
    "find_claude_cli",
    "guard_from_limits",
    "hook_decision",
    "hook_env",
    "hook_probe_enabled",
    "hook_probe_note",
    "hook_settings_json",
    "host_tool_rule",
    "login_env",
    "map_bundle",
    "parse_auth_method",
    "parse_hooks",
    "plan_hook_probe",
    "resolve_writes",
    "risky_option_warnings",
    "run_command",
    "safe_rule_compile",
    "sdk_tool_handler",
    "sdk_tool_server",
    "split_mcp_name",
    "subprocess_runner",
    "to_jsonable",
    "usage_from_sdk",
    "verify_login",
    "writes_lines",
]
