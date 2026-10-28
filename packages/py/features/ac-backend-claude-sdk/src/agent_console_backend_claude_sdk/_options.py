"""claude-sdk 백엔드 설정(`Agent.backend_options`)과 관측 옵션(`AgentRequest.observe`) 스키마.

기본값은 안전한 쪽이다(design §4.7): 권한 모드 `dontAsk`, 프로젝트 설정만 읽기,
`--strict-mcp-config`, 에이전트 `tools`에 없는 내장 도구는 쓸 수 없음.
모델 id는 여기에 없다 — `Agent.model`에서 온다.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent_console_contracts import x_path, x_ui

type PermissionModeName = Literal[
    "default", "acceptEdits", "plan", "bypassPermissions", "dontAsk", "auto"
]
type SettingSourceName = Literal["user", "project", "local"]

CLAUDE_SDK_BACKEND_ID = "claude-agent-sdk"
"""기본 디스크립터 id(entry point 이름과 같다).
기본 수집기(X7)의 `descriptor.backend`도 이 값이다."""

DEFAULT_OBSERVED_HOOK_EVENTS: tuple[str, ...] = (
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "UserPromptSubmit",
    "SubagentStart",
    "SubagentStop",
    "PreCompact",
    "Stop",
    "Notification",
)
"""관측 훅 기본 이벤트(design §8.2 "SDK 관찰 훅"). `observe.hook_events`로 바꾼다."""

MANAGED_SDK_FIELDS: frozenset[str] = frozenset({"cwd", "hooks", "can_use_tool", "resume", "agents"})
"""`sdk_options`로 덮어쓸 수 없는 `ClaudeAgentOptions` 필드(백엔드가 관리)."""


DEFAULT_DELEGATION_TOOL = "Agent"
"""서브에이전트 위임 도구 이름(SDK 문서: `tool_use` 블록 이름. 이전 이름 `Task`)."""

DEFAULT_DELEGATION_TOOL_NAMES: tuple[str, ...] = ("Agent", "Task")
"""위임 도구 호출로 알아볼 이름(SDK 버전마다 `Agent`/`Task`)."""

DEFAULT_HOST_TOOL_SERVER = "agent-console"
"""플랫폼 도구(`AgentRequest.host_tools`)를 담는 in-process MCP 서버 이름 기본값
(옵션 스키마 기본값). 모델이 부르는 이름은 `mcp__<서버>__<도구>`다."""

DEFAULT_SUBAGENT_ENV: dict[str, str] = {
    # 서브에이전트가 다시 서브에이전트를 만들지 못하게(위임 방식 sdk-subagents max_depth=1).
    "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1",
    # 서브에이전트를 전경에서 돌려 결과가 위임 도구 결과로 같은 턴 안에 돌아오게.
    "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
    # 등록하지 않은 기본 서브에이전트(general-purpose 등)로 위임하지 못하게.
    "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",
}
"""`subagents`가 있을 때 CLI 하위 프로세스에 넣는 환경변수(Claude Code 문서의 변수).
설정 `subagent_env`로 교체한다."""

DEFAULT_FILES_NOTICE = "다음 참고 파일이 제공되었다. 필요하면 읽어서 활용한다.\n{files}"

DEFAULT_SKILL_TOOL = "Skill"
"""skill을 부르는 내장 도구 이름. 묶음에 skill이 있으면 `tools`에 더한다."""
"""실행 묶음 `files` 칸의 파일 목록을 지침 끝에 붙일 때 쓰는 템플릿(`{files}` = `- 경로` 줄들)."""


def _project_only() -> list[SettingSourceName]:
    return ["project"]


class ClaudeSdkAuth(BaseModel):
    """에이전트 실행에 쓸 인증 방식입니다. 키·토큰은 비밀 참조(secret://이름)로만 적습니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # 값은 `secret://이름` 참조로 둔다. 참조는 노드가 해석해 넘기거나, 남아 있으면 백엔드가
    # 주입한 해석기로 푼다.
    #
    # - `api_key`(선택): `api_key`(또는 `env`의 같은 변수)를 `api_key_env`로 넘기고,
    #   구독 토큰 변수는 비운다. 키가 없으면 실행하지 않는다(`auth_missing`).
    # - `subscription`(기본, 5.2R.79): Claude Code 로그인(구독) 자격을 쓴다. `api_key_env`를
    #   빈 값으로 덮어써 API 키가 끼어들지 않게 하고, `oauth_token`을 주면 `oauth_token_env`로
    #   넘긴다(없으면 CLI가 HOME 아래 로그인 자격을 읽는다). Anthropic 문서상 Agent SDK 기반
    #   앱에는 API 키 사용이 안내되므로 사용은 본인 책임이다. 설치자 `allow_subscription_auth`
    #   (기본 켜짐)가 켜져야 동작하고, 꺼져 있으면 검증 오류
    #   `backend.subscription_auth_disabled`·실행 거부다. 켜져 있으면 실행마다 강화된
    #   `log.warning`을 낸다. 토큰은 사용자 자신의 것을 비밀 저장소 참조로만 읽는다
    #   (이 패키지에는 토큰을 받아 두거나 저장하는 경로가 없다).

    model_config = ConfigDict(extra="forbid")

    mode: Literal["api_key", "subscription"] = Field(
        default="subscription",
        title="인증 방식",
        description="기본은 구독 로그인(Claude Code 로그인, 본인 책임)이고 API 키도 고를 수 "
        "있습니다. 구독은 설치자 설정에서 허용돼 있어야 합니다(기본 허용).",
        json_schema_extra=x_ui(
            enum_labels={"api_key": "API 키", "subscription": "구독 로그인"},
            tier="basic",
            when="구독 대신 API 키로 실행하고 싶을 때 api_key로 바꾸세요.",
        ),
    )
    api_key: str | None = Field(
        default=None,
        title="API 키",
        description="API 키 방식에서 쓸 키입니다. secret://이름으로만 적습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="다른 API 키를 쓰거나 키를 바꿨을 때 바꾸세요.",
            example="secret://anthropic-api-key",
        ),
    )
    oauth_token: str | None = Field(
        default=None,
        title="구독 토큰",
        description="구독 방식에서 쓸 토큰(secret://이름)입니다. 비우면 CLI 로그인 정보를 씁니다.",
        json_schema_extra=x_ui(tier="advanced", example="secret://claude-oauth-token"),
    )
    api_key_env: str = Field(
        default="ANTHROPIC_API_KEY",
        title="API 키 변수 이름",
        description="API 키를 넘길 환경 변수 이름입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    oauth_token_env: str = Field(
        default="CLAUDE_CODE_OAUTH_TOKEN",
        title="구독 토큰 변수 이름",
        description="구독 토큰을 넘길 환경 변수 이름입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class ClaudeSdkBackendOptions(BaseModel):
    """Claude Agent SDK(에이전트 실행 도구)로 에이전트를 돌릴 때 쓰는 설정입니다."""

    # 에이전트의 `Agent.backend_options` 형식. 비밀 값(`env`)은 노드가 `secret://…`를 해석해 넘긴다.
    # (docstring은 설정 폼 머리말로 보이므로 개발자 메모는 이 주석에 둔다.)

    model_config = ConfigDict(extra="forbid")

    permission_mode: PermissionModeName = Field(
        default="dontAsk",
        title="권한 모드",
        description="도구 사용 권한 모드입니다. 기본 dontAsk는 미리 허용한 것 밖을 거부합니다.",
        json_schema_extra=x_ui(
            enum_labels={
                "default": "기본(매번 묻기)",
                "acceptEdits": "파일 수정은 허용",
                "plan": "계획만 세우기",
                "bypassPermissions": "모두 허용",
                "dontAsk": "미리 허용한 것만",
                "auto": "자동 판단",
            },
            tier="basic",
            when=(
                "에이전트가 파일 수정 등을 묻지 않고 하게 하거나(acceptEdits) 매번 묻게 하고 "
                "싶을 때 바꾸세요."
            ),
        ),
    )
    setting_sources: list[SettingSourceName] = Field(
        default_factory=_project_only,
        title="읽을 설정 파일",
        description=(
            "읽을 Claude Code 설정 출처입니다. 기본은 project만 읽어 개인 설정과 섞이지 않습니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="내 Claude Code 개인 설정(user)도 함께 쓰고 싶을 때 바꾸세요.",
            group="files",
            group_title="설정·파일",
            enum_labels={
                "user": "개인 설정(user)",
                "project": "프로젝트 설정(project)",
                "local": "프로젝트 개인 설정(local)",
            },
        ),
    )
    strict_mcp_config: bool = Field(
        default=True,
        title="MCP 서버만 사용",
        description="여기와 리소스로 준 MCP(외부 도구 서버)만 쓰고 다른 곳의 서버는 무시합니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="Claude Code에 따로 등록한 서버도 쓰고 싶을 때 끄세요.",
            group="tools",
            group_title="도구",
        ),
    )
    mcp_servers: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        title="MCP 서버",
        description=(
            "직접 적는 MCP(외부 도구 서버) 설정입니다(이름 → 설정). 보통은 리소스로 붙입니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="리소스로 만들지 않고 이 에이전트에만 서버를 붙이고 싶을 때 적으세요.",
            group="tools",
            group_title="도구",
        ),
    )
    tools: list[str] | Literal["claude_code"] | None = Field(
        default=None,
        title="내장 도구",
        description=(
            "쓸 수 있는 내장 도구입니다. 비우면 에이전트의 도구, claude_code면 기본 도구 "
            "전체입니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="Claude Code 기본 도구 전체(claude_code)를 쓰게 하고 싶을 때 바꾸세요.",
            group="tools",
            group_title="도구",
        ),
    )
    allowed_tools: list[str] | None = Field(
        default=None,
        title="묻지 않고 허용",
        description="묻지 않고 허용할 도구 규칙입니다. 비우면 에이전트의 도구를 씁니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="자주 쓰는 도구를 매번 묻지 않고 허용하고 싶을 때 적으세요.",
            group="tools",
            group_title="도구",
        ),
    )
    disallowed_tools: list[str] = Field(
        default_factory=list,
        title="금지 도구",
        description="이 실행 방식에서 쓰지 못하게 할 도구 이름입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="이 실행 방식에서 특정 도구를 막고 싶을 때 더하세요.",
            group="tools",
            group_title="도구",
        ),
    )
    network_tools: list[str] = Field(
        default_factory=lambda: ["WebFetch", "WebSearch"],
        title="네트워크 도구",
        description="네트워크를 허용하지 않았을 때 막을 도구 이름입니다.",
        json_schema_extra=x_ui(tier="advanced", group="limits", group_title="실행 범위 검사"),
    )
    command_input_keys: list[str] = Field(
        default_factory=lambda: ["command"],
        title="명령 입력 키",
        description="허용 명령 목록으로 검사할 도구 입력 이름입니다.",
        json_schema_extra=x_ui(tier="advanced", group="limits", group_title="실행 범위 검사"),
    )
    path_input_keys: list[str] = Field(
        default_factory=lambda: ["file_path", "path", "notebook_path"],
        title="경로 입력 키",
        description="허용 폴더로 검사할 도구 입력 이름입니다.",
        json_schema_extra=x_ui(tier="advanced", group="limits", group_title="실행 범위 검사"),
    )
    unmatched_permission: Literal["deny", "allow"] = Field(
        default="deny",
        title="물을 곳 없는 권한 요청",
        description=(
            "권한을 물어야 하는데 답할 연결이 없을 때 거부(deny)할지 허용(allow)할지입니다."
        ),
        json_schema_extra=x_ui(
            enum_labels={"deny": "거부", "allow": "허용"},
            tier="advanced",
            when="승인 연결 없이도 권한 요청을 허용해야 할 때만 allow로 바꾸세요(위험할 수 있음).",
            group="permission",
            group_title="권한",
        ),
    )
    prompting_permission_modes: list[str] = Field(
        default_factory=lambda: ["default", "acceptEdits", "plan"],
        title="묻는 권한 모드",
        description="권한을 사용자에게 물을 수 있는 모드입니다. 이 모드면 승인 연결이 필요합니다.",
        json_schema_extra=x_ui(tier="advanced", group="permission", group_title="권한"),
    )
    question_tool: str = Field(
        default="AskUserQuestion",
        title="되묻기 도구",
        description="사용자에게 되묻는 도구 이름입니다. 되묻기 연결이 있을 때만 씁니다.",
        json_schema_extra=x_ui(tier="advanced", group="tools", group_title="도구"),
    )
    system_prompt_mode: Literal["custom", "claude_code_append"] = Field(
        default="custom",
        title="시스템 프롬프트 방식",
        description=(
            "에이전트 지침만 쓸지(custom) Claude Code 기본 지침 뒤에 "
            "붙일지(claude_code_append)입니다."
        ),
        json_schema_extra=x_ui(
            enum_labels={
                "custom": "직접 쓴 글만",
                "claude_code_append": "Claude Code 기본에 덧붙이기",
            },
            tier="basic",
            when=(
                "Claude Code의 기본 도구 사용 요령을 함께 쓰고 싶을 때 claude_code_append로 "
                "바꾸세요."
            ),
        ),
    )
    include_partial_messages: bool = Field(
        default=True,
        title="글 흘려 보기",
        description="답이 써지는 동안 글을 조금씩 받아 화면에 보입니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="글이 조금씩 보이는 것이 필요 없을 때 끄세요."
        ),
    )
    max_turns: int | None = Field(
        default=None,
        ge=1,
        title="최대 턴 수",
        description="한 번 실행에서 모델이 주고받는 최대 횟수입니다. 비우면 제한이 없습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="에이전트가 끝없이 도구를 부르며 오래 돌 때 줄이세요.",
            example=20,
            unit="턴",
        ),
    )
    max_budget_usd: float | None = Field(
        default=None,
        gt=0,
        title="최대 비용(USD)",
        description="한 번 실행의 비용 상한입니다. 비우면 제한이 없습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="한 번 실행에 쓸 비용을 묶어 두고 싶을 때 정하세요.",
            example=1.0,
            unit="USD",
        ),
    )
    fallback_model: str | None = Field(
        default=None,
        title="대체 모델",
        description="주 모델을 쓸 수 없을 때 쓸 모델입니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="주 모델이 붐비거나 막혀 실행이 실패할 때 정하세요.", example=None
        ),
    )
    effort: str | None = Field(
        default=None,
        title="생각 노력",
        description="모델이 얼마나 깊게 생각할지입니다(예: low, medium, high).",
        json_schema_extra=x_ui(
            tier="advanced", when="답이 얕으면 높이고, 느리거나 비싸면 낮추세요.", example="medium"
        ),
    )
    add_dirs: list[str] = Field(
        default_factory=list,
        title="추가 폴더",
        description="허용 폴더 밖에 더 읽게 할 폴더입니다.",
        # x-path: 프로젝트 실행에서 경로 지킴 대상(design §PI.5 X33, ac-projects.outside_paths).
        json_schema_extra={
            **x_path("directory"),
            **x_ui(
                tier="advanced",
                when="에이전트가 작업 폴더 밖의 문서를 읽어야 할 때 더하세요.",
                group="files",
                group_title="설정·파일",
            ),
        },
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        title="환경 변수",
        description=(
            "실행할 때 넣을 환경 변수입니다. 비밀 값은 secret://이름으로 적고 기록에서 가려집니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="에이전트가 쓰는 도구가 환경 변수(키·토큰 등)를 요구할 때 적으세요.",
        ),
    )
    cli_path: str | None = Field(
        default=None,
        title="CLI 경로",
        description="쓸 Claude Code CLI 경로입니다. 비우면 함께 설치된 것을 씁니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="직접 설치한 다른 버전의 Claude Code를 쓰고 싶을 때 적으세요.",
            example="/usr/local/bin/claude",
        ),
    )
    sandbox: dict[str, Any] | None = Field(
        default=None,
        title="샌드박스",
        description="Claude Code 샌드박스 설정을 그대로 넘깁니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    auth: ClaudeSdkAuth | None = Field(
        default=None,
        title="인증",
        description=(
            "구독(기본, 본인 책임)이나 API 키 중 어떻게 로그인할지입니다. 칸을 열면 구독이 "
            "기본이고 API 키도 고를 수 있습니다. 아예 비우면 환경 변수·서버 정책을 따릅니다."
        ),
        json_schema_extra=x_ui(
            tier="basic", when="API 키나 구독 중 무엇으로 로그인할지 정할 때 바꾸세요."
        ),
    )
    forward_subagent_text: bool = Field(
        default=True,
        title="서브에이전트 글 보기",
        description="서브에이전트가 쓴 글도 받아 그 에이전트의 메시지로 보입니다.",
        json_schema_extra=x_ui(tier="advanced", group="subagents", group_title="서브에이전트"),
    )
    delegation_tool: str = Field(
        default=DEFAULT_DELEGATION_TOOL,
        title="위임 도구",
        description="서브에이전트가 있을 때 더할 위임 도구 이름입니다.",
        json_schema_extra=x_ui(tier="advanced", group="subagents", group_title="서브에이전트"),
    )
    delegation_tool_names: list[str] = Field(
        default_factory=lambda: list(DEFAULT_DELEGATION_TOOL_NAMES),
        title="위임 도구 이름들",
        description="위임 호출로 알아볼 도구 이름입니다.",
        json_schema_extra=x_ui(tier="advanced", group="subagents", group_title="서브에이전트"),
    )
    host_tool_server: str = Field(
        default=DEFAULT_HOST_TOOL_SERVER,
        min_length=1,
        pattern=r"^[A-Za-z0-9_-]+$",
        title="플랫폼 도구 서버 이름",
        description=(
            "위임 도구 등 플랫폼 도구를 담는 MCP(외부 도구 서버) 이름입니다. 다른 서버와 "
            "겹치면 안 됩니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="다른 서버 이름과 겹친다는 오류가 날 때만 바꾸세요.",
            group="subagents",
            group_title="서브에이전트",
        ),
    )
    subagent_tools_preapprove: bool = Field(
        default=False,
        title="서브에이전트 도구 미리 허용",
        description=(
            "서브에이전트 도구 규칙을 위임자에게도 미리 허용합니다. 넓어지므로 기본은 끔입니다."
        ),
        json_schema_extra=x_ui(tier="advanced", group="subagents", group_title="서브에이전트"),
    )
    subagent_env: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_SUBAGENT_ENV),
        title="서브에이전트 환경 변수",
        description=(
            "서브에이전트가 있을 때 넣는 환경 변수입니다. 환경 변수에 같은 키가 있으면 그쪽이 "
            "이깁니다."
        ),
        json_schema_extra=x_ui(tier="advanced", group="subagents", group_title="서브에이전트"),
    )
    files_notice: str | None = Field(
        default=DEFAULT_FILES_NOTICE,
        title="참고 파일 안내",
        description="붙인 파일 목록을 지침 끝에 알릴 문구입니다({files}). 비우면 붙이지 않습니다.",
        json_schema_extra=x_ui(tier="advanced", group="files", group_title="설정·파일"),
    )
    skill_tool: str = Field(
        default=DEFAULT_SKILL_TOOL,
        title="skill 도구",
        description="skill을 부르는 도구 이름입니다. skill을 붙이면 자동으로 더합니다.",
        json_schema_extra=x_ui(tier="advanced", group="files", group_title="설정·파일"),
    )
    skill_name_template: str = Field(
        default="{plugin}:{skill}",
        title="skill 이름 형식",
        description="묶음 안 skill의 이름 형식입니다({plugin}·{skill}).",
        json_schema_extra=x_ui(tier="advanced", group="files", group_title="설정·파일"),
    )
    rule_delivery: Literal["instructions", "files"] = Field(
        default="instructions",
        title="규칙 전달 방식",
        description="경로 조건 규칙을 지침에 붙일지(instructions) 규칙 파일로 둘지(files)입니다.",
        json_schema_extra=x_ui(
            enum_labels={"instructions": "지침 글로 전달", "files": "파일로 전달"},
            tier="advanced",
            group="files",
            group_title="설정·파일",
        ),
    )
    rule_files_env: dict[str, str] = Field(
        default_factory=lambda: {"CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD": "1"},
        title="규칙 파일 환경 변수",
        description="규칙을 파일로 전달할 때 넣는 환경 변수입니다.",
        json_schema_extra=x_ui(tier="advanced", group="files", group_title="설정·파일"),
    )
    hook_delivery: Literal["callback", "settings"] = Field(
        default="callback",
        title="hook 전달 방식",
        description=(
            "명령형 hook을 실행 범위 검사 뒤 돌릴지(callback) CLI가 직접 돌릴지(settings)입니다."
        ),
        json_schema_extra=x_ui(
            enum_labels={"callback": "검사 뒤 직접 실행", "settings": "CLI가 실행"},
            tier="advanced",
            group="hooks",
            group_title="hook",
        ),
    )
    hook_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        title="hook 시간 제한",
        description="hook(도구 실행 전후에 도는 명령)에 시간 제한을 적지 않았을 때 쓰는 값입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="hook 명령이 오래 걸려 중간에 끊길 때 늘리세요.",
            unit="초",
            group="hooks",
            group_title="hook",
        ),
    )
    sdk_options: dict[str, Any] = Field(
        default_factory=dict,
        title="기타 SDK 옵션",
        description=(
            "위에 없는 Claude Agent SDK(에이전트 실행 라이브러리) 옵션을 이름 그대로 넘깁니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced", when="위 항목에 없는 옵션이 꼭 필요할 때만 쓰세요."
        ),
    )

    @field_validator("host_tool_server")
    @classmethod
    def _no_double_underscore(cls, value: str) -> str:
        if "__" in value:
            raise ValueError(
                "host_tool_server에는 '__'를 쓸 수 없습니다(mcp__<서버>__<도구> 구분자)"
            )
        return value

    @model_validator(mode="after")
    def _auth_matches_env(self) -> Self:
        if self.auth is not None:
            if self.auth.mode == "subscription" and self.env.get(self.auth.api_key_env):
                raise ValueError(
                    f"auth.mode=subscription인데 env에 {self.auth.api_key_env}가 있습니다"
                )
            if (
                self.auth.mode == "api_key"
                and self.auth.api_key
                and self.auth.api_key_env in (self.env)
            ):
                raise ValueError(
                    f"auth.api_key와 env.{self.auth.api_key_env}를 함께 줄 수 없습니다"
                )
        return self


class ObserveOptions(BaseModel):
    """`AgentRequest.observe`의 옛 키 형식(design §8.3 Phase 1 범위, 읽기 호환용).

    4R.8부터 백엔드는 이 모델 대신 `collectors.resolve_collector_settings`로 `observe.collectors`와
    옛 키를 함께 해석한다(옛 키 `hooks`→`sdk-hooks`, `mcp`→`mcp-calls`,
    `hook_events`→`sdk-hooks` 설정 `events`. 둘 다 있으면 `collectors`가 이긴다).
    """

    model_config = ConfigDict(extra="ignore")

    hooks: bool = Field(
        default=False,
        description="hook.* 이벤트: SDK 관찰 훅 콜백 + CLI 훅 실행(include_hook_events).",
    )
    mcp: bool = Field(default=False, description="mcp.* 이벤트: 서버 상태, mcp__ 도구 호출 쌍.")
    hook_events: list[str] = Field(
        default_factory=lambda: list(DEFAULT_OBSERVED_HOOK_EVENTS),
        description="관측 콜백을 걸 SDK 훅 이벤트 이름.",
    )


def claude_sdk_config_schema() -> dict[str, Any]:
    """`BackendDescriptor.config_schema`로 쓰는 JSON Schema."""
    return ClaudeSdkBackendOptions.model_json_schema()
