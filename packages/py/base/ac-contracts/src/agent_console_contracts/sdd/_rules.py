"""SDD 사용자 데이터: 문서 틀(`SpecTemplate`)·스펙(`SpecDefinition`)·규칙(`SpecRules`)·작업 문법·
설정 섹션 `sdd`(`SddSettings`). 모두 모르는 키를 보존한다(손으로 고친 YAML 왕복).

모델 docstring과 필드 설명은 규칙 폼의 문구라 사용자 말로 쓰고, 개발자용 설명은 `#` 주석에 둔다
(설정 폼 도움말 린트 `schema-help-lint`가 이 스키마를 검사한다).

이름(문서 종류·상태·역할·프로필·관문·목적)은 전부 사용자 데이터다. 계약은 아무 이름도 모른다.
알려진 값은 문서 상수(`_api.py`의 `Known*`)로만 둔다.

규칙 키를 생략하면(None) 사용자 설정 `sdd.syntax` → 패키지 기본 문법 순으로 따른다(design §6R.1.3).
그래서 목록·객체 필드의 기본값은 빈 값이 아니라 None이다(빈 목록 = "이 스펙에서는 없음").
"""

from typing import Literal

from pydantic import ConfigDict, Field

from agent_console_contracts._base import DefinitionModel, JsonObject, NonEmptyStr, Slug
from agent_console_contracts.common import KnownUiWidgets, x_ui
from agent_console_contracts.runs import ConditionSpec

_ID_DESCRIPTION = "가리킬 때 쓰는 고유 이름입니다. 영문·숫자·-·_만 씁니다."
_TONE_DESCRIPTION = "칩 색조입니다(예: success, warning, danger). 모르는 값이면 기본 색입니다."

type SecretScanMode = Literal["off", "warn", "reject"]
"""문서 본문 비밀 의심 검사(고정 어휘): off = 검사 안 함, warn = 저장하고 정보 띠, reject = 거부."""

type AutomationScope = Literal["stage", "spec"]
"""자동 진행 범위(고정 어휘): stage = 지금 단계가 끝나면 멈춤, spec = 스펙 전체."""


# ---------------------------------------------------------------- 작업 문법(syntax)


class TaskStatusSpec(DefinitionModel):
    """작업 상태 하나입니다. 작업 줄의 체크 칸 글자로 상태를 구분합니다."""

    # 보기 응답의 풀린 라벨은 `TaskStatusInfo`(label 필수). 여기 label은 생략 가능(= id).

    id: Slug = Field(
        title="id",
        description="상태를 가리키는 이름입니다. 실행 결과 반영과 관문 조건이 이 이름을 씁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="상태를 새로 더할 때 한 번 정하세요.", example="doing", order=1
        ),
    )
    label: str | None = Field(
        default=None,
        title="표시 이름",
        description="화면에 보일 이름입니다. 비우면 id를 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="화면에 보이는 상태 이름을 바꾸고 싶을 때 바꾸세요.",
            example="진행 중",
        ),
    )
    marker: str | list[str] = Field(
        title="체크 칸 글자",
        description="작업 줄 대괄호 안의 글자입니다. 여러 개면 처음 것으로 씁니다(예: x와 X).",
        json_schema_extra=x_ui(
            tier="basic",
            when="문서에서 이 상태를 다른 글자로 적고 싶을 때 바꾸세요.",
            example="~",
            order=2,
        ),
    )
    done: bool = Field(
        default=False,
        title="끝난 상태",
        description="켜면 이 상태의 작업을 끝난 것으로 봅니다. 의존 작업의 준비 판단에 씁니다.",
        json_schema_extra=x_ui(tier="basic", when="완료로 칠 상태에서만 켜세요."),
    )
    tone: str | None = Field(
        default=None,
        title="색조",
        description=_TONE_DESCRIPTION,
        json_schema_extra=x_ui(tier="advanced", example="success", widget=KnownUiWidgets.TONE),
    )


class TaskSyntax(DefinitionModel):
    """작업 줄을 읽는 규칙입니다. 비운 항목은 앱 설정이나 기본 규칙을 따릅니다."""

    list_item: str | None = Field(
        default=None,
        title="작업 줄 모양",
        description="어떤 목록 항목을 작업으로 볼지입니다(예: checkbox = 체크 칸 목록).",
        json_schema_extra=x_ui(tier="advanced", example="checkbox"),
    )
    statuses: list[TaskStatusSpec] | None = Field(
        default=None,
        title="작업 상태",
        description="체크 칸 글자와 상태의 짝입니다. 규칙의 작업 상태가 있으면 그쪽이 먼저입니다.",
        json_schema_extra=x_ui(tier="advanced", item_title="/label"),
    )
    id_pattern: str | None = Field(
        default=None,
        title="작업 id 찾기",
        description="작업 줄 머리에서 작업 id를 찾는 정규식입니다. id 이름의 묶음을 씁니다.",
        json_schema_extra=x_ui(
            tier="advanced", example=r"^(?P<id>[0-9A-Za-z][\w.\-]*)\s+", widget=KnownUiWidgets.REGEX
        ),
    )
    field_pattern: str | None = Field(
        default=None,
        title="필드 찾기",
        description=(
            "작업 줄에서 [키: 값] 같은 필드를 찾는 정규식입니다. key와 value 묶음을 씁니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example=r"\[(?P<key>[\w\-]+):\s*(?P<value>[^\]]*)\]",
            widget=KnownUiWidgets.REGEX,
        ),
    )
    list_separator: str | None = Field(
        default=None,
        title="값 나누기 글자",
        description="필드 값 하나에 여러 값을 적을 때 사이에 넣는 글자입니다.",
        json_schema_extra=x_ui(tier="advanced", example=","),
    )
    range_separator: str | None = Field(
        default=None,
        title="범위 글자",
        description="두 작업 id 사이에 넣어 문서 순서상 그 사이 작업 전부를 뜻하는 글자입니다.",
        json_schema_extra=x_ui(tier="advanced", example="~"),
    )
    none_values: list[str] | None = Field(
        default=None,
        title="값 없음 표시",
        description="필드 값이 이 중 하나면 값이 없는 것으로 봅니다(예: 대시).",
        json_schema_extra=x_ui(tier="advanced", example=["—", "-"]),
    )
    roles: dict[str, str] | None = Field(
        default=None,
        title="필드 역할",
        description="필드 이름 → 역할입니다. 의존·요구·담당 역할을 계획과 추적 표가 읽습니다.",
        json_schema_extra=x_ui(
            tier="advanced", example={"depends": "dependencies", "req": "requirements"}
        ),
    )
    body: str | None = Field(
        default=None,
        title="작업 본문",
        description="작업 아래 들여쓴 목록·문단을 작업 본문으로 볼지입니다(예: nested).",
        json_schema_extra=x_ui(tier="advanced", example="nested"),
    )
    max_depth: int | None = Field(
        default=None,
        ge=1,
        title="작업 깊이",
        description="몇 단계까지 들여쓴 체크 칸을 작업으로 볼지입니다. 비우면 모두 봅니다.",
        json_schema_extra=x_ui(tier="advanced", example=2),
    )


class RequirementSyntax(DefinitionModel):
    """요구 문서에서 요구 id를 찾는 규칙입니다."""

    patterns: list[str] | None = Field(
        default=None,
        title="요구 id 찾기",
        description="줄마다 시험할 정규식 목록입니다. id 이름의 묶음이 요구 id입니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            example=[r"^\*\*(?P<id>[A-Z][A-Za-z]*\d[\w.]*)\*\*"],
            widget=KnownUiWidgets.REGEX,
        ),
    )


class StageSyntax(DefinitionModel):
    """작업 문서의 제목을 단계로 보는 규칙입니다."""

    heading_levels: list[int] | None = Field(
        default=None,
        title="단계 제목 수준",
        description="이 수준의 제목(2 = 두 번째 큰 제목)을 단계로 봅니다.",
        json_schema_extra=x_ui(tier="advanced", example=[2, 3]),
    )
    pattern: str | None = Field(
        default=None,
        title="단계 id 찾기",
        description="제목에서 단계 id를 찾는 정규식입니다. 비우면 제목 전체를 씁니다.",
        json_schema_extra=x_ui(tier="advanced", example=None, widget=KnownUiWidgets.REGEX),
    )


class SpecSyntax(DefinitionModel):
    """작업·요구·단계를 문서에서 읽는 규칙입니다. 비운 항목은 앱 설정이나 기본 규칙을 따릅니다."""

    # 병합: 패키지 기본(include_default_syntax) → 사용자 설정 sdd.syntax → 스펙 rules.syntax.
    # 키 단위 덮어쓰기, 목록은 통째로 바꾼다.

    task: TaskSyntax | None = Field(
        default=None,
        title="작업 줄",
        description="작업 줄을 읽는 규칙입니다.",
        json_schema_extra=x_ui(tier="advanced", order=1),
    )
    requirement: RequirementSyntax | None = Field(
        default=None,
        title="요구 id",
        description="요구 문서에서 요구 id를 찾는 규칙입니다.",
        json_schema_extra=x_ui(tier="advanced", order=2),
    )
    stage: StageSyntax | None = Field(
        default=None,
        title="단계",
        description="작업 문서의 제목을 단계로 보는 규칙입니다.",
        json_schema_extra=x_ui(tier="advanced", order=3),
    )


# ---------------------------------------------------------------- 문서 상태·전환


class DocumentStateOnEdit(DefinitionModel):
    """이 상태의 문서 본문을 고쳤을 때 바꿀 상태입니다."""

    to: NonEmptyStr = Field(
        title="바꿀 상태",
        description="본문을 고치면 이 문서 상태로 돌아갑니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="승인 뒤 고친 문서를 다시 검토받게 하고 싶을 때 고르세요.",
            example="draft",
            widget=KnownUiWidgets.STATE_REF,
        ),
    )


class DocumentStateSpec(DefinitionModel):
    """문서 상태 하나입니다(예: 초안, 검토 중, 승인됨)."""

    id: Slug = Field(
        title="id",
        description="상태를 가리키는 이름입니다. 전환 규칙과 관문 조건이 이 이름을 씁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="상태를 새로 더할 때 한 번 정하세요.", example="approved", order=1
        ),
    )
    label: str | None = Field(
        default=None,
        title="표시 이름",
        description="화면에 보일 이름입니다. 비우면 id를 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="화면에 보이는 상태 이름을 바꾸고 싶을 때 바꾸세요.",
            example="승인됨",
        ),
    )
    tone: str | None = Field(
        default=None,
        title="색조",
        description=_TONE_DESCRIPTION,
        json_schema_extra=x_ui(tier="advanced", example="success", widget=KnownUiWidgets.TONE),
    )
    on_edit: DocumentStateOnEdit | None = Field(
        default=None,
        title="고치면",
        description="이 상태의 문서 본문을 고쳤을 때 바꿀 상태입니다. 비우면 그대로 둡니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class StateTransition(DefinitionModel):
    """문서 상태를 바꿀 수 있는 길 하나입니다. 누가 바꿀 수 있는지도 정합니다."""

    from_: NonEmptyStr = Field(
        alias="from",
        title="이전 상태",
        description="이 상태에서 출발합니다. 별표(*)는 어느 상태에서나 뜻입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="이 전환을 쓸 수 있는 출발 상태를 바꿀 때 고르세요.",
            example="review",
            widget=KnownUiWidgets.STATE_REF,
            order=1,
        ),
    )
    to: NonEmptyStr = Field(
        title="다음 상태",
        description="이 상태로 바꿉니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="전환이 도착할 상태를 바꿀 때 고르세요.",
            example="approved",
            widget=KnownUiWidgets.STATE_REF,
            order=2,
        ),
    )
    by: list[str] = Field(
        default_factory=list,
        title="바꿀 수 있는 쪽",
        description=(
            "이 전환을 할 수 있는 쪽입니다(예: human = 사람, run = 실행). 비우면 아무도 못 합니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="사람만 승인하게 하거나 실행도 바꾸게 할 때 고치세요.",
            example=["human"],
        ),
    )


# ---------------------------------------------------------------- 관문·실행 프로필·검증·자동 진행


class SpecGate(DefinitionModel):
    """관문 하나입니다. 조건이 맞지 않으면 실행이나 상태 바꾸기를 막고 안내 문장을 보입니다."""

    # 조건 맥락: {spec: {id, name}, documents: {<id>: {state}}, task: {key, id, status, fields,
    # ready, stage}, stage: {id, done, total}}. 평가는 ac-conditions(ac-sdd.evaluate_gates).

    id: Slug = Field(
        title="id",
        description=_ID_DESCRIPTION,
        json_schema_extra=x_ui(
            tier="basic", when="관문을 새로 더할 때 한 번 정하세요.", example="design-approved"
        ),
    )
    applies_to: list[str] = Field(
        default_factory=list,
        title="막을 일",
        description=(
            "이 관문이 막는 일입니다(run = 실행, task_status = 작업 상태, document_state = 문서 "
            "상태)."
        ),
        json_schema_extra=x_ui(
            tier="basic", when="관문이 막을 일을 더하거나 뺄 때 고치세요.", example=["run"]
        ),
    )
    require: ConditionSpec = Field(
        default_factory=ConditionSpec,
        title="통과 조건",
        description="이 조건이 맞아야 지나갑니다. 예: 설계 문서 상태가 승인됨.",
        json_schema_extra=x_ui(
            tier="basic",
            when="무엇이 끝나야 지나갈지 바꿀 때 고치세요.",
            widget=KnownUiWidgets.CONDITION,
        ),
    )
    message: str = Field(
        default="",
        title="안내 문장",
        description="막혔을 때 화면에 보일 문장입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="막힌 이유를 사람이 알기 쉽게 적고 싶을 때 고치세요.",
            example="설계가 승인되기 전에는 작업을 실행하지 않습니다",
        ),
    )


class RunProfile(DefinitionModel):
    """실행 프로필 하나입니다. 작업을 어느 팀 구성에 어떤 입력으로 맡길지 정합니다."""

    # input 값의 문자열은 ac-text-template로 치환한다(변수 표는 GET …/variables).
    # status_on 키 = 실행 상태(started·succeeded·failed·cancelled·interrupted, 열린 문자열),
    # 값 = 작업 상태 id. 비우면 상태를 바꾸지 않는다(K6R-6).

    id: Slug = Field(
        title="id",
        description=_ID_DESCRIPTION,
        json_schema_extra=x_ui(
            tier="basic", when="프로필을 새로 더할 때 한 번 정하세요.", example="implement", order=1
        ),
    )
    title: NonEmptyStr = Field(
        title="이름",
        description="실행 메뉴에 보일 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="실행 메뉴에서 알아보기 쉬운 이름으로 바꾸고 싶을 때 바꾸세요.",
            example="구현",
            order=2,
        ),
    )
    graph: NonEmptyStr = Field(
        title="팀 구성",
        description="작업을 맡길 팀 구성입니다. 그 프로젝트에 있는 팀 구성이어야 합니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="작업을 다른 팀에게 맡기고 싶을 때 고르세요.",
            example="dev-team",
            widget=KnownUiWidgets.GRAPH_REF,
            order=3,
        ),
    )
    when: ConditionSpec | None = Field(
        default=None,
        title="보일 작업",
        description="이 조건에 맞는 작업에만 메뉴에 보입니다. 비우면 모든 작업에 보입니다.",
        json_schema_extra=x_ui(tier="advanced", widget=KnownUiWidgets.CONDITION),
    )
    input: JsonObject = Field(
        default_factory=dict,
        title="입력",
        description=(
            "팀 구성 입력 이름 → 값입니다. 값의 중괄호 변수(예: 작업 id)는 실행할 때 채웁니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="팀에게 보낼 요청 문장을 바꾸고 싶을 때 고치세요.",
            example={"request": "작업 {task_id} {task_title}"},
            widget=KnownUiWidgets.TEMPLATE_TEXT,
        ),
    )
    purpose: str | None = Field(
        default=None,
        title="목적",
        description="이 실행의 목적입니다(예: implement, verify). 검증 결과를 고를 때 씁니다.",
        json_schema_extra=x_ui(tier="advanced", example="verify"),
    )
    status_on: dict[str, str] = Field(
        default_factory=dict,
        title="결과에 따른 작업 상태",
        description=(
            "실행 상태(예: succeeded) → 바꿀 작업 상태입니다. 비우면 작업 상태를 바꾸지 않습니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="실행이 끝나면 작업 표시를 자동으로 바꾸고 싶을 때 고치세요.",
            example={"started": "doing", "succeeded": "review"},
            widget=KnownUiWidgets.STATUS_REF,
        ),
    )


class VerificationConfig(DefinitionModel):
    """어떤 실행을 검증으로 볼지와 실행 결과를 검증 결과로 바꾸는 표입니다."""

    purposes: list[str] = Field(
        default_factory=list,
        title="검증 목적",
        description="이 목적의 실행 프로필로 돌린 실행을 검증으로 봅니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="검증으로 칠 실행 프로필 목적을 바꿀 때 고치세요.",
            example=["verify"],
        ),
    )
    result_map: dict[str, str] = Field(
        default_factory=dict,
        title="결과 바꾸기",
        description="실행 상태 → 검증 결과(예: succeeded → pass)입니다. 없는 상태는 그대로 씁니다.",
        json_schema_extra=x_ui(tier="advanced", example={"succeeded": "pass", "failed": "fail"}),
    )


class AutomationConfig(DefinitionModel):
    """자동 진행입니다. 켜면 의존이 끝난 작업을 차례로 실행합니다."""

    # link-runs-sdd가 실행이 끝날 때마다 ready 작업을 max_parallel까지 시작한다(design §6R.1.5).

    enabled: bool = Field(
        default=False,
        title="켜기",
        description="켜면 준비된 작업을 자동으로 시작합니다. 기본은 꺼짐입니다.",
        json_schema_extra=x_ui(tier="basic", when="작업을 하나씩 직접 시작하지 않으려면 켜세요."),
    )
    profile: str | None = Field(
        default=None,
        title="실행 프로필",
        description="자동으로 시작할 때 쓸 실행 프로필입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="자동 진행에 다른 실행 프로필을 쓰고 싶을 때 고르세요.",
            example="implement",
            widget=KnownUiWidgets.PROFILE_REF,
        ),
    )
    max_parallel: int = Field(
        default=1,
        ge=1,
        title="동시 실행 수",
        description="한 번에 돌릴 작업 수의 상한입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="여러 작업을 함께 돌리고 싶을 때 늘리세요.", unit="개"
        ),
    )
    max_failures: int = Field(
        default=3,
        ge=1,
        title="실패 상한",
        description="같은 작업이 이만큼 연달아 실패하면 그 작업을 건너뜁니다.",
        json_schema_extra=x_ui(tier="advanced", unit="번"),
    )
    scope: AutomationScope = Field(
        default="stage",
        title="범위",
        description="지금 단계가 끝나면 멈출지, 스펙 전체를 이어 갈지 고릅니다.",
        json_schema_extra=x_ui(
            tier="advanced", enum_labels={"stage": "단계까지", "spec": "스펙 전체"}
        ),
    )


class SpecRules(DefinitionModel):
    """스펙 규칙입니다. 문서 상태·승인, 작업 상태, 관문, 실행 프로필, 검증, 자동 진행을 정합니다."""

    # 생략(None) = 사용자 설정 → 패키지 기본(문법·작업 상태). 문서 상태·관문·프로필은 기본이 없다.

    syntax: SpecSyntax | None = Field(
        default=None,
        title="작업 문법",
        description=(
            "작업·요구·단계를 문서에서 읽는 규칙입니다. 비우면 앱 설정과 기본 규칙을 씁니다."
        ),
        json_schema_extra=x_ui(tier="advanced", order=8),
    )
    document_states: list[DocumentStateSpec] | None = Field(
        default=None,
        title="문서 상태",
        description=(
            "문서가 가질 수 있는 상태입니다(예: 초안, 승인됨). 비우면 상태를 쓰지 않습니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="문서 승인 단계를 더하거나 이름을 바꿀 때 고치세요.",
            item_title="/label",
            order=1,
        ),
    )
    initial_document_state: str | None = Field(
        default=None,
        title="처음 문서 상태",
        description="새 문서가 갖는 상태입니다. 비우면 문서 상태 목록의 첫 번째입니다.",
        json_schema_extra=x_ui(tier="advanced", example="draft", widget=KnownUiWidgets.STATE_REF),
    )
    transitions: list[StateTransition] | None = Field(
        default=None,
        title="상태 전환",
        description="문서 상태를 바꿀 수 있는 길과 바꿀 수 있는 쪽입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="누가 승인할 수 있는지 바꿀 때 고치세요.",
            item_title="/to",
            order=2,
        ),
    )
    task_statuses: list[TaskStatusSpec] | None = Field(
        default=None,
        title="작업 상태",
        description="작업 상태와 체크 칸 글자입니다. 비우면 작업 문법의 상태를 씁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="진행 중·검증 대기 같은 상태를 더할 때 고치세요.",
            item_title="/label",
            order=3,
        ),
    )
    gates: list[SpecGate] | None = Field(
        default=None,
        title="관문",
        description="조건이 맞기 전에는 실행이나 상태 바꾸기를 막습니다. 기본은 없습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="설계 승인 전 실행 금지 같은 규칙을 두고 싶을 때 더하세요.",
            item_title="/id",
            order=4,
        ),
    )
    run_profiles: list[RunProfile] | None = Field(
        default=None,
        title="실행 프로필",
        description="작업을 맡길 팀 구성과 입력입니다. 작업의 실행 메뉴에 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="작업을 실행할 팀이나 요청 문장을 바꿀 때 고치세요.",
            item_title="/title",
            order=5,
        ),
    )
    verification: VerificationConfig | None = Field(
        default=None,
        title="검증",
        description="어떤 실행을 검증으로 볼지 정합니다. 추적 표의 검증 열에 씁니다.",
        json_schema_extra=x_ui(tier="advanced", order=6),
    )
    automation: AutomationConfig | None = Field(
        default=None,
        title="자동 진행",
        description="준비된 작업을 자동으로 시작하는 설정입니다. 비우면 꺼짐입니다.",
        json_schema_extra=x_ui(tier="advanced", order=7),
    )


# ---------------------------------------------------------------- 문서·틀·스펙


class StateChange(DefinitionModel):
    """문서 상태를 마지막으로 바꾼 기록입니다. 앱이 채웁니다."""

    by: NonEmptyStr = Field(
        title="바꾼 쪽",
        description="상태를 바꾼 쪽입니다(예: human = 사람, run = 실행).",
        json_schema_extra=x_ui(tier="advanced", example="human"),
    )
    at: float = Field(
        title="시각",
        description="바꾼 시각입니다(1970년부터 센 초).",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
    )
    run_id: str | None = Field(
        default=None,
        title="실행",
        description="실행이 바꿨으면 그 실행 id입니다.",
        json_schema_extra=x_ui(tier="advanced", example=None),
    )
    note: str | None = Field(
        default=None,
        title="메모",
        description="바꿀 때 남긴 한 줄 메모입니다.",
        json_schema_extra=x_ui(tier="advanced", example="검토 완료"),
    )


class SpecDocument(DefinitionModel):
    """스펙 문서 하나입니다. 순서대로 탭에 보입니다."""

    id: Slug = Field(
        title="id",
        description="문서를 가리키는 이름입니다. 관문 조건과 입력 틀 변수가 이 이름을 씁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="문서를 새로 더할 때 한 번 정하세요.", example="design", order=1
        ),
    )
    title: NonEmptyStr = Field(
        title="제목",
        description="탭과 목록에 보일 문서 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="탭에 보이는 이름을 바꾸고 싶을 때 바꾸세요.",
            example="설계",
            order=2,
        ),
    )
    file: NonEmptyStr = Field(
        title="파일",
        description="본문 파일 이름입니다. 스펙 폴더 안 상대 경로만 씁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="본문 파일 이름을 바꾸고 싶을 때 바꾸세요.",
            example="design.md",
            order=3,
        ),
    )
    roles: list[str] = Field(
        default_factory=list,
        title="쓰임",
        description=(
            "이 문서를 무엇으로 읽을지입니다(requirements = 요구, tasks = 작업). 비우면 읽기만 "
            "합니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="작업 목록이나 요구 id를 이 문서에서 읽게 할 때 고르세요.",
            example=["tasks"],
        ),
    )
    state: str | None = Field(
        default=None,
        title="상태",
        description="지금 문서 상태입니다. 상태 전환 버튼으로 바꿉니다.",
        json_schema_extra=x_ui(tier="advanced", example="draft", widget=KnownUiWidgets.STATE_REF),
    )
    state_changed: StateChange | None = Field(
        default=None,
        title="상태 바꾼 기록",
        description="상태를 마지막으로 바꾼 쪽과 시각입니다. 앱이 채웁니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class SpecContentRef(DefinitionModel):
    """정의 파일 옆 본문 폴더의 대표 파일입니다."""

    file: NonEmptyStr = Field(
        title="대표 파일",
        description="본문 폴더 안에서 먼저 열 파일입니다.",
        json_schema_extra=x_ui(tier="advanced", example="requirements.md"),
    )


class _SpecCommon(DefinitionModel):
    """문서 틀과 스펙의 공통 필드(내부 베이스, 스키마에 따로 나오지 않는다)."""

    kind: NonEmptyStr = Field(
        title="종류",
        description="정의 종류 이름입니다. 직접 바꾸지 않습니다.",
        json_schema_extra=x_ui(tier="advanced", example="spec"),
    )
    id: Slug = Field(
        title="id", description=_ID_DESCRIPTION, json_schema_extra=x_ui(tier="advanced")
    )
    schema_version: int = Field(
        default=1,
        title="형식 버전",
        description="파일 형식 번호입니다. 직접 바꾸지 않습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    name: NonEmptyStr = Field(
        title="이름",
        description="목록에 보일 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="목록에서 알아보기 쉬운 이름으로 바꾸고 싶을 때 바꾸세요.",
            example="결제 v2",
        ),
    )
    description: str = Field(
        default="",
        title="설명",
        description="무엇을 위한 것인지 적습니다. 목록에 함께 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="목록에서 쓰임새를 알리고 싶을 때 적으세요.",
            example="요구 → 설계 → 작업 순서로 씁니다",
        ),
    )
    documents: list[SpecDocument] = Field(
        default_factory=list,
        title="문서",
        description="문서 목록입니다. 순서대로 탭에 보입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="문서를 더하거나 순서를 바꿀 때 고치세요.", item_title="/title"
        ),
    )
    rules: SpecRules = Field(
        default_factory=SpecRules,
        title="규칙",
        description="문서 상태·작업 상태·관문·실행 프로필 같은 규칙입니다.",
        json_schema_extra=x_ui(tier="basic", when="승인 단계나 실행 방법을 바꿀 때 고치세요."),
    )
    labels: list[str] = Field(
        default_factory=list,
        title="라벨",
        description="찾기·거르기에 쓰는 꼬리표입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    attributes: JsonObject = Field(
        default_factory=dict,
        title="기타 속성",
        description="다른 도구가 읽는 자유 속성입니다. 보통은 비워 둡니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    content: SpecContentRef | None = Field(
        default=None,
        title="본문",
        description="본문 폴더의 대표 파일입니다. 앱이 채웁니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class SpecTemplate(_SpecCommon):
    """문서 틀입니다. 스펙을 만들 때 문서 뼈대와 규칙을 그대로 복사합니다."""

    # 정의 종류 이름(kind)은 mod-sdd 데이터(기본 spec-template). 라이브러리·프로젝트 공간, 옮길 수
    # 있음.

    model_config = ConfigDict(title="문서 틀")


class SpecDefinition(_SpecCommon):
    """스펙입니다. 문서와 문서 상태, 이 스펙의 규칙을 담습니다."""

    # 정의 종류 이름(kind)은 mod-sdd 데이터(기본 spec). 프로젝트·단독 공간에만(library=False).
    # 만들 때 틀의 documents·rules를 복사하고 이후 틀과 독립(틀 id·버전을 쓰지 않는다, K33-17).

    model_config = ConfigDict(title="스펙")


# ---------------------------------------------------------------- 사용자 설정 섹션 sdd


class VerificationSourceSetting(DefinitionModel):
    """검증 결과를 가져올 곳 하나입니다(예: 테스트 결과 파일)."""

    id: NonEmptyStr = Field(
        title="출처",
        description="설치된 검증 결과 출처의 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="다른 검증 결과 출처를 쓰고 싶을 때 고르세요.", example="junit"
        ),
    )
    enabled: bool = Field(
        default=True,
        title="켜기",
        description="끄면 이 출처의 결과를 추적 표에 넣지 않습니다.",
        json_schema_extra=x_ui(tier="basic", when="잠시 이 출처를 쓰지 않으려면 끄세요."),
    )
    options: JsonObject = Field(
        default_factory=dict,
        title="옵션",
        description="출처가 정한 설정입니다(예: 결과 파일 위치).",
        json_schema_extra=x_ui(tier="advanced", example={"path": "reports/junit.xml"}),
    )


class SddSettings(DefinitionModel):
    """스펙 기능의 작업 문법, 비밀 검사, 검증 결과 출처를 정합니다."""

    # 워크스페이스 설정의 sdd 섹션(mod-sdd가 소유, 공통 설정 모델에는 필드 없음 — 메모리 설정과 같은
    # 방식). 깨진 부분만 빼고 경고(sdd.settings_invalid), 모르는 키 보존.

    model_config = ConfigDict(title="스펙")

    include_default_syntax: bool = Field(
        default=True,
        title="기본 작업 문법 사용",
        description="앱이 주는 기본 작업 문법(체크 칸 작업 줄 등)을 씁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="기본 문법 대신 내가 만든 문법만 쓰고 싶을 때 끄세요."
        ),
    )
    syntax: SpecSyntax | None = Field(
        default=None,
        title="작업 문법",
        description="모든 스펙에 쓸 작업 문법입니다. 스펙 규칙이 있으면 그쪽이 먼저입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    secret_scan: SecretScanMode = Field(
        default="warn",
        title="비밀 값 검사",
        description="문서 본문에 비밀로 보이는 값이 있을 때 어떻게 할지 고릅니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="오탐이 많으면 끄고, 비밀이 섞이면 안 되면 거부로 바꾸세요.",
            enum_labels={"off": "검사 안 함", "warn": "알리고 저장", "reject": "저장 거부"},
        ),
    )
    verification_sources: list[VerificationSourceSetting] = Field(
        default_factory=list,
        title="검증 결과 출처",
        description="실행 말고 다른 곳(예: 테스트 결과 파일)에서 검증 결과를 가져옵니다.",
        json_schema_extra=x_ui(tier="advanced", item_title="/id"),
    )


__all__ = [
    "AutomationConfig",
    "AutomationScope",
    "DocumentStateOnEdit",
    "DocumentStateSpec",
    "RequirementSyntax",
    "RunProfile",
    "SddSettings",
    "SecretScanMode",
    "SpecContentRef",
    "SpecDefinition",
    "SpecDocument",
    "SpecGate",
    "SpecRules",
    "SpecSyntax",
    "SpecTemplate",
    "StageSyntax",
    "StateChange",
    "StateTransition",
    "TaskStatusSpec",
    "TaskSyntax",
    "VerificationConfig",
    "VerificationSourceSetting",
]
