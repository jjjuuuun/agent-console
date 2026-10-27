"""사용자 정의 엔티티(데이터): Agent, Graph(팀 구성), WorkspaceSettings, 설정 층.

설계: design §2.2, §R1, §R2.

노드 `config`, `attributes`, `backend_options`는 `dict[str, Any]`이며
계약은 그 내용을 해석하지 않는다.
계약에는 특정 노드 타입·엣지 타입·백엔드·리소스 종류 이름이 없다.
"""

from typing import Any, ClassVar, Literal

from pydantic import (
    ConfigDict,
    Field,
    field_validator,
)
from pydantic.config import JsonDict, JsonValue

from agent_console_contracts._base import (
    DefinitionModel,
    JsonObject,
    NonEmptyStr,
    OmitWhenUnsetModel,
    Slug,
)
from agent_console_contracts.common import X_UI, Endpoint, PortDef, Position, x_ui
from agent_console_contracts.logs import LogSettings
from agent_console_contracts.resources import ResourceAttachment

type JoinRule = Literal["any", "all"]
"""노드 활성화 규칙(design §4.3)."""

type NetworkPolicy = Literal["allow", "deny"]


_X_MERGE = "x-merge"
"""병합 규칙 주석 키. 값은 병합 전략 이름(문자열, 전략 표는 ac-settings)."""

_X_WIDEN = "x-widen"
"""넓힘 판정 주석 키. 아래 층 값이 위 층보다 넓어지면 화면이 경고한다.
값은 판정 규칙 이름 또는 객체(해석은 ac-settings)."""


class Limits(DefinitionModel):
    """에이전트가 쓸 디렉터리·명령·네트워크. 비운 항목은 상위 설정이나 안전한 기본값을 따른다."""

    # design §4.7, §R2.3. 설정 층 사이 병합은 교체(AgentSettings.limits의 x-merge replace)이고,
    # 아래 층이 위 층보다 넓히면 경고한다(필드별 x-widen). 사용자는 settings_merge로 규칙을 바꾼다.
    # title·description은 설정 폼에 그대로 보이는 문구다(필드 포함).
    model_config = ConfigDict(title="실행 범위")

    directories: list[str] | None = Field(
        default=None,
        title="허용 디렉터리",
        description=(
            "에이전트가 읽고 쓸 수 있는 폴더입니다. {workspace}는 작업 공간 경로로 바뀝니다."
        ),
        json_schema_extra={
            _X_WIDEN: "path_subset",
            **x_ui(
                tier="basic",
                when="에이전트가 작업 폴더 밖의 파일을 다뤄야 할 때 더하세요.",
                example=["{workspace}"],
            ),
        },
    )
    commands: list[str] | None = Field(
        default=None,
        title="허용 명령",
        description=(
            "에이전트가 실행할 수 있는 명령입니다. 비우면 공통·팀 설정 값이나 안전한 "
            "기본값을 씁니다."
        ),
        json_schema_extra={
            _X_WIDEN: "subset",
            **x_ui(
                tier="basic",
                when=(
                    "에이전트가 테스트·빌드 같은 명령을 돌려야 하거나, 위험한 명령을 막고 싶을 "
                    "때 바꾸세요."
                ),
                example=["git", "pytest"],
            ),
        },
    )
    network: NetworkPolicy | None = Field(
        default=None,
        title="네트워크",
        description="외부 네트워크 접근을 허용(allow)할지 막을지(deny) 정합니다.",
        json_schema_extra={
            _X_WIDEN: {"kind": "order", "order": ["deny", "allow"]},
            **x_ui(
                enum_labels={"allow": "허용", "deny": "막기"},
                tier="basic",
                when="에이전트가 웹 검색·다운로드를 해야 하거나 외부 접속을 막고 싶을 때 바꾸세요.",
            ),
        },
    )


# ---------------------------------------------------------------- 설정 층(design §R2)

type SessionPolicy = Literal["continue", "fresh"]
"""대화의 다음 턴에서 노드 세션을 이어 쓸지(continue) 새로 시작할지(fresh)."""

type BusyPolicy = Literal["queue", "reject"]
"""대화가 실행 중일 때 새 메시지 처리."""

type ReplyDisplay = Literal["separate", "merged", "final_only"]
"""답변 여러 개 표시 방식(design §R2.2)."""

type ChatTitlePolicy = Literal["first_message", "manual"]

type SendKey = Literal["enter", "mod_enter"]
"""채팅 전송 키. enter = Enter 전송·Shift+Enter 줄바꿈, mod_enter = Ctrl/Cmd+Enter 전송."""

type OnTimeout = Literal["expire", "cancel_run"]
"""상호작용 응답 대기 한도를 넘었을 때."""

type DefinitionScope = Literal["project", "shared"]
"""새 정의의 범위. project = 지금 고른 프로젝트 전용, shared = 공용."""

PROJECT_FIELD_DESCRIPTION = (
    "이 정의가 속한 프로젝트입니다. 비우면 공용이라 모든 프로젝트에서 보입니다."
)

_ID_DESCRIPTION = "가리킬 때 쓰는 고유 이름입니다. 파일 이름으로도 쓰며 영문·숫자·-·_만 씁니다."
_SCHEMA_VERSION_DESCRIPTION = "파일 형식 번호입니다. 직접 바꾸지 않습니다."
_LABELS_DESCRIPTION = "찾기·거르기에 쓰는 꼬리표입니다."
_SETTINGS_MERGE_DESCRIPTION = (
    "설정 항목마다 공통·팀·에이전트 설정을 합치는 방법을 바꿉니다(예: /limits → intersect)."
)
_SETTINGS_MERGE_WHEN = (
    "에이전트·팀 설정이 공통 설정 값을 덮어쓰지 않고 좁히거나 더하게 하려면 바꾸세요."
)
_ATTRIBUTES_DESCRIPTION = "다른 도구가 읽는 자유 속성입니다. 보통은 비워 둡니다."

type QueueAfterRestart = Literal["ask", "run", "drop"]
"""서버 재시작 뒤 남은 대기열 처리. 동작 모드(종류 id가 아님)라 고정 어휘다.
ask = 모든 항목을 멈춤(held)으로 두고 채팅에서 묻기, run = 순서대로 실행, drop = 지움."""


class CollectorSetting(DefinitionModel):
    """관측 수집기 하나를 켤지와 그 설정입니다. 비운 항목은 공통 설정·팀 설정 값을 따릅니다."""

    # X7, design §4R.3.

    model_config = ConfigDict(title="관측 수집기")

    enabled: bool | None = Field(
        default=None,
        title="사용",
        description="이 수집기로 기록할지 정합니다. 비우면 공통·팀 설정의 값을 따릅니다.",
        json_schema_extra=x_ui(
            tier="basic", when="이 수집기의 기록이 필요하거나 너무 많을 때 바꾸세요."
        ),
    )
    config: JsonObject | None = Field(
        default=None,
        title="수집기 설정",
        description="수집기마다 정한 추가 설정입니다. 비우면 수집기 기본값을 씁니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="수집기가 기록할 범위를 좁히거나 넓히고 싶을 때 바꾸세요."
        ),
    )


class ObserveSettings(DefinitionModel):
    """실행 중에 hook(도구 실행 전후에 도는 명령)·MCP(외부 도구 서버) 호출 등을 기록합니다.

    비운 항목은 공통 설정·팀 설정 값을 따릅니다.
    """

    # design §R4.4·§4R.3. 수집 항목은 collectors(수집기 id → 설정)로 정한다. 옛 키 hooks·mcp·
    # hook_events는 읽기 호환이다(백엔드가 기본 수집기의 enabled·config.events로 읽고, 둘 다 있으면
    # collectors가 이긴다).
    model_config = ConfigDict(title="관측 설정")

    collectors: dict[str, CollectorSetting] | None = Field(
        default=None,
        title="관측 수집기",
        description=(
            "수집기마다 켜고 끄며 설정합니다. 고를 수 있는 수집기는 실행 백엔드가 알려 줍니다."
        ),
        json_schema_extra=x_ui(
            tier="basic", when="실행 중 무엇을 기록할지 고르고 싶을 때 바꾸세요."
        ),
    )
    hook_probe: bool | None = Field(
        default=None,
        title="hook 입출력 전체 기록",
        description=(
            "hook(도구 실행 전후에 도는 명령)의 입력·출력·결정·시간까지 기록합니다. 기본은 "
            "꺼짐입니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced", when="hook이 왜 막았는지 따져 보고 싶을 때 켜세요."
        ),
    )
    hooks: bool | None = Field(
        default=None,
        title="hook 이벤트 기록",
        description=(
            "이전 형식입니다. hook(도구 실행 전후에 도는 명령) 실행을 기록합니다. 새 설정은 관측 "
            "수집기를 씁니다."
        ),
        json_schema_extra=x_ui(tier="advanced"),
    )
    mcp: bool | None = Field(
        default=None,
        title="MCP 호출 기록",
        description=(
            "이전 형식입니다. MCP(외부 도구 서버) 호출을 기록합니다. 새 설정은 관측 수집기를 "
            "씁니다."
        ),
        json_schema_extra=x_ui(tier="advanced"),
    )
    hook_events: list[str] | None = Field(
        default=None,
        title="기록할 hook 이벤트",
        description=(
            "기록할 hook(도구 실행 전후에 도는 명령) 이벤트 이름입니다. 비우면 실행 백엔드 기본 "
            "목록입니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="특정 hook 이벤트만 기록하고 싶을 때 바꾸세요.",
            example=["PreToolUse", "PostToolUse"],
        ),
    )


class AgentSettings(DefinitionModel):
    """에이전트가 실행될 때 쓰는 설정입니다.

    비운 항목은 더 넓은 설정(공통 설정, 팀 설정, 에이전트 순)에서 정한 값을 따릅니다.
    """

    # 한 층의 에이전트 설정. 상속 순서는 공통 → 팀 구성 → 에이전트 → 노드.

    # design §R2.2. 생략 = 상속: 필드를 생략하면 위 층 값을 쓴다. 값이 있으면(null·빈 목록 포함)
    # 이 층에서 정한 것이다. 구분은 model_fields_set에 남으므로 저장·전송은
    # model_dump(exclude_unset=True)로 한다. 층 병합은 ac-settings·ac-teams가 한다.
    # 필드별 병합 규칙 기본값은 스키마 주석 x-merge(없으면 스칼라·목록 = 교체, 객체 = 병합).
    # 클래스 문서는 설정 폼에 그대로 보이는 문구다.
    model_config = ConfigDict(title="에이전트 설정")

    backend: str | None = Field(
        default=None,
        title="실행 백엔드",
        description=(
            "에이전트를 실제로 돌릴 실행 방식입니다. 비우면 팀 설정이나 공통 설정의 값을 씁니다."
        ),
        # 예시 없음(null): 값은 설치된 실행 백엔드 목록에서 고른다(계약은 이름을 모른다).
        json_schema_extra=x_ui(
            tier="advanced",
            when="이 에이전트만 다른 실행 방식(예: 체험용)으로 돌리고 싶을 때 바꾸세요.",
            example=None,
        ),
    )
    model: str | None = Field(
        default=None,
        title="모델",
        description=(
            "에이전트가 쓸 모델입니다. 목록에서 고르거나 직접 입력합니다. 비우면 팀·공통 "
            "설정 값입니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="더 빠르거나 더 똑똑한 모델이 필요할 때, 또는 비용을 줄이고 싶을 때 바꾸세요.",
            example=None,
        ),
    )
    system_prompt: str | None = Field(
        default=None,
        title="시스템 프롬프트",
        description="에이전트의 기본 지침입니다. 비우면 팀 설정이나 공통 설정의 값을 씁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="에이전트의 말투·역할·지켜야 할 규칙을 정하고 싶을 때 바꾸세요.",
            example="당신은 코드 리뷰어입니다. 변경의 위험부터 짚어 주세요.",
        ),
    )
    tools: list[str] | None = Field(
        default=None,
        title="도구",
        description=(
            "에이전트가 쓸 수 있는 도구 이름입니다. 비우면 실행 백엔드의 기본 도구를 씁니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="에이전트가 쓸 수 있는 도구를 좁히거나 넓히고 싶을 때 바꾸세요.",
            example=["Read", "Grep"],
        ),
    )
    disallowed_tools: list[str] | None = Field(
        default=None,
        title="금지 도구",
        description="에이전트가 쓰지 못하게 막을 도구 이름입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="특정 도구(예: 명령 실행)를 절대 쓰지 못하게 하고 싶을 때 바꾸세요.",
            example=["Bash"],
        ),
    )
    limits: Limits | None = Field(
        default=None,
        title="실행 범위",
        description=(
            "에이전트가 쓸 폴더·명령·네트워크 범위입니다. 여기서 정하면 공통·팀 설정의 "
            "범위를 통째로 바꿉니다."
        ),
        json_schema_extra={
            _X_MERGE: "replace",
            **x_ui(
                tier="advanced",
                when="에이전트가 건드려도 되는 폴더·명령·네트워크를 정하고 싶을 때 바꾸세요.",
            ),
        },
    )
    observe: ObserveSettings | None = Field(
        default=None,
        title="관측",
        description=(
            "실행 중 hook(도구 실행 전후에 도는 명령)·MCP(외부 도구 서버) 호출을 기록할지 정합니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced", when="에이전트가 무엇을 했는지 자세히 따져 보고 싶을 때 켜세요."
        ),
    )
    resources: list[ResourceAttachment] | None = Field(
        default=None,
        title="리소스",
        description=(
            "붙인 지침·파일·외부 도구 서버(MCP) 등입니다. 공통·팀 설정에서 붙인 것과 함께 쓰입니다."
        ),
        json_schema_extra={
            _X_MERGE: "keyed_attachments",
            **x_ui(
                tier="basic", when="에이전트에게 지침·참고 파일·외부 도구를 주고 싶을 때 붙이세요."
            ),
        },
    )
    working_directory: str | None = Field(
        default=None,
        title="작업 폴더",
        description=(
            "에이전트가 일하는 폴더입니다. 비우면 프로젝트나 서버 설정의 작업 폴더를 씁니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="에이전트마다 다른 저장소·폴더에서 일하게 하고 싶을 때 바꾸세요.",
            example="/home/me/projects/app",
        ),
    )
    prompt_template: str | None = Field(
        default=None,
        title="입력 합치기 형식",
        description=(
            "넘겨받은 값을 프롬프트로 합치는 틀입니다. {inputs}·{message}·{node}를 쓰고, "
            "비우면 {inputs} 그대로입니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="앞 단계 결과 앞뒤에 고정 문장을 붙이고 싶을 때 바꾸세요.",
            example="다음 자료를 검토하세요:\n{inputs}",
            group="prompt",
            group_title="프롬프트 조립",
        ),
    )
    # design §R3.2-4(1R.35). 기본값은 여기(계약 데이터)에만 있다.
    # 노드는 값이 없으면 이 기본값을 쓴다.
    prompt_input_template: str | None = Field(
        default="{source}: {value}",
        title="값별 형식(여러 값)",
        description=(
            "값이 여러 개 들어올 때 값 하나를 적는 틀입니다. {source}(보낸 노드 이름)·{value}·"
            "{index} 등을 씁니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="여러 결과를 받을 때 누가 보낸 것인지 표시를 바꾸고 싶을 때 바꾸세요.",
            example="[{index}] {source}\n{value}",
            group="prompt",
            group_title="프롬프트 조립",
        ),
    )
    prompt_single_input_template: str | None = Field(
        default="{value}",
        title="값별 형식(값 하나)",
        description="값이 하나만 들어올 때 쓰는 틀입니다. 변수는 여러 값일 때와 같습니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="결과가 하나일 때도 앞에 설명을 붙이고 싶을 때 바꾸세요.",
            group="prompt",
            group_title="프롬프트 조립",
        ),
    )
    prompt_input_separator: str | None = Field(
        default="\n\n",
        title="값 구분자",
        description="여러 값을 이을 때 사이에 넣는 문자열입니다. 기본은 빈 줄 하나입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="여러 결과 사이를 줄 대신 다른 구분 문구로 나누고 싶을 때 바꾸세요.",
            group="prompt",
            group_title="프롬프트 조립",
        ),
    )
    session: SessionPolicy | None = Field(
        default=None,
        title="세션 이어 쓰기",
        description=(
            "다음 턴에 대화를 이어 쓸지(continue) 매번 새로 시작할지(fresh) 정합니다. 비우면 "
            "이어 씁니다."
        ),
        json_schema_extra=x_ui(
            enum_labels={"continue": "이어서 쓰기", "fresh": "새로 시작"},
            tier="advanced",
            when="턴마다 앞 내용을 잊고 새로 답하게 하고 싶을 때 fresh로 바꾸세요.",
        ),
    )
    backend_options: JsonObject | None = Field(
        default=None,
        title="백엔드 옵션",
        description=(
            "고른 실행 백엔드가 따로 받는 설정입니다. 비밀 값은 secret://이름으로만 적습니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="실행 방식의 세부 동작(턴 수·비용 한도·권한 등)을 조정하고 싶을 때 바꾸세요.",
        ),
    )


class _AgentIdentity(DefinitionModel):
    """에이전트 정의의 식별·표시 필드(설정이 아닌 것). `Agent` 필드 순서를 위해 따로 둔다."""

    kind: Literal["agent"] = "agent"
    id: Slug = Field(
        title="id", description=_ID_DESCRIPTION, json_schema_extra=x_ui(tier="advanced")
    )
    schema_version: int = Field(
        default=1,
        title="형식 버전",
        description=_SCHEMA_VERSION_DESCRIPTION,
        json_schema_extra=x_ui(tier="advanced"),
    )
    name: NonEmptyStr = Field(
        title="이름",
        description="에이전트를 부르는 이름입니다. 팀 그래프와 채팅에 이 이름이 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="목록이나 팀 그래프에서 알아보기 쉬운 이름으로 바꾸고 싶을 때 바꾸세요.",
            example="조사 팀원",
        ),
    )
    description: str = Field(
        default="",
        title="설명",
        description="언제 이 에이전트에게 맡길지 적습니다. 위임할 때 대상을 고르는 단서가 됩니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="다른 에이전트가 이 에이전트에게 일을 잘못 맡기거나 안 맡길 때 고치세요.",
            example="코드 변경을 검토해야 할 때 맡깁니다.",
        ),
    )
    role: str = Field(
        default="",
        title="역할",
        description="이 에이전트가 하는 일을 한 줄로 적습니다. 목록과 노드에 함께 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="목록에서 이 에이전트가 무엇을 하는지 한눈에 보이게 하고 싶을 때 바꾸세요.",
            example="코드 리뷰어",
        ),
    )
    labels: list[str] = Field(
        default_factory=list,
        title="라벨",
        description=_LABELS_DESCRIPTION,
        json_schema_extra=x_ui(tier="advanced", example=["review"]),
    )
    attributes: JsonObject = Field(
        default_factory=dict,
        title="기타 속성",
        description=_ATTRIBUTES_DESCRIPTION,
        json_schema_extra=x_ui(tier="advanced"),
    )
    # 0.8.0(design §UX-P.4). 생략 = 공용. 지정하지 않으면 직렬화하지 않는다(정의 해시 안정).
    project: Slug | None = Field(
        default=None,
        title="프로젝트",
        description=PROJECT_FIELD_DESCRIPTION,
        json_schema_extra=x_ui(
            tier="basic",
            when="이 정의를 특정 프로젝트에서만 보이게 하고 싶을 때 고르세요.",
            example=None,
        ),
    )


class Agent(AgentSettings, _AgentIdentity, OmitWhenUnsetModel):
    """에이전트 하나입니다. 이름·역할과 실행 설정을 담습니다.

    비운 설정은 공통 설정·팀 설정 값을 따릅니다.
    """

    # 에이전트 정의(`<workspace>/agents/<id>.yaml`). 설정 필드는 `AgentSettings`와 같다
    # (에이전트 층, 생략 = 상속).

    model_config = ConfigDict(title="에이전트")

    _OMIT_WHEN_UNSET: ClassVar[tuple[tuple[str, ...], ...]] = (("project",),)


# ---------------------------------------------------------------- 화면 배치(layout, graph-edges §5)
# layout은 그림을 그리기 위한 데이터다. 실행 엔진·검증·버전 해시가 읽지 않는다
# (E-3, position과 같음).
# 모든 키 선택, 생략 = 상속. 값은 문자열·숫자이며 범위·개수 제한을 계약에 두지 않는다(편집기 규칙,
# graph-edges §5.2). 손으로 고친 YAML이 저장소에서 읽기 실패가 되지 않게 하기 위해서다.
# 모르는 하위 키는 보존한다(DefinitionModel, extra=allow).


class NodeLayout(DefinitionModel):
    """노드 하나의 화면 배치입니다.

    비우면 팀 배치, 편집기 설정, 노드 종류 기본값 순으로 따릅니다.
    """

    # 생략 = 상속(그래프 → 사용자 설정 → 노드 타입 힌트).

    direction: str | None = Field(
        default=None,
        title="방향",
        description="노드의 입력→출력 방향입니다(lr, tb, rl, bt, auto). 비우면 팀 설정을 따릅니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="이 노드만 입력·출력 방향을 다르게 그리고 싶을 때 바꾸세요.",
            example="lr",
        ),
    )
    ports: dict[str, str] | None = Field(
        default=None,
        title="포트 위치",
        description=(
            "포트를 노드의 어느 면에 둘지입니다(키 in:이름·out:이름, 값 "
            "left·right·top·bottom·auto)."
        ),
        json_schema_extra=x_ui(tier="advanced", example={"in:input": "left"}),
    )


class EdgeLayout(DefinitionModel):
    """연결선 하나의 화면 배치입니다. 비우면 팀 배치와 편집기 설정을 따릅니다."""

    # 생략 = 상속. 범위는 편집기가 정한다.

    shape: str | None = Field(
        default=None,
        title="모양",
        description="연결선 모양 이름입니다(예: bezier, smoothstep). 비우면 팀 설정을 따릅니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="이 연결선만 모양을 다르게 그리고 싶을 때 바꾸세요.",
            example="smoothstep",
        ),
    )
    radius: float | None = Field(
        default=None,
        title="둥글기",
        description="꺾이는 모서리를 얼마나 둥글게 할지입니다(0~24).",
        json_schema_extra=x_ui(tier="advanced", example=8, unit="px"),
    )
    bend: float | None = Field(
        default=None,
        title="꺾임 위치",
        description="경유점이 없을 때 선이 꺾이는 위치를 비율로 정합니다(0~1).",
        json_schema_extra=x_ui(tier="advanced", example=0.5),
    )
    waypoints: list[Position] | None = Field(
        default=None,
        title="경유점",
        description="연결선이 지나갈 캔버스 위 점입니다(최대 16개).",
        json_schema_extra=x_ui(tier="advanced"),
    )
    label_t: float | None = Field(
        default=None,
        title="라벨 위치",
        description="라벨을 선의 어느 지점에 둘지 비율로 정합니다(0.1~0.9).",
        json_schema_extra=x_ui(tier="advanced", example=0.5),
    )
    label_offset: Position | None = Field(
        default=None,
        title="라벨 어긋남",
        description="선에서 떨어뜨린 라벨의 가로·세로 거리입니다.",
        json_schema_extra=x_ui(tier="advanced", unit="px"),
    )


class GraphUiLayout(DefinitionModel):
    """이 팀의 화면 배치 기본값입니다(노드 방향·연결선 모양).

    비우면 편집기 설정, 노드·연결 종류 기본값 순으로 따릅니다.
    """

    # `Graph.ui.layout`의 형식(문서화 모델). `Graph.ui`는 열린 객체로 두고 이 키만 이 형식을 따른다.
    # 생략 = 상속(사용자 설정 → 디스크립터 힌트 → 내장 기본값).

    direction: str | None = Field(
        default=None,
        title="기본 방향",
        description=(
            "이 팀의 기본 노드 방향입니다(lr, tb, rl, bt, auto). 비우면 편집기 설정을 따릅니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="팀 그래프 전체를 위→아래 등 다른 방향으로 그리고 싶을 때 바꾸세요.",
            example="lr",
        ),
    )
    edge_shape: str | None = Field(
        default=None,
        title="기본 연결선 모양",
        description=(
            "이 팀의 기본 연결선 모양입니다(예: bezier, smoothstep, auto). "
            "비우면 편집기 설정을 따릅니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="팀 그래프의 연결선 모양을 한꺼번에 바꾸고 싶을 때 바꾸세요.",
            example="smoothstep",
        ),
    )
    edge_shape_by_kind: dict[str, str] | None = Field(
        default=None,
        title="연결 종류별 모양",
        description="연결 종류마다 다른 모양을 씁니다. 팀 기본 모양보다 우선합니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class NodeSpec(DefinitionModel):
    """팀 안의 노드 하나입니다. 노드 종류에 따라 하는 일과 설정 항목이 다릅니다."""

    # `type`은 레지스트리 키(임의 문자열).

    id: NonEmptyStr = Field(
        title="노드 id",
        description="팀 안에서 노드를 가리키는 고유 이름입니다. 자동으로 만들어집니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    type: NonEmptyStr = Field(
        title="노드 종류",
        description="노드가 하는 일의 종류입니다. 종류마다 설정 항목이 다릅니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    type_version: int | None = Field(
        default=None,
        title="종류 버전",
        description="노드 종류의 버전입니다. 비우면 최신 버전을 씁니다.",
        json_schema_extra=x_ui(tier="advanced", example=1),
    )
    label: str | None = Field(
        default=None,
        title="이름",
        description="팀 안에서 이 노드를 부르는 이름입니다. 비우면 연결된 정의의 이름을 씁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="같은 에이전트를 팀 안에서 다른 이름으로 부르고 싶을 때 바꾸세요.",
            example="검토 담당",
        ),
    )
    config: JsonObject = Field(
        default_factory=dict,
        title="노드 설정",
        description="노드 종류가 정한 설정입니다. 에이전트 노드는 에이전트 설정을 덮어씁니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    position: Position | None = Field(
        default=None,
        title="위치",
        description="캔버스 위 노드 위치입니다. 끌어서 옮기면 바뀝니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    group: str | None = Field(
        default=None,
        title="그룹",
        description="노드를 묶어 보이는 그룹 이름입니다.",
        json_schema_extra=x_ui(tier="advanced", example="조사 단계"),
    )
    join: JoinRule | None = Field(
        default=None,
        title="시작 조건",
        description="들어오는 값이 하나만 와도 시작할지(any) 모두 기다릴지(all) 정합니다.",
        json_schema_extra=x_ui(
            enum_labels={"any": "하나라도 도착하면", "all": "모두 도착하면"},
            tier="advanced",
            when=("여러 앞 단계 결과를 모두 모아 한 번에 처리하고 싶을 때 all로 바꾸세요."),
        ),
    )
    layout: NodeLayout | None = Field(
        default=None,
        title="배치",
        description="화면 배치(방향·포트 위치)입니다. 실행 결과에는 영향이 없습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class EdgeSpec(DefinitionModel):
    """두 노드를 잇는 연결 하나입니다. 출발 노드의 포트에서 도착 노드의 포트로 이어집니다.

    연결 종류에 따라 일이 넘어가는 방식이 다릅니다.
    """

    # 엣지: 소스 노드.포트 → 타깃 노드.포트. `kind`는 엣지 타입 id(임의 문자열).

    id: NonEmptyStr = Field(
        title="연결 id",
        description="팀 안에서 연결을 가리키는 고유 이름입니다. 자동으로 만들어집니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    source: Endpoint = Field(
        title="출발",
        description="연결이 시작되는 노드와 포트입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    target: Endpoint = Field(
        title="도착",
        description="연결이 끝나는 노드와 포트입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    kind: NonEmptyStr = Field(
        title="연결 종류",
        description="연결이 하는 일의 종류입니다. 종류마다 설정 항목이 다릅니다.",
        json_schema_extra=x_ui(
            tier="basic", when="연결이 하는 일(데이터 전달·위임·답변 등)을 바꾸고 싶을 때 고르세요."
        ),
    )
    label: str | None = Field(
        default=None,
        title="라벨",
        description="연결선 위에 보일 짧은 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="연결선이 무엇을 넘기는지 그래프에 표시하고 싶을 때 적으세요.",
            example="검토 요청",
        ),
    )
    config: JsonObject = Field(
        default_factory=dict,
        title="연결 설정",
        description="연결 종류가 정한 설정입니다(예: 지나갈 조건, 답변 이름).",
        json_schema_extra=x_ui(
            tier="basic", when="연결의 조건·답변 이름 같은 세부 동작을 정하고 싶을 때 바꾸세요."
        ),
    )
    layout: EdgeLayout | None = Field(
        default=None,
        title="모양·경로",
        description="연결선 모양·경유점·라벨 위치입니다. 실행 결과에는 영향이 없습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class ChatSettings(DefinitionModel):
    """채팅 동작입니다. 공통 설정에서 정하고, 팀마다 다르게 정할 수 있습니다."""

    # 층: 공통 → 팀 구성.

    model_config = ConfigDict(title="채팅 설정")

    busy_policy: BusyPolicy = Field(
        default="queue",
        title="실행 중 새 메시지",
        description=(
            "앞 턴이 도는 중 온 메시지를 기다렸다 실행할지(queue) 거절할지(reject) 정합니다."
        ),
        json_schema_extra=x_ui(
            enum_labels={"queue": "기다렸다 실행", "reject": "거절"},
            tier="advanced",
            when="실행 중 보낸 메시지를 쌓아 두지 않고 바로 거절하고 싶을 때 바꾸세요.",
        ),
    )
    reply_display: ReplyDisplay = Field(
        default="separate",
        title="답변 여러 개 표시",
        description=(
            "답변이 여러 개일 때 따로(separate), 하나로(merged), 마지막만(final_only) 보입니다."
        ),
        json_schema_extra=x_ui(
            enum_labels={
                "separate": "따로 보이기",
                "merged": "하나로 합치기",
                "final_only": "마지막 답변만",
            },
            tier="basic",
            when="팀 답변이 여러 개라 채팅이 길어질 때 merged나 final_only로 바꾸세요.",
        ),
    )
    title: ChatTitlePolicy = Field(
        default="first_message",
        title="대화 제목",
        description=(
            "제목을 첫 메시지로 자동으로 정할지(first_message) 직접 적을지(manual) 고릅니다."
        ),
        json_schema_extra=x_ui(
            enum_labels={"first_message": "첫 메시지로 정하기", "manual": "직접 정하기"},
            tier="basic",
            when="대화 제목을 직접 정하고 싶을 때 manual로 바꾸세요.",
        ),
    )
    send_key: SendKey = Field(
        default="enter",
        title="전송 키",
        description="enter: Enter 전송·Shift+Enter 줄바꿈, mod_enter: Ctrl/Cmd+Enter 전송.",
        json_schema_extra=x_ui(
            enum_labels={"enter": "Enter로 전송", "mod_enter": "Ctrl/Cmd+Enter로 전송"},
            tier="basic",
            when="Enter로 줄을 자주 바꾸다 실수로 보낼 때 mod_enter로 바꾸세요.",
        ),
    )
    list_sort: str | None = Field(
        default=None,
        title="대화 목록 정렬",
        description="대화 목록의 정렬 방식입니다. 비우면 답을 기다리는 대화가 먼저 옵니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="대화 목록을 최근 순으로 보고 싶을 때 바꾸세요.",
            example="updated",
        ),
    )
    answer_with_composer: bool = Field(
        default=True,
        title="입력창으로 답하기",
        description=(
            "답을 기다리는 질문이 하나이고 글로 답할 수 있으면 입력창에 쓴 내용을 그 답으로 "
            "보냅니다."
        ),
        json_schema_extra=x_ui(tier="advanced", when="질문에 항상 카드로만 답하고 싶을 때 끄세요."),
    )
    queue_after_restart: QueueAfterRestart = Field(
        default="ask",
        title="재시작 뒤 대기 메시지",
        description=(
            "서버가 다시 시작됐을 때 남은 대기 메시지를 물어볼지(ask), 실행할지(run), "
            "지울지(drop) 정합니다."
        ),
        json_schema_extra=x_ui(
            enum_labels={"ask": "물어보기", "run": "실행하기", "drop": "지우기"},
            tier="advanced",
            when="서버를 다시 켤 때마다 남은 메시지를 묻지 않고 처리하고 싶을 때 바꾸세요.",
        ),
    )
    offer_resume: bool = Field(
        default=True,
        title="끊긴 턴 이어 가기 제안",
        description="중간에 끊긴 턴에 [이 지점부터 다시 실행] 버튼을 보입니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="끊긴 턴에 다시 실행 버튼이 필요 없을 때 끄세요."
        ),
    )


class EditorSettings(DefinitionModel):
    """팀 구성 편집기 동작입니다. 새 연결의 기본 종류, 연결선 모양, 노드 방향을 정합니다.

    모양과 방향을 비워 두면 연결선이 노드를 피해 가는 자동 경로로 그립니다.
    """

    model_config = ConfigDict(title="편집기 설정")

    default_edge_kind: str | None = Field(
        default=None,
        title="새 연결 기본 종류",
        description=(
            "새 연결을 그을 때 먼저 고를 연결 종류입니다. 비우면 이을 수 있는 첫 종류입니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="새 연결을 그을 때마다 같은 종류를 고르고 있다면 바꾸세요.",
            example=None,
        ),
    )
    default_direction: str | None = Field(
        default=None,
        title="기본 노드 방향",
        description=(
            "방향을 정하지 않은 팀의 노드 방향입니다(lr, tb, rl, bt, auto). 새 팀은 auto"
            "(연결선이 노드를 피해 감)입니다. 비우면 노드 종류 기본값, 없으면 lr."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="방향을 정하지 않은 예전 팀을 위→아래 등 한 방향으로 그리고 싶을 때 바꾸세요.",
            example="lr",
        ),
    )
    default_edge_shape: str | None = Field(
        default=None,
        title="기본 연결선 모양",
        description=(
            "팀이 모양을 정하지 않았을 때의 연결선 모양입니다(예: bezier, smoothstep, auto). "
            "비우면 자동 경로(연결선이 노드를 피해 감)입니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="연결선을 곡선·꺾은선 중 한 모양으로 통일하고 싶을 때 바꾸세요.",
            example="auto",
        ),
    )
    # 0.8.0(design §5.2R.3 #6). 생략 = 켬(웹이 해석). 팀 구성 층에서는 지정했을 때만 직렬화한다.
    auto_connect_io: bool | None = Field(
        default=None,
        title="입구·답변 자동 연결",
        description="첫 에이전트를 놓을 때 입구·답변 연결을 한 번 만들어 줍니다. 비우면 켬입니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="입구·답변 연결을 직접 그리고 싶을 때 끄세요."
        ),
    )


class DelegationSettings(DefinitionModel):
    """위임 설정입니다. 고른 위임 방식이 깊이를 정하지 않을 때 씁니다."""

    # 위임 방식 디스크립터가 깊이를 정하지 않을 때 쓴다.

    model_config = ConfigDict(title="위임 설정")

    max_depth: int | None = Field(
        default=None,
        ge=1,
        title="최대 위임 깊이",
        description=(
            "맡긴 일을 다시 맡기는 단계가 몇 번까지 이어질 수 있는지입니다. 비우면 위임 방식 "
            "기본값."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="맡긴 일이 계속 다른 에이전트로 넘어가 끝나지 않을 때 줄이세요.",
            example=2,
            unit="단계",
        ),
    )
    # design §5R.7·§5R.17(0.7.0). 기본값 3은 계약 데이터다(공통 층의 기본값). null = 제한 없음
    # (자기 참조·순환 참조는 깊이와 상관없이 `team.recursive`로 막는다).
    max_nesting: int | None = Field(
        default=3,
        ge=1,
        title="최대 팀 중첩 깊이",
        description="팀 안에 팀을 넣을 수 있는 깊이입니다. 비우면 제한이 없습니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="팀 안에 팀을 더 깊게 넣어야 할 때 늘리세요.", unit="단계"
        ),
    )


class FlowSettings(DefinitionModel):
    """반복·실행 한도입니다. 팀 설정에서 비운 항목은 공통 설정 값을 따릅니다."""

    # 층: 공통 → 팀 구성.

    # 0.7.0. 사이클 연결의 최대 반복은 엣지 config `max_iterations` → 이 값 → 연결 종류 디스크립터
    # `cycle.max_iterations` 순으로 정한다(생략 = 상속).
    model_config = ConfigDict(title="흐름 설정")

    max_iterations: int | None = Field(
        default=None,
        ge=1,
        title="최대 반복 횟수",
        description=(
            "되돌아가는 연결이 반복할 수 있는 최대 횟수입니다. 비우면 연결 종류 기본값입니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="고쳐 쓰기 반복이 너무 많거나 적을 때 바꾸세요.",
            example=5,
            unit="회",
        ),
    )
    max_node_runs: int | None = Field(
        default=200,
        ge=1,
        title="노드 실행 총 한도",
        description=(
            "한 실행에서 노드가 도는 총횟수 한도입니다. 넘으면 실행을 실패로 끝냅니다. "
            "비우면 제한이 없습니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced", when="반복이 많은 팀이 한도에 걸려 멈출 때 늘리세요.", unit="회"
        ),
    )


class InteractionSettings(DefinitionModel):
    """실행 중 상호작용(되묻기·승인·검토) 대기 설정."""

    model_config = ConfigDict(title="상호작용 설정")

    timeout_seconds: float | None = Field(
        default=None,
        gt=0,
        title="응답 대기 한도(초)",
        description="실행 중 질문·승인 요청에 답을 기다리는 시간입니다. 비우면 무기한 기다립니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="질문·승인 요청을 오래 붙잡아 두지 않고 정해진 시간 뒤 정리하고 싶을 때 정하세요.",
            example=600,
            unit="초",
        ),
    )
    on_timeout: OnTimeout = Field(
        default="expire",
        title="한도 초과 시",
        description=(
            "답이 없을 때 요청만 닫고 계속할지(expire) 실행을 취소할지(cancel_run) 정합니다."
        ),
        json_schema_extra=x_ui(
            enum_labels={"expire": "요청만 닫기", "cancel_run": "실행 취소"},
            tier="advanced",
            when="답이 없으면 실행을 아예 멈추고 싶을 때 cancel_run으로 바꾸세요.",
        ),
    )


class UsageSourceSetting(DefinitionModel):
    """사용량 출처 하나의 사용 여부·설정."""

    model_config = ConfigDict(title="사용량 출처")

    id: NonEmptyStr = Field(
        title="출처",
        description="사용량을 읽어 올 곳입니다(예: 실행 기록, 상태 줄 파일).",
        json_schema_extra=x_ui(tier="basic", when="다른 곳에서 사용량을 읽고 싶을 때 고르세요."),
    )
    enabled: bool = Field(
        default=True,
        title="사용",
        description="이 출처에서 사용량을 읽을지 정합니다.",
        json_schema_extra=x_ui(tier="basic", when="이 출처의 값이 필요 없거나 틀릴 때 끄세요."),
    )
    config: JsonObject = Field(
        default_factory=dict,
        title="출처 설정",
        description="출처마다 정한 추가 설정입니다(예: 읽을 파일 경로).",
        json_schema_extra=x_ui(
            tier="advanced", when="출처가 읽을 파일 경로 등을 바꾸고 싶을 때 바꾸세요."
        ),
    )


class UsageSettings(DefinitionModel):
    """사용량 화면 설정입니다. 사용량 출처와 사용량 창의 표시 이름을 정합니다."""

    # 창 이름 목록은 코드에 없고 출처가 주는 창 id + 이 표시 이름이다.

    model_config = ConfigDict(title="사용량 설정")

    window_labels: dict[str, str] = Field(
        default_factory=dict,
        title="창 표시 이름",
        description="사용량 창 이름을 화면에 보일 이름으로 바꿉니다(창 id → 이름).",
        json_schema_extra=x_ui(
            tier="advanced",
            when="창 이름(예: five_hour)을 알아보기 쉬운 말로 바꾸고 싶을 때 적으세요.",
        ),
    )
    sources: list[UsageSourceSetting] = Field(
        default_factory=list,
        title="출처",
        description="사용량을 읽어 올 곳과 각 설정입니다. 비우면 자동으로 켜지는 출처를 씁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="사용량이 보이지 않거나 다른 곳에서 읽고 싶을 때 바꾸세요."
        ),
    )
    primary_source_order: list[str] = Field(
        default_factory=list,
        title="출처 우선순위",
        description="창 카드에 크게 보일 출처 순서입니다. 비우면 가장 최근 공식 값을 씁니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="여러 출처 중 믿는 값을 크게 보고 싶을 때 정하세요."
        ),
    )
    stale_after_seconds: float | None = Field(
        default=None,
        gt=0,
        title="오래된 값 기준(초)",
        description=(
            "값을 받은 뒤 이 시간이 지나면 오래된 값으로 표시합니다. 비우면 판정하지 않습니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="오래된 사용량 값을 따로 표시하고 싶을 때 정하세요.",
            example=600,
            unit="초",
        ),
    )


DEFAULT_NOTIFICATION_EVENTS: tuple[str, ...] = ("interaction.requested",)
"""`ui.notifications.events` 기본값(데이터 기본값일 뿐, 사용자가 바꾼다)."""


class NotificationSettings(DefinitionModel):
    """브라우저 알림과 소리입니다. 비운 항목은 기본값을 씁니다."""

    # 웹만 해석한다. 생략 = 기본값.

    model_config = ConfigDict(title="알림 설정")

    enabled: bool = Field(
        default=False,
        title="브라우저 알림",
        description="고른 일이 생기면 브라우저 알림을 띄웁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="다른 탭에서 일하다 답을 기다리는 요청을 놓칠 때 켜세요."
        ),
    )
    sound: bool = Field(
        default=False,
        title="소리",
        description="알림과 함께 짧은 소리를 냅니다.",
        json_schema_extra=x_ui(tier="basic", when="알림을 소리로도 알아차리고 싶을 때 켜세요."),
    )
    events: list[str] = Field(
        default_factory=lambda: list(DEFAULT_NOTIFICATION_EVENTS),
        title="알림 대상",
        description=(
            "알림을 띄울 일입니다(예: interaction.requested = 답을 기다림, run.failed = 실패)."
        ),
        # default_factory는 JSON Schema에 default를 남기지 않는다. 웹은 스키마 기본값을 읽으므로
        # 같은 값을 명시한다(스키마 기본값 = 모델 기본값은 테스트가 확인).
        json_schema_extra={
            "default": list(DEFAULT_NOTIFICATION_EVENTS),
            "examples": [
                list(DEFAULT_NOTIFICATION_EVENTS),
                ["interaction.requested", "run.failed"],
            ],
            **x_ui(tier="advanced", when="실패 같은 다른 일도 알림을 받고 싶을 때 더하세요."),
        },
    )
    only_when_hidden: bool = Field(
        default=True,
        title="탭이 안 보일 때만",
        description="탭을 보고 있는 동안에는 화면에만 표시하고 알림을 띄우지 않습니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="탭을 보고 있을 때도 알림을 받고 싶을 때 끄세요."
        ),
    )


DEFAULT_USAGE_INDICATOR_FIELDS: tuple[str, ...] = ("label", "value", "gauge")
"""사용량 표시기 항목 요소의 기본 순서(스키마 기본값 데이터). 어휘 해석은 웹의 항목 표가 한다."""

# 5.2R.56(ux-overhaul §15.3 명세 B): 화면은 규칙대로만 칠한다(임계 숫자는 여기 데이터뿐).
DEFAULT_USAGE_INDICATOR_COLOR_RULES: tuple[tuple[float, str], ...] = (
    (0.0, "success"),
    (0.7, "warning"),
    (0.9, "danger"),
)
"""사용량 색 규칙 기본값 ``(at, tone)``. 사용자가 비우면(``[]``) 색을 바꾸지 않는다(accent)."""


def _default_color_rules_data() -> list[JsonValue]:
    return [{"at": at, "tone": tone} for at, tone in DEFAULT_USAGE_INDICATOR_COLOR_RULES]


DEFAULT_USAGE_INDICATOR_PLACEMENT = "sidebar-bottom"
"""사용량 표시기 배치 기본값(웹 배치 표의 id). 모르는 값은 웹이 이 값으로 대신한다."""


class UsageIndicatorColorRule(DefinitionModel):
    """사용률 임계 색 규칙 한 줄."""

    model_config = ConfigDict(title="사용량 색 규칙")

    at: float = Field(
        ge=0,
        le=1,
        title="사용률 기준",
        description="사용률(0~1)이 이 값 이상이면 규칙을 적용합니다.",
        examples=[0.8],
        json_schema_extra=x_ui(
            tier="basic", when="경고 색을 더 일찍 또는 늦게 보고 싶을 때 바꾸세요."
        ),
    )
    tone: NonEmptyStr = Field(
        title="색",
        description=("칠할 색 이름입니다(예: warning, danger). 모르는 값은 기본 색으로 그립니다."),
        examples=["warning"],
        json_schema_extra=x_ui(
            tier="basic", when="한도에 가까울 때 다른 색으로 보고 싶을 때 바꾸세요."
        ),
    )


class UsageIndicatorSettings(DefinitionModel):
    """모든 화면에 보이는 사용량 표시기입니다. 비운 항목은 기본값을 씁니다."""

    # 웹만 해석한다. 생략 = 기본값.

    model_config = ConfigDict(title="사용량 표시기 설정")

    enabled: bool = Field(
        default=True,
        title="사용량 표시기 보이기",
        description="모든 화면 구석에 남은·쓴 사용량을 작게 보입니다.",
        json_schema_extra=x_ui(tier="basic", when="화면 구석의 사용량 표시가 필요 없을 때 끄세요."),
    )
    placement: NonEmptyStr = Field(
        default=DEFAULT_USAGE_INDICATOR_PLACEMENT,
        title="위치",
        description="표시기를 놓을 곳입니다. 모르는 값이면 사이드바 아래에 보입니다.",
        examples=[DEFAULT_USAGE_INDICATOR_PLACEMENT],
        json_schema_extra=x_ui(
            tier="basic", when="사용량 표시가 다른 위치에 있는 편이 보기 좋을 때 바꾸세요."
        ),
    )
    windows: list[NonEmptyStr] = Field(
        default_factory=list,
        title="보일 창",
        description="보일 사용량 창. 비우면 출처가 준 순서의 앞쪽부터 보일 창 수만큼 보입니다.",
        # default_factory는 스키마에 default를 남기지 않으므로 명시한다(웹은 스키마 기본값을 읽음).
        json_schema_extra={
            "default": [],
            "examples": [[]],
            **x_ui(tier="advanced", when="특정 창(예: 주간)만 보고 싶을 때 고르세요."),
        },
    )
    max_items: int = Field(
        default=2,
        ge=1,
        le=6,
        title="보일 창 수",
        description="보일 창을 고르지 않았을 때 앞에서부터 몇 개를 보일지입니다(1~6).",
        json_schema_extra=x_ui(
            tier="advanced", when="창을 더 많이 또는 적게 보고 싶을 때 바꾸세요.", unit="개"
        ),
    )
    fields: list[NonEmptyStr] = Field(
        default_factory=lambda: list(DEFAULT_USAGE_INDICATOR_FIELDS),
        title="항목",
        description=(
            "항목에 보일 요소(순서대로). 알려진 값: label, value, gauge, reset, trust, observed. "
            "모르는 값은 무시합니다."
        ),
        json_schema_extra={
            "default": list(DEFAULT_USAGE_INDICATOR_FIELDS),
            "examples": [
                list(DEFAULT_USAGE_INDICATOR_FIELDS),
                ["label", "value", "gauge", "reset"],
            ],
            **x_ui(tier="advanced", when="초기화 시각 같은 정보를 더 보고 싶을 때 더하세요."),
        },
    )
    # 0.8.0: 기본값을 remaining → used로 바꿨다(사용자 지시, design §5.2R.4).
    # 값을 적은 설정은 그대로다.
    value_mode: Literal["remaining", "used"] = Field(
        default="used",
        title="값 방향",
        description=(
            "숫자와 게이지를 사용한 양/남은 양 중 무엇으로 보일지. 남은 양으로 보려면 remaining."
        ),
        json_schema_extra=x_ui(
            enum_labels={"remaining": "남은 양", "used": "쓴 양"},
            tier="basic",
            when="쓴 양 대신 남은 양으로 보고 싶을 때 remaining으로 바꾸세요.",
        ),
    )
    color_rules: list[UsageIndicatorColorRule] = Field(
        default_factory=lambda: [
            UsageIndicatorColorRule(at=at, tone=tone)
            for at, tone in DEFAULT_USAGE_INDICATOR_COLOR_RULES
        ],
        title="색 규칙",
        description=(
            "사용률이 기준 이상이면 게이지를 그 색으로 칠합니다(가장 높은 기준이 이깁니다). "
            "기본은 0% 초록·70% 노랑·90% 빨강입니다. 비우면 색을 바꾸지 않습니다."
        ),
        json_schema_extra={
            "default": _default_color_rules_data(),
            "examples": [
                _default_color_rules_data(),
                [{"at": 0.8, "tone": "warning"}],
                [],
            ],
            **x_ui(
                tier="advanced", when="한도에 가까워진 것을 색으로 눈에 띄게 하고 싶을 때 더하세요."
            ),
        },
    )
    hide_when_empty: bool = Field(
        default=False,
        title="관측이 없으면 숨기기",
        description="받은 사용량이 하나도 없으면 표시기를 숨깁니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="사용량을 받지 못할 때 빈 표시가 거슬리면 켜세요."
        ),
    )
    also_in_title: bool = Field(
        default=False,
        title="탭 제목에도 보이기",
        description="브라우저 탭·창 제목에도 첫 항목을 붙입니다.",
        json_schema_extra=x_ui(tier="advanced", when="다른 탭에서도 사용량을 보고 싶을 때 켜세요."),
    )

    @field_validator("color_rules")
    @classmethod
    def _unique_rule_thresholds(
        cls, rules: list[UsageIndicatorColorRule]
    ) -> list[UsageIndicatorColorRule]:
        seen: set[float] = set()
        for rule in rules:
            if rule.at in seen:
                raise ValueError(f"같은 사용률 규칙이 있습니다: {rule.at}")
            seen.add(rule.at)
        return rules


class VersionUiSettings(DefinitionModel):
    """버전 비교 화면 설정입니다. 비운 항목은 기본값을 씁니다."""

    # E-15. 웹만 해석한다. 생략 = 상속(웹 기본값).

    model_config = ConfigDict(title="버전 비교 설정")

    item_label_keys: list[str] | None = Field(
        default=None,
        title="항목 이름 키",
        description=(
            "버전 비교에서 노드·연결 등을 부를 때 찾을 이름 키입니다(앞에서부터). "
            "비우면 label, name, title, id."
        ),
        examples=[["label", "name", "title", "id"]],
        json_schema_extra=x_ui(
            tier="advanced", when="버전 비교에서 항목 이름이 id로만 보일 때 바꾸세요."
        ),
    )


class UiPreferences(DefinitionModel):
    """화면 동작 설정."""

    model_config = ConfigDict(title="화면 설정")

    keybindings: dict[str, str] | None = Field(
        default=None,
        title="단축키",
        description="동작마다 키 조합을 바꿉니다. 적은 항목만 바뀌고 나머지는 기본 키입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="기본 단축키가 다른 프로그램과 겹치거나 손에 맞지 않을 때 바꾸세요."
        ),
    )
    notifications: NotificationSettings = Field(
        default_factory=NotificationSettings,
        title="알림",
        description="브라우저 알림과 소리를 정합니다.",
        json_schema_extra=x_ui(tier="basic", when="답을 기다리는 요청을 놓치지 않으려면 바꾸세요."),
    )
    usage_indicator: UsageIndicatorSettings = Field(
        default_factory=UsageIndicatorSettings,
        title="사용량 표시기",
        description="모든 화면에 보이는 작은 사용량 표시입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="사용량 표시의 위치·내용을 바꾸고 싶을 때 바꾸세요."
        ),
    )
    versions: VersionUiSettings = Field(
        default_factory=VersionUiSettings,
        title="버전 비교",
        description="버전 비교 화면에서 항목을 부르는 방법입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class SecretRuleSettings(DefinitionModel):
    """비밀 값으로 의심할 규칙을 더합니다. 기본 규칙에 더하기만 하며 줄일 수는 없습니다."""

    model_config = ConfigDict(title="비밀 규칙")

    extra_key_names: list[str] = Field(
        default_factory=list,
        title="추가 비밀 키 이름",
        description="이 이름(또는 이 단어가 든 이름)의 값을 비밀로 의심합니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="우리 팀만 쓰는 비밀 이름(예: deploy_key)이 있을 때 더하세요.",
            example=["api_key"],
        ),
    )
    extra_value_patterns: list[str] = Field(
        default_factory=list,
        title="추가 비밀 값 패턴",
        description=(
            "값이 이 정규식과 맞으면 비밀로 의심합니다. 위험한 패턴은 저장할 때 거부됩니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="특정 형식의 토큰이 기록에 남는 것을 막고 싶을 때 더하세요.",
            example=["^sk-[A-Za-z0-9]{20,}$"],
        ),
    )
    redact_suspected_in_logs: bool = Field(
        default=True,
        title="실행 기록에서 의심 값 가리기",
        description="실행 기록·질문 응답을 저장하기 전에 비밀로 의심되는 값을 가립니다.",
        json_schema_extra=x_ui(
            tier="basic", when="비밀이 아닌 값까지 가려져 기록을 읽기 어려울 때만 끄세요."
        ),
    )


class ProjectPreferences(DefinitionModel):
    """프로젝트 관련 설정입니다. 새로 만드는 에이전트·팀 등을 어느 범위에 둘지 정합니다."""

    # 프로젝트 목록 자체는 정의 종류 `project`다.

    # 0.8.0. 계약 하위 모듈 `projects`가 아니라 여기 둔다: 공통 설정(WorkspaceSettings)의 섹션이고,
    # `projects`는 `definitions`를 쓰므로(Project.settings = AgentSettings)
    # 반대 방향 import를 피한다.
    model_config = ConfigDict(title="프로젝트 설정")

    new_definition_scope: dict[str, DefinitionScope] = Field(
        default_factory=dict,
        title="종류별 새 정의 범위",
        description=(
            "종류마다 새로 만든 정의를 프로젝트 전용(project)으로 둘지 공용(shared)으로 둘지입니다."
        ),
        json_schema_extra={"default": {}, **x_ui(tier="advanced", example={"agent": "shared"})},
    )
    fallback: DefinitionScope = Field(
        default="project",
        title="기본 범위",
        description="종류별 범위에 없는 종류를 새로 만들 때의 범위입니다.",
        json_schema_extra=x_ui(
            enum_labels={"project": "프로젝트 것", "shared": "공용 것"}, tier="advanced"
        ),
    )


_DEFAULTS_LAYER_UI: dict[str, dict[str, Any]] = {
    "backend": x_ui(
        tier="basic",
        when=(
            "처음 쓸 때 먼저 고르세요. 모든 에이전트가 기본으로 쓸 실행 방식을 바꿀 때도 바꾸세요."
        ),
    )[X_UI],
}
"""공통 층(에이전트 기본값) 폼에서만 분류를 바꾸는 필드 → x-ui.

처음 쓰는 사람이 꼭 정하는 값만 둔다."""


def _defaults_layer_ui(schema: JsonDict) -> None:
    """공통 층 폼: 실행 백엔드처럼 처음에 꼭 정할 값을 기본 필드로 올린다.

    에이전트 폼에서 실행 백엔드는 '이 에이전트만 다르게'라서 고급이지만, 공통 설정에서는 모든 실행이
    기대는 기본값이라 첫 줄에 보여야 한다. 필드 정의를 복제하지 않고 스키마만 고친다.
    """
    props = schema.get("properties")
    if not isinstance(props, dict):
        return
    for name, ui in _DEFAULTS_LAYER_UI.items():
        prop = props.get(name)
        if isinstance(prop, dict):
            base = prop.get(X_UI)
            prop[X_UI] = {**(base if isinstance(base, dict) else {}), **ui}


class AgentDefaults(AgentSettings):
    """모든 에이전트가 함께 쓰는 기본 설정입니다.

    팀이나 에이전트에서 따로 정하지 않은 항목은 여기 값을 씁니다. 처음 쓸 때 실행 백엔드를
    먼저 고르고, 모든 에이전트의 모델·도구·권한을 한꺼번에 바꾸고 싶을 때 고치세요.
    """

    # 개발자 메모(스키마에 나가지 않음): 공통 층의 에이전트 설정(`WorkspaceSettings.agent_defaults`,
    # 화면 이름 "에이전트 기본값"). 필드와 의미는 `AgentSettings`와 같다(생략 = 상속). 폼 분류만
    # 다르다(실행 백엔드가 기본 필드, `_defaults_layer_ui`).

    model_config = ConfigDict(title="에이전트 기본값", json_schema_extra=_defaults_layer_ui)


_TEAM_AGENT_GROUP = x_ui(tier="advanced", group="agent", group_title="에이전트 기본값")[X_UI]
"""팀 구성 층에서 물려받은 에이전트 설정 필드의 x-ui(전부 고급, 한 소제목)."""


def _team_layer_ui(schema: JsonDict) -> None:
    """팀 구성 층 폼: 물려받은 에이전트 설정 필드를 고급의 '에이전트 기본값' 묶음으로 보인다.

    에이전트 폼에서는 모델·시스템 프롬프트가 기본 필드지만, 팀 설정에서는 대부분 공통 값을 물려받아
    전부 고급으로 접는다. 필드 정의를 복제하지 않고 스키마만 고친다.
    """
    props = schema.get("properties")
    if not isinstance(props, dict):
        return
    for name in AgentSettings.model_fields:
        prop = props.get(name)
        if isinstance(prop, dict):
            base = prop.get(X_UI)
            prop[X_UI] = {**(base if isinstance(base, dict) else {}), **_TEAM_AGENT_GROUP}


class GraphSettings(AgentSettings, OmitWhenUnsetModel):
    """팀 구성 층 설정: 에이전트 설정과 채팅·편집기·위임·상호작용 설정. 비우면 공통 설정."""

    model_config = ConfigDict(title="팀 구성 설정", json_schema_extra=_team_layer_ui)

    chat: ChatSettings | None = Field(
        default=None,
        title="채팅",
        description="이 팀의 채팅 동작입니다. 비운 항목은 공통 설정을 따릅니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="이 팀만 답변 표시나 실행 중 메시지 처리를 다르게 하고 싶을 때 바꾸세요.",
            group="chat",
            group_title="채팅",
        ),
    )
    editor: EditorSettings | None = Field(
        default=None,
        title="편집기",
        description="이 팀을 편집할 때의 기본 동작입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="이 팀을 편집할 때만 기본 연결 종류·방향을 다르게 하고 싶을 때 바꾸세요.",
            group="editor",
            group_title="편집기",
        ),
    )
    delegation: DelegationSettings | None = Field(
        default=None,
        title="위임",
        description="이 팀에서 일을 맡기는 깊이 한도입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="이 팀에서만 맡기는 깊이를 다르게 하고 싶을 때 바꾸세요.",
            group="delegation",
            group_title="위임",
        ),
    )
    interaction: InteractionSettings | None = Field(
        default=None,
        title="상호작용",
        description="실행 중 질문·승인 요청을 기다리는 방식입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="이 팀에서만 질문·승인 대기 시간을 다르게 하고 싶을 때 바꾸세요.",
            group="interaction",
            group_title="상호작용",
        ),
    )
    settings_merge: dict[str, str] | None = Field(
        default=None,
        title="병합 규칙 덮어쓰기",
        description=_SETTINGS_MERGE_DESCRIPTION,
        json_schema_extra=x_ui(
            tier="advanced",
            when=_SETTINGS_MERGE_WHEN,
            example={"/limits": "intersect"},
            group="merge",
            group_title="병합",
        ),
    )
    flow: FlowSettings | None = Field(
        default=None,
        title="흐름",
        description="반복 횟수와 노드 실행 총 한도입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="이 팀에서만 반복 횟수 한도를 다르게 하고 싶을 때 바꾸세요.",
            group="flow",
            group_title="흐름",
        ),
    )

    # 버전 해시 안정(5R.2): 그래프 버전 해시는 기본값까지 넣은 전체 직렬화로 계산한다(ac-graph
    # `canonical_graph`). 0.7.0에서 팀 구성 층에 더한 필드가 지정되지 않았는데도 null·기본값으로
    # 나타나면 0.6.0 이하에서 저장한 팀 구성의 해시가 모두 바뀐다. 그래서 아래 경로는 **지정했을
    # 때만** 직렬화한다(층 값은 원래 exclude_unset으로 읽으므로 의미는 같다). 앞으로 이 층에 필드를
    # 더할 때도 여기에 적는다(0.8.0: editor.auto_connect_io).
    _OMIT_WHEN_UNSET: ClassVar[tuple[tuple[str, ...], ...]] = (
        ("flow",),
        ("delegation", "max_nesting"),
        ("editor", "auto_connect_io"),
    )


class Graph(OmitWhenUnsetModel):
    """팀 구성입니다. 노드(에이전트 등)와 그 사이 연결로 일이 흘러가는 순서를 정합니다."""

    # 팀 구성 그래프 정의(`<workspace>/graphs/<id>.yaml`). 화면 이름은 "팀 구성".

    kind: Literal["graph"] = "graph"
    id: Slug = Field(
        title="id", description=_ID_DESCRIPTION, json_schema_extra=x_ui(tier="advanced")
    )
    schema_version: int = Field(
        default=1,
        title="형식 버전",
        description=_SCHEMA_VERSION_DESCRIPTION,
        json_schema_extra=x_ui(tier="advanced"),
    )
    name: NonEmptyStr = Field(
        title="이름",
        description="팀 구성을 부르는 이름입니다. 목록과 채팅에 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="목록과 채팅에서 알아보기 쉬운 이름으로 바꾸고 싶을 때 바꾸세요.",
            example="코드 리뷰 팀",
        ),
    )
    description: str = Field(
        default="",
        title="설명",
        description="이 팀이 하는 일을 적습니다. 목록에 함께 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="팀 목록에서 이 팀이 무엇을 하는지 알리고 싶을 때 적으세요.",
            example="변경을 나눠 검토하고 요약합니다.",
        ),
    )
    labels: list[str] = Field(
        default_factory=list,
        title="라벨",
        description=_LABELS_DESCRIPTION,
        json_schema_extra=x_ui(tier="advanced"),
    )
    attributes: JsonObject = Field(
        default_factory=dict,
        title="기타 속성",
        description=_ATTRIBUTES_DESCRIPTION,
        json_schema_extra=x_ui(tier="advanced"),
    )
    settings: GraphSettings | None = Field(
        default=None,
        title="팀 설정",
        description="이 팀의 에이전트·채팅·위임 설정입니다. 비운 항목은 공통 설정을 따릅니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="이 팀만 모델·채팅·위임 동작을 공통 설정과 다르게 하고 싶을 때 바꾸세요.",
        ),
    )
    inputs: list[PortDef] = Field(
        default_factory=list,
        title="입력 포트",
        description="팀이 받는 입력입니다. 실행할 때 포트 이름마다 값을 넣습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    outputs: list[PortDef] = Field(
        default_factory=list,
        title="출력 포트",
        description="팀이 내보내는 출력입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    nodes: list[NodeSpec] = Field(
        default_factory=list,
        title="노드",
        description="팀에 놓인 노드입니다. 캔버스에서 고칩니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    edges: list[EdgeSpec] = Field(
        default_factory=list,
        title="연결",
        description="노드 사이의 연결입니다. 캔버스에서 고칩니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    groups: list[JsonObject] = Field(
        default_factory=list,
        title="그룹",
        description="노드를 묶어 보이는 그룹입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    limits: Limits | None = Field(
        default=None,
        title="실행 범위(이전 형식)",
        description="이전 형식의 실행 범위입니다. 새 설정은 팀 설정의 실행 범위를 씁니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    ui: JsonObject = Field(
        default_factory=dict,
        title="편집기 상태",
        description="편집기 화면 상태(보기 위치·배치 등)입니다. 직접 고치지 않아도 됩니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    # 0.8.0(design §UX-P.4). 생략 = 공용. 그래프 버전 해시(ac-graph)는 이 필드를 뺀다.
    project: Slug | None = Field(
        default=None,
        title="프로젝트",
        description=PROJECT_FIELD_DESCRIPTION,
        json_schema_extra=x_ui(
            tier="basic",
            when="이 팀을 특정 프로젝트에서만 보이게 하고 싶을 때 고르세요.",
            example=None,
        ),
    )

    _OMIT_WHEN_UNSET: ClassVar[tuple[tuple[str, ...], ...]] = (("project",),)


class WorkspaceSettings(DefinitionModel):
    """이 워크스페이스의 공통 설정과 사용자 설정입니다."""

    # 파일: <workspace>/settings.yaml. 설정 화면은 이 스키마로 폼을 그리므로
    # title·description은 화면에 그대로 보이는 문구다(필드 포함).
    model_config = ConfigDict(title="워크스페이스 설정")

    schema_version: int = Field(
        default=1,
        title="형식 버전",
        description=_SCHEMA_VERSION_DESCRIPTION,
        json_schema_extra=x_ui(tier="advanced"),
    )
    agent_defaults: AgentDefaults = Field(
        default_factory=AgentDefaults,
        title="에이전트 공통 설정",
        description="모든 팀과 에이전트가 물려받는 기본값입니다. 팀·에이전트에서 덮어씁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="모든 에이전트에 같은 모델·지침·실행 방식을 쓰게 하고 싶을 때 바꾸세요.",
        ),
    )
    chat: ChatSettings = Field(
        default_factory=ChatSettings,
        title="채팅",
        description="대화 화면과 메시지 처리 방식입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="대화 화면의 답변 표시·전송 키를 바꾸고 싶을 때 바꾸세요."
        ),
    )
    editor: EditorSettings = Field(
        default_factory=EditorSettings,
        title="편집기",
        description="팀 구성 편집기의 기본 동작입니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="팀 편집기의 기본 연결 종류·방향·모양을 바꾸고 싶을 때 바꾸세요."
        ),
    )
    delegation: DelegationSettings = Field(
        default_factory=DelegationSettings,
        title="위임",
        description="다른 에이전트·팀에 일을 맡기는 깊이 한도입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="맡긴 일이 너무 깊게 이어지거나 팀을 더 깊게 넣어야 할 때 바꾸세요.",
        ),
    )
    flow: FlowSettings = Field(
        default_factory=FlowSettings,
        title="흐름",
        description="반복 횟수·노드 실행 총 한도입니다. 비운 항목은 기본값을 따릅니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="반복이 많은 팀이 한도에 걸려 멈출 때 바꾸세요."
        ),
    )
    interaction: InteractionSettings = Field(
        default_factory=InteractionSettings,
        title="상호작용",
        description="실행 중 질문·승인 요청을 기다리는 방식입니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="질문·승인 요청을 얼마나 기다릴지 정하고 싶을 때 바꾸세요."
        ),
    )
    usage: UsageSettings = Field(
        default_factory=UsageSettings,
        title="사용량",
        description="사용량을 읽어 올 곳과 창 표시 방식입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="사용량이 보이지 않거나 다른 곳에서 읽고 싶을 때 바꾸세요."
        ),
    )
    ui: UiPreferences = Field(
        default_factory=UiPreferences,
        title="화면",
        description="단축키·알림·사용량 표시기 같은 화면 동작입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="단축키·알림·사용량 표시를 내 손에 맞게 바꾸고 싶을 때 바꾸세요."
        ),
    )
    settings_merge: dict[str, str] = Field(
        default_factory=dict,
        title="병합 규칙 덮어쓰기",
        description=_SETTINGS_MERGE_DESCRIPTION,
        json_schema_extra=x_ui(
            tier="advanced", when=_SETTINGS_MERGE_WHEN, example={"/limits": "intersect"}
        ),
    )
    secrets: SecretRuleSettings = Field(
        default_factory=SecretRuleSettings,
        title="비밀",
        description="비밀로 의심할 이름·값 규칙을 더합니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="기록에서 가려야 할 비밀 형식이 더 있을 때 바꾸세요."
        ),
    )
    logs: LogSettings = Field(
        default_factory=LogSettings,
        title="로그",
        description=(
            "읽을 로그 출처·범주 표시·프로젝트 묶기·대시보드입니다. 비운 항목은 기본값입니다."
        ),
        json_schema_extra=x_ui(
            tier="basic", when="다른 로그 폴더를 읽거나 로그를 프로젝트별로 묶고 싶을 때 바꾸세요."
        ),
    )
    projects: ProjectPreferences | None = Field(
        default=None,
        title="프로젝트",
        description="새 정의를 공용으로 둘지 프로젝트 전용으로 둘지의 기본값입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    default_backend: str | None = Field(
        default=None,
        title="기본 실행 백엔드(이전 형식)",
        description="더 이상 쓰지 않습니다. 에이전트 공통 설정의 실행 백엔드를 씁니다(읽기만 함).",
        json_schema_extra={"deprecated": True, **x_ui(tier="advanced", example=None)},
    )
    attributes: JsonObject = Field(
        default_factory=dict,
        title="기타 속성",
        description=_ATTRIBUTES_DESCRIPTION,
        json_schema_extra=x_ui(tier="advanced"),
    )

    @field_validator("agent_defaults", mode="before")
    @classmethod
    def _accept_agent_settings(cls, value: Any) -> Any:
        """`AgentSettings` 인스턴스도 받는다(지정한 필드만 옮겨 '생략 = 상속'을 지킨다)."""
        if isinstance(value, AgentSettings) and not isinstance(value, AgentDefaults):
            return value.model_dump(exclude_unset=True, by_alias=True)
        return value
