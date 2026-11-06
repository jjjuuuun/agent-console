"""SDD REST 요청·결과 모델, 오류 상세, 문서 상수(design §6R.6·§6R.7·§6R.18).

경로 문서(모델 아님): `/sdd/*`의 `?project=`(= 공간, 없으면 라이브러리 또는 단독 루트).
문서 상수(`Known*`)는 목록·enum이 아니다. 데이터·플러그인은 다른 값을 쓸 수 있고 화면은 모르는 값을
원문으로 보인다. 이름 → 값 표를 스키마 `x-constants`로 내보낸다.
"""

from typing import Final, Literal

from pydantic import Field

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr, Slug
from agent_console_contracts.common import SpaceRef
from agent_console_contracts.definitions import Issue

from ._views import ParsedTask, SpecIssue

type TemplateConflictPolicy = Literal["fail", "overwrite", "rename"]
"""틀로 저장할 때 같은 id가 있으면(고정 어휘): fail = 409 `sdd.template_exists`, overwrite = 덮어씀,
rename = 새 id(접미 번호)."""

type SaveAsTemplateStatus = Literal["created", "overwritten", "renamed"]
"""틀로 저장 결과(고정 어휘)."""


# ---------------------------------------------------------------- 만들기·가져오기·내보내기


class SpecCreateRequest(ContractModel):
    """`POST /sdd/specs` 요청. 응답은 `SpecView`(201)."""

    id: Slug | None = Field(default=None, description="스펙 id. 생략하면 이름에서 만든다.")
    name: NonEmptyStr
    description: str = ""
    template: Slug | None = Field(
        default=None,
        description=(
            "같은 공간의 문서 틀 id. 생략 = 빈 스펙(빈 문서 하나 + 규칙 비움). 다른 공간의 틀은 "
            "먼저 "
            "프로젝트로 복사한다."
        ),
    )


class SpecImportRequest(ContractModel):
    """`POST /sdd/specs/import`: 프로젝트 폴더 안 마크다운 파일을 새 스펙 본문으로 **복사**한다."""

    id: Slug | None = None
    name: NonEmptyStr
    files: list[NonEmptyStr] = Field(
        min_length=1, description="프로젝트 폴더 기준 상대 경로(링크·`..` 거부)."
    )


class SpecExportRequest(ContractModel):
    """`POST /sdd/specs/{id}/export`: 스펙 문서를 프로젝트 폴더 안 경로로 복사한다."""

    to_dir: NonEmptyStr = Field(description="프로젝트 폴더 기준 상대 경로(앱 구성 폴더 안은 거부).")
    overwrite: bool = Field(default=False, description="false면 있는 파일은 건너뛴다.")


class SpecExportResult(ContractModel):
    """폴더로 내보내기 결과."""

    to_dir: NonEmptyStr
    written: list[str] = Field(default_factory=list, description="쓴 파일(to_dir 기준).")
    skipped: list[str] = Field(default_factory=list, description="있어서 건너뛴 파일.")


class SaveAsTemplateRequest(ContractModel):
    """`POST /sdd/specs/{id}/save-as-template`: 스펙의 문서 목록·규칙을 문서 틀로 복사한다.

    문서 상태 값·상태 바꾼 기록은 빼고, `include_content=false`면 본문 파일은 빈 파일이다. 프로필의
    팀 구성은 함께 복사하지 않는다(틀은 id만 가진다).
    """

    name: NonEmptyStr
    id: Slug | None = Field(default=None, description="틀 id. 생략하면 이름에서 만든다.")
    include_content: bool = Field(default=False, description="문서 본문도 복사한다.")
    on_conflict: TemplateConflictPolicy = "fail"
    target: SpaceRef | None = Field(
        default=None, description="저장할 공간. 생략 = 라이브러리(공용 구성)."
    )


class SaveAsTemplateResult(ContractModel):
    """틀로 저장 결과."""

    template_id: NonEmptyStr = Field(description="저장한 문서 틀 id.")
    target: SpaceRef = Field(default_factory=SpaceRef)
    status: SaveAsTemplateStatus


# ---------------------------------------------------------------- 문서 본문·상태


class SpecDocumentContent(ContractModel):
    """`GET /sdd/specs/{id}/documents/{doc}` 응답: 본문 원문과 해시.

    본문 파일이 없으면 404 `sdd.document_missing`(읽기로 파일을 만들지 않는다).
    """

    document_id: NonEmptyStr
    file: NonEmptyStr
    content: str
    content_hash: NonEmptyStr = Field(description="본문 해시(`If-Match`).")
    issues: list[SpecIssue] = Field(
        default_factory=list, description="정보 이슈(예: `sdd.secret_suspect`, 위치만·값 없음)."
    )


class SpecDocumentWrite(ContractModel):
    """`PUT /sdd/specs/{id}/documents/{doc}` 요청. `If-Match` 본문 해시, 새로 만들 때만
    `If-None-Match: *`."""

    content: str


class DocumentStateChange(ContractModel):
    """`POST /sdd/specs/{id}/documents/{doc}/state` 요청: 문서 상태 전환(전환·관문 검사)."""

    to: NonEmptyStr
    note: str | None = Field(default=None, description="상태 바꾼 기록에 남길 한 줄.")


# ---------------------------------------------------------------- 작업 고치기·동작


class TaskPatch(ContractModel):
    """`PATCH /sdd/specs/{id}/tasks/{key}`: 작업 머리 줄의 상태·필드만 고친다(줄 하나)."""

    status: str | None = Field(default=None, description="바꿀 작업 상태 id. 생략 = 그대로.")
    fields: dict[str, str | None] | None = Field(
        default=None, description="바꿀 필드(값 null = 필드 지우기). 생략 = 그대로."
    )
    expected_line_hash: NonEmptyStr = Field(
        description="화면이 본 머리 줄 해시. 다르면 409 `sdd.task_changed`."
    )


class TaskPatchResult(ContractModel):
    """작업 고치기 결과."""

    task: ParsedTask
    version_hash: NonEmptyStr = Field(description="저장 뒤 스펙 정의 버전.")
    content_hash: NonEmptyStr = Field(description="저장 뒤 작업 문서 본문 해시.")


class SddTaskChangedDetails(ContractModel):
    """`sdd.task_changed`(HTTP 409) 오류의 `error.details`: 지금 머리 줄."""

    task_key: NonEmptyStr
    line_hash: str | None = Field(
        default=None, description="지금 머리 줄 해시(작업이 없으면 null)."
    )
    line: int | None = Field(default=None, ge=1)
    text: str | None = Field(default=None, description="지금 머리 줄 원문.")


class TaskActionKey(ContractModel):
    """작업 동작 하나를 가리키는 키(연동 id + 동작 id)."""

    integration: NonEmptyStr
    id: NonEmptyStr


class TaskAction(TaskActionKey):
    """작업 연동(X43)이 내는 동작 하나. 기본 연동은 실행 프로필마다 하나."""

    label: NonEmptyStr = Field(description="메뉴에 보일 이름(데이터 원문).")
    purpose: str | None = None
    disabled: Issue | None = Field(
        default=None, description="지금 쓸 수 없는 이유(예: 관문). null = 쓸 수 있음."
    )


class TaskActionRequest(ContractModel):
    """`POST /sdd/specs/{id}/tasks/{key}/actions/{integration}/{action}` 요청."""

    args: JsonObject = Field(default_factory=dict, description="동작이 정한 인자.")


class TaskActionResult(ContractModel):
    """작업 동작 결과. `status`는 열린 문자열(알려진 값 `KnownTaskActionStatuses`)."""

    task_key: str | None = None
    status: NonEmptyStr
    run_id: str | None = None
    issue: Issue | None = None


class BulkActionsRequest(ContractModel):
    """`POST /sdd/specs/{id}/bulk-actions`: 고른 작업들에서 쓸 수 있는 동작의 합집합."""

    task_keys: list[NonEmptyStr] = Field(min_length=1)


class BulkActionsResult(ContractModel):
    """한꺼번에 시작 대화상자의 동작 목록. 연동이 없으면 빈 목록."""

    actions: list[TaskAction] = Field(
        default_factory=list, description="합집합(연동·동작 id로 같은 것을 묶음)."
    )
    per_task: dict[str, list[TaskActionKey]] = Field(
        default_factory=dict, description="작업 키 → 그 작업에서 쓸 수 있는 동작."
    )


class BulkStartRequest(ContractModel):
    """`POST /sdd/specs/{id}/bulk-start`: 고른 작업을 한 동작으로 시작(상한
    `SddLimits.max_bulk_start`)."""

    task_keys: list[NonEmptyStr] = Field(min_length=1)
    action: TaskActionKey
    args: JsonObject = Field(default_factory=dict)


class BulkStartResult(ContractModel):
    """작업별 결과(그 동작이 안 맞는 작업은 `failed` + `sdd.action_unavailable`)."""

    items: list[TaskActionResult] = Field(default_factory=list)


class SddGateBlockedDetails(ContractModel):
    """`sdd.gate_blocked`(HTTP 422) 오류의 `error.details`, 동작의 `disabled.details`."""

    gate_id: NonEmptyStr
    message: str = ""
    document_ids: list[str] = Field(
        default_factory=list, description="관문 조건이 보는 문서 id(화면 [문서 열기])."
    )


class SddDocumentMissingDetails(ContractModel):
    """`sdd.document_missing`(HTTP 404) 오류의 `error.details`."""

    document_id: NonEmptyStr
    file: NonEmptyStr


class RulesCheckRequest(ContractModel):
    """`POST /sdd/templates/check`: 규칙·문서 목록 검사(저장하지 않음). 응답은
    `RulesCheckResult`."""

    rules: JsonObject = Field(default_factory=dict, description="규칙 문서(스펙 규칙 모양).")
    documents: list[JsonObject] = Field(default_factory=list, description="문서 목록.")


class RulesCheckResult(ContractModel):
    """규칙 검사 결과."""

    issues: list[SpecIssue] = Field(default_factory=list)


# ---------------------------------------------------------------- 문서 상수


class KnownDocumentRoles:
    """`SpecDocument.roles`의 알려진 값(파서가 읽는 역할). **문서 상수**다.

    `x-constants.KNOWN_DOCUMENT_ROLES`. 화면은 제안으로만 쓴다(열린 문자열).
    """

    REQUIREMENTS: Final = "requirements"
    TASKS: Final = "tasks"


class KnownTaskFieldRoles:
    """작업 필드 역할(코드 개념, 어느 필드가 그 역할인지는 문법 데이터 `roles`). **문서 상수**다.

    `x-constants.KNOWN_TASK_FIELD_ROLES`. 계획은 dependencies, 추적은 requirements를 읽는다.
    """

    DEPENDENCIES: Final = "dependencies"
    REQUIREMENTS: Final = "requirements"
    ASSIGNEE: Final = "assignee"
    WEIGHT: Final = "weight"
    """병목 계산 가중치(선택, 없으면 1)."""


class KnownGateTargets:
    """`SpecGate.applies_to`의 알려진 값. **문서 상수**다. `x-constants.KNOWN_GATE_TARGETS`."""

    RUN: Final = "run"
    """실행 시작 전."""
    TASK_STATUS: Final = "task_status"
    """작업 상태 바꾸기 전(고치기·실행 결과 반영·자동 진행)."""
    DOCUMENT_STATE: Final = "document_state"
    """문서 상태 전환 전."""


class KnownTransitionActors:
    """`StateTransition.by`의 알려진 값. **문서 상수**다. `x-constants.KNOWN_TRANSITION_ACTORS`."""

    HUMAN: Final = "human"
    """웹 사용자."""
    RUN: Final = "run"
    """실행 라벨이 있는 요청(실행 결과 반영)."""
    AGENT: Final = "agent"
    """예약(에이전트 도구)."""


class KnownTraceGaps:
    """`TraceRow.gaps`의 알려진 값. **문서 상수**다. `x-constants.KNOWN_TRACE_GAPS`."""

    NO_TASK: Final = "no_task"
    NO_RUN: Final = "no_run"
    NOT_VERIFIED: Final = "not_verified"
    VERIFICATION_FAILED: Final = "verification_failed"
    TASK_NOT_DONE: Final = "task_not_done"


class KnownTaskLinkKinds:
    """`TaskLink.kind`의 알려진 값. **문서 상수**다. `x-constants.KNOWN_TASK_LINK_KINDS`."""

    RUN: Final = "run"
    """`ref` = 루트 Run id."""


class KnownAutomationStopReasons:
    """`AutomationState.stopped_reason`의 알려진 값. **문서 상수**다.

    `x-constants.KNOWN_AUTOMATION_STOP_REASONS`.
    """

    USER: Final = "user"
    STAGE_DONE: Final = "stage_done"
    SPEC_DONE: Final = "spec_done"
    FAILURES: Final = "failures"
    LINK_DISABLED: Final = "link_disabled"


class KnownSyntaxSources:
    """`EffectiveSyntax.sources` 값의 알려진 값. **문서 상수**다.
    `x-constants.KNOWN_SYNTAX_SOURCES`."""

    DEFAULT: Final = "default"
    """패키지 기본 문법."""
    SETTINGS: Final = "settings"
    """앱 사용자 설정 sdd.syntax."""
    SPEC: Final = "spec"
    """스펙 규칙."""


class KnownTaskActionStatuses:
    """`TaskActionResult.status`의 알려진 값. **문서 상수**다.

    `x-constants.KNOWN_TASK_ACTION_STATUSES`. 화면은 모르는 값을 failed처럼 + 원문으로 보인다.
    """

    STARTED: Final = "started"
    BLOCKED: Final = "blocked"
    """관문에 막힘(`issue.code` = `sdd.gate_blocked`)."""
    FAILED: Final = "failed"


__all__ = [
    "BulkActionsRequest",
    "BulkActionsResult",
    "BulkStartRequest",
    "BulkStartResult",
    "DocumentStateChange",
    "KnownAutomationStopReasons",
    "KnownDocumentRoles",
    "KnownGateTargets",
    "KnownSyntaxSources",
    "KnownTaskActionStatuses",
    "KnownTaskFieldRoles",
    "KnownTaskLinkKinds",
    "KnownTraceGaps",
    "KnownTransitionActors",
    "RulesCheckRequest",
    "RulesCheckResult",
    "SaveAsTemplateRequest",
    "SaveAsTemplateResult",
    "SaveAsTemplateStatus",
    "SddDocumentMissingDetails",
    "SddGateBlockedDetails",
    "SddTaskChangedDetails",
    "SpecCreateRequest",
    "SpecDocumentContent",
    "SpecDocumentWrite",
    "SpecExportRequest",
    "SpecExportResult",
    "SpecImportRequest",
    "TaskAction",
    "TaskActionKey",
    "TaskActionRequest",
    "TaskActionResult",
    "TaskPatch",
    "TaskPatchResult",
    "TemplateConflictPolicy",
]
