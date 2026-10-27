"""실행 확장 지점 디스크립터: 노드 타입·연결 종류·백엔드·모델·위임 방식·상호작용 종류
(design §3.3, §R3, §R14.3).

레지스트리 내용을 웹으로 그대로 전달한다. 엔진·편집기·화면은 종류 이름을 모르고 디스크립터
속성으로만 동작한다. 연결 종류·상호작용 종류·위임 방식의 id는 모두 임의 문자열이다.
"""

from typing import Literal

from pydantic import Field

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr
from agent_console_contracts.common import JsonPointer, PortSpec, UiHints
from agent_console_contracts.definitions import JoinRule

type EdgeScheduling = Literal["flow", "none", "entry", "exit"]
"""엣지가 실행 스케줄에서 갖는 의미(엔진 어휘, design §R3.1).

- flow: 출발 노드가 끝나면 값을 도착 노드로 흘린다(위상·사이클 계산 대상).
- none: 스케줄과 무관(위임·리소스·상호작용 허용 등). 위상·사이클 계산에서 빠진다.
- entry: 도착 노드가 입구다. Run 입력을 넣는다. 위상·사이클 계산에서 빠진다.
- exit: 출발 노드가 끝나면 그 출력을 답변(`run.reply`)으로 발행한다. 위상·사이클 계산에서 빠진다.
"""


class DefinitionBinding(ContractModel):
    """노드 타입이 정의 하나에서 만들어진다는 표시(편집기 팔레트 근거).

    예: 정의 종류 `kind`의 항목 하나를 끌어 놓으면 노드 config의 `field`에 그 id가 들어간다.
    """

    kind: NonEmptyStr = Field(description="정의 종류 이름(저장소 kind).")
    field: NonEmptyStr = Field(description="정의 id를 넣을 노드 config 키.")


class NodeTypeDescriptor(ContractModel):
    """노드 타입 디스크립터(X1). 편집기 팔레트·노드 모양·설정 폼은 이것만으로 그린다."""

    id: NonEmptyStr
    version: int = 1
    title: NonEmptyStr
    description: str = ""
    category: str = Field(default="", description="팔레트 묶음 이름(문자열, 고정 목록 아님).")
    role: str | None = Field(
        default=None,
        description="노드 역할 문자열(연결 규칙 `connects`의 근거, 고정 목록 아님).",
    )
    executable: bool = Field(
        default=True, description="false면 엔진이 스케줄하지 않는다(리소스 등)."
    )
    binds: DefinitionBinding | None = Field(
        default=None, description="이 노드 타입이 정의 하나에서 만들어지면 그 종류와 config 키."
    )
    config_schema: JsonObject = Field(
        default_factory=dict, description="config의 JSON Schema(폼 자동 생성)."
    )
    ui_schema: JsonObject = Field(default_factory=dict, description="rjsf uiSchema 힌트(선택).")
    static_ports: PortSpec | None = Field(
        default=None, description="고정 포트. dynamic_ports가 true면 서버에 계산을 요청한다."
    )
    dynamic_ports: bool = False
    join: JoinRule = "any"
    capabilities: list[str] = Field(
        default_factory=list, description="능력 문자열(해석은 엔진·화면 몫, 고정 목록 아님)."
    )
    rerunnable: bool = Field(
        default=False,
        description=("끊긴 실행을 이어 갈 때 저장된 입력으로 이 노드부터 다시 실행할 수 있는지."),
    )
    ui_hints: UiHints | None = None


class EdgeInvocation(ContractModel):
    """이 연결로 이어진 아래 노드를 위 노드 실행 안에서 부를 때 쓸 위임 방식."""

    strategy: NonEmptyStr = Field(
        description="위임 방식(X12) id. 엣지 config strategy로 덮어쓸 수 있다."
    )


class EdgeConnects(ContractModel):
    """어떤 노드 역할끼리 이을 수 있는지. 빈 목록 = 제한 없음."""

    source: list[str] = Field(default_factory=list, description="출발 노드 역할 목록.")
    target: list[str] = Field(default_factory=list, description="도착 노드 역할 목록.")


class EdgeInteraction(ContractModel):
    """이 연결의 출발 노드가 실행 중 열 수 있는 상호작용 종류."""

    kinds: list[str] = Field(
        default_factory=list,
        description="상호작용 종류 id 목록. 엣지 config kinds로 좁힐 수 있다.",
    )


class EdgePortPair(ContractModel):
    """연결 종류의 기본 포트 이름. 편집기 토글(입구·답변·묻기)이 엣지를 만들 때 쓴다."""

    source: str | None = Field(default=None, description="출발 노드 포트 이름.")
    target: str | None = Field(default=None, description="도착 노드 포트 이름.")


class ReplyFields(ContractModel):
    """답변(exit) 연결이 엣지 config의 어디에 답변 속성을 두는지.

    값은 엣지 `config` 기준 JSON Pointer다. 플러그인이 선언하며 계약에는 키 이름 기본값이 없다.
    생략한 속성은 기본 규칙(label = 엣지 label, order 없음, final = true, stream = false)을 쓴다.
    """

    label: JsonPointer | None = Field(default=None, description="답변 표시 이름의 위치.")
    order: JsonPointer | None = Field(default=None, description="답변 순서의 위치.")
    final: JsonPointer | None = Field(default=None, description="최종 답변 여부의 위치.")
    stream: JsonPointer | None = Field(default=None, description="흘려 보내기 여부의 위치.")


class CyclePolicy(ContractModel):
    """사이클을 허용하는 연결 종류의 반복 정책(0.7.0).

    이 정책이 있는 연결 종류(사이클 연결)는 흐름 사이클을 닫을 수 있다. 엔진·검증은 연결 이름이
    아니라 이 속성이 있는지로 판단한다.
    """

    max_iterations: int = Field(
        ge=1,
        description=(
            "기본 최대 반복 횟수. 엣지 config `max_iterations` → 설정 `flow.max_iterations` → "
            "이 값 순으로 정한다."
        ),
    )
    title: str | None = Field(default=None, description="화면 표시 문구(예: 회차 한도 칩).")


class EdgeTypeDescriptor(ContractModel):
    """엣지 타입(연결 종류) 디스크립터(X2). 엔진·편집기는 이름이 아니라 이 속성으로 구분한다."""

    id: NonEmptyStr
    version: int = 1
    title: NonEmptyStr
    description: str = ""
    scheduling: EdgeScheduling = Field(default="flow", description="스케줄 의미(엔진 어휘).")
    invocation: EdgeInvocation | None = None
    connects: EdgeConnects | None = Field(
        default=None, description="연결 가능한 노드 역할. 없으면 제한 없음."
    )
    interaction: EdgeInteraction | None = None
    default_ports: EdgePortPair | None = Field(
        default=None,
        description="새 엣지의 기본 포트. 없으면 노드 타입 포트 순서에서 첫 호환 포트.",
    )
    reply_fields: ReplyFields | None = Field(
        default=None,
        description="답변 연결이면 답변 속성의 config 위치. null = config에서 읽지 않음.",
    )
    cycle: CyclePolicy | None = Field(
        default=None,
        description=(
            "있으면 사이클 연결이다: 흐름 사이클을 닫을 수 있고 지나갈 때 반복 영역을 다시 연다"
            ". null = 사이클 불가."
        ),
    )
    handles_failure: bool = Field(
        default=False,
        description=(
            "출발 노드가 실패해도 지나갈 수 있는 연결(실패 처리). "
            "화면·검증 표시용이며 실제 통과 여부는 연결 종류 구현이 정한다."
        ),
    )
    config_schema: JsonObject = Field(default_factory=dict)
    ui_schema: JsonObject = Field(default_factory=dict)
    ui_hints: UiHints | None = None


class EnforceCapabilities(ContractModel):
    """백엔드가 실제로 강제할 수 있는 실행 범위 항목. false면 화면이 경고한다."""

    directories: bool = False
    commands: bool = False
    network: bool = False


class BackendCapabilities(ContractModel):
    """실행 백엔드 능력."""

    streaming: bool = False
    tools: bool = False
    hooks: bool = False
    mcp: bool = False
    resume: bool = False
    cancel: bool = False
    subagents: bool = Field(
        default=False, description="요청 안의 서브에이전트 목록을 한 세션에서 실행할 수 있다."
    )
    resource_slots: list[str] = Field(
        default_factory=list, description="받을 수 있는 실행 묶음 칸 이름."
    )
    interactions: list[str] | None = Field(
        default=None, description="열 수 있는 상호작용 종류 id. null = 제한 없음."
    )
    subagent_slots: list[str] | None = Field(
        default=None,
        description=(
            "서브에이전트(위임받는 노드)마다 따로 받는 실행 묶음 칸. `resource_slots`에 있지만 "
            "여기 없는 칸은 위임자 세션에 합쳐진다(세션 공유, 묶음 미리보기가 경고). "
            "null = 구분 정보 없음(경고하지 않음)."
        ),
    )
    slot_notes: dict[str, str] | None = Field(
        default=None,
        description=(
            "칸 이름 → 그 칸에 대한 백엔드 설명(예: 받지 않는 이유, 설정으로 꺼져 있음). "
            "`resource.slot_unsupported` 경고의 `details.reason`·문구에 붙는다. "
            "null = 설명 없음."
        ),
    )
    enforce: EnforceCapabilities = Field(default_factory=EnforceCapabilities)
    host_tools: bool = Field(
        default=False,
        description=(
            "플랫폼이 만든 도구(위임 도구 등)를 모델에게 주고 호출을 플랫폼으로 돌려줄 수 있다"
            "(독립 위임에 필요)."
        ),
    )
    # 0.8.0(ux-overhaul §15.8): 선택 능력. 백엔드가 ``status``·``probe`` 메서드를 구현했다는 선언.
    status: bool = Field(
        default=False,
        description=(
            "정적 점검(인증·설정 확인, 모델·네트워크 호출 없음)을 지원한다. "
            "`GET /backends/{id}/status`가 이 값이 false면 상태 unknown을 낸다."
        ),
    )
    probe: bool = Field(
        default=False,
        description=(
            "연결 테스트(가장 짧은 실제 호출 한 번)를 지원한다. false면 "
            "`POST /backends/{id}/probe`가 409 `backend.probe_unsupported`."
        ),
    )
    # 0.8.0(ux-overhaul §15.9, F14): 선택 능력. ``start_login``·``logout`` 구현 선언.
    login: bool = Field(
        default=False,
        description=(
            "앱 화면에서 백엔드 계정 로그인을 시작할 수 있다(방법은 `login_methods`). "
            "false면 `POST /backends/{id}/login`이 409 `backend.login_unsupported`."
        ),
    )
    logout: bool = Field(
        default=False,
        description=(
            "앱 화면에서 백엔드 계정 로그아웃(연결 해제)을 할 수 있다. false면 "
            "`POST /backends/{id}/logout`이 409 `backend.logout_unsupported`."
        ),
    )


class CollectorDescriptor(ContractModel):
    """관측 수집기 디스크립터. 실행 중 SDK 콜백·메시지에서 이벤트를 모은다.

    수집기는 백엔드별 프로토콜로 구현되고 `backend`로 걸러진다. 설정은
    `AgentSettings.observe.collectors{id: {enabled?, config?}}`(생략 = 상속)다.
    """

    id: NonEmptyStr
    title: NonEmptyStr
    backend: NonEmptyStr = Field(description="이 수집기를 쓰는 실행 백엔드 id.")
    description: str | None = None
    config_schema: JsonObject = Field(default_factory=dict)
    emits: list[str] = Field(
        default_factory=list, description="내는 실행 이벤트 type 또는 접두사(예: hook.*, mcp.*)."
    )


class LoginMethodInfo(ContractModel):
    """백엔드가 제공하는 로그인 방법 하나(데이터). 화면은 문구를 그대로 보인다."""

    id: NonEmptyStr = Field(description="방법 id(백엔드가 정함, 열린 문자열).")
    label: NonEmptyStr = Field(description="버튼 문구(사용자 언어, 예: 구독으로 로그인).")
    description: str = Field(default="", description="방법 설명 한 줄.")
    notice: str = Field(
        default="",
        description="시작 확인 창에 늘 보이는 안내(예: 본인 구독·본인 책임 문구). 숨기기 없음.",
    )
    writes: list[str] = Field(
        default_factory=list,
        description=(
            "이 로그인이 이 PC에서 바꾸는 것(서버가 실제 경로로 풀어 준 줄, 사용자 언어)."
        ),
    )
    needs_browser: bool = Field(
        default=True, description="브라우저에서 로그인하는 단계가 있다(화면 안내용)."
    )


class BackendDescriptor(ContractModel):
    """실행 백엔드 디스크립터(X3)."""

    id: NonEmptyStr
    title: NonEmptyStr
    description: str = ""
    config_schema: JsonObject = Field(
        default_factory=dict, description="backend_options의 JSON Schema."
    )
    capabilities: BackendCapabilities = Field(default_factory=BackendCapabilities)
    collectors: list[CollectorDescriptor] = Field(
        default_factory=list,
        description="이 백엔드에서 쓸 수 있는 관측 수집기(X7). 설정 화면이 폼을 그린다.",
    )
    # 0.8.0(design §5.2R.3 #5): 백엔드 고르기 카드의 비용 문구·배지(`ui_hints.badge`).
    cost_note: str = Field(
        default="", description="비용 안내 한 줄(예: 구독 사용량을 씁니다). 비우면 표시 안 함."
    )
    probe_cost_note: str = Field(
        default="",
        description=(
            "연결 테스트 호출의 비용 안내 한 줄(확인 대화상자에 보임). 비우면 `cost_note`를 쓴다."
        ),
    )
    ui_hints: UiHints | None = None
    login_methods: list[LoginMethodInfo] = Field(
        default_factory=list,
        description=(
            "앱 화면에서 시작할 수 있는 로그인 방법(`capabilities.login`과 함께). "
            "비면 로그인 버튼 없음."
        ),
    )


class ModelInfo(ContractModel):
    """백엔드가 제공하는 모델 하나(`list_models()`). 모델 목록은 코드에 없다."""

    id: NonEmptyStr
    title: str | None = None
    description: str | None = None
    context_window: int | None = None
    attributes: JsonObject = Field(default_factory=dict)


class DelegationStrategyDescriptor(ContractModel):
    """위임 방식 디스크립터. 혼합 그래프 검증 규칙은 이 값으로 계산한다."""

    id: NonEmptyStr
    title: NonEmptyStr
    description: str = ""
    config_schema: JsonObject = Field(default_factory=dict)
    member_fields: list[str] = Field(
        description="위임받는 노드에 적용되는 AgentSettings 필드(나머지는 화면에서 회색)."
    )
    max_depth: int | None = Field(ge=1, description="위임 깊이 한도. null = 제한 없음.")
    allows_outgoing_flow: bool = Field(
        default=False, description="위임받는 노드가 흐름 연결을 내보낼 수 있는지."
    )
    requires_backend_capability: str | None = Field(
        default=None, description="위임자 백엔드에 필요한 능력 이름(BackendCapabilities 필드)."
    )
    member_interaction_kinds: list[str] | None = Field(
        default=None, description="위임받는 노드가 열 수 있는 상호작용 종류. null = 제한 없음."
    )
    composable: bool = Field(
        default=False,
        description=(
            "다른 composable 위임 방식과 한 위임자에서 합쳐 실행할 수 있다"
            "(혼합 위임). false인 방식이 다른 방식과 섞이면 `team.mixed_strategies`."
        ),
    )
    shares_session: bool = Field(
        default=True,
        description=(
            "위임받는 노드가 위임자 세션 안에서 실행되는지(0.8.0). false면 대상이 자기 세션에서 "
            "돌아 위임자 세션에 대상의 상호작용 권한을 더하지 않는다."
        ),
    )
    ui_hints: UiHints | None = None


class InteractionKindDescriptor(ContractModel):
    """상호작용 종류 디스크립터. 화면은 이것으로 카드·폼을 그린다."""

    id: NonEmptyStr
    version: int = 1
    title: NonEmptyStr
    description: str = ""
    request_schema: JsonObject = Field(
        default_factory=dict, description="요청 payload의 JSON Schema."
    )
    response_schema: JsonObject = Field(
        default_factory=dict,
        description="기본 응답 JSON Schema. 요청마다 자기 것으로 바꿀 수 있다.",
    )
    free_text_path: str | None = Field(
        default=None,
        pattern=r"^(/.*)?$",
        description="채팅 입력창 답을 넣을 응답 위치(JSON Pointer). null이면 입력창 답변 불가.",
    )
    expire_response: JsonObject | None = Field(
        default=None, description="만료·취소 때 요청자에게 돌려줄 응답."
    )
    ui_hints: UiHints | None = Field(
        default=None, description="renderer = 화면 렌더러 이름(모르면 스키마 폼)."
    )
