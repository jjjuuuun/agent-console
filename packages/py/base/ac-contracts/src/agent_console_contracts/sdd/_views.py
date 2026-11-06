"""SDD 보기(응답) 모델: 파싱 결과·계획·추적·화면 정보. 저장하지 않는 계산 결과다(design
§6R.1.3·§6R.1.6).

작업 키 = 작업 id(있으면), 없으면 `@<문서 id>:<그 문서 안 작업 순번>`(K6R-4). 상태·문서 종류 라벨은
서버가 늘 채운다(§6R.18 Q1 — 웹에 상태 이름 표를 두지 않는다).
"""

from pydantic import Field

from agent_console_contracts._base import ContractModel, NonEmptyStr
from agent_console_contracts.common import LabelDisplay, SpaceRef, Usage
from agent_console_contracts.definitions import Issue

from ._rules import SpecDefinition, SpecDocument, SpecSyntax


class SpecIssue(Issue):
    """스펙 파싱·규칙 검사 이슈. `Issue`에 문서·줄·작업 위치를 더한다(값 원문은 담지 않는다).

    알려진 코드는 `KnownIssueCodes`의 `sdd.*`(열린 문자열).
    """

    document: str | None = Field(default=None, description="문서 id(문서 하나에 걸린 이슈).")
    line: int | None = Field(default=None, ge=1, description="그 문서의 줄 번호(1부터).")
    task_key: str | None = Field(default=None, description="작업 하나에 걸린 이슈면 작업 키.")


# ---------------------------------------------------------------- 풀린 상태 라벨


class TaskStatusInfo(ContractModel):
    """작업 상태 하나(보기용, 라벨이 늘 채워짐 — 데이터의 label → 없으면 id)."""

    id: NonEmptyStr
    label: NonEmptyStr
    markers: list[str] = Field(
        default_factory=list, description="체크 칸 글자(첫 번째가 상태를 바꿀 때 쓰는 글자)."
    )
    done: bool = False
    tone: str | None = Field(default=None, description="색조(열린 문자열).")


class DocumentStateInfo(ContractModel):
    """문서 상태 하나(보기용, 라벨이 늘 채워짐)."""

    id: NonEmptyStr
    label: NonEmptyStr
    tone: str | None = None


# ---------------------------------------------------------------- 파싱 결과(SpecIndex)


class ParsedDocument(ContractModel):
    """문서 하나의 파싱 상태."""

    id: NonEmptyStr
    file: NonEmptyStr
    roles: list[str] = Field(default_factory=list)
    exists: bool = Field(
        default=True, description="본문 파일이 있는가(없으면 다른 값은 비어 있다)."
    )
    content_hash: str | None = Field(default=None, description="본문 파일 해시(`If-Match`용).")
    tasks: int = Field(default=0, ge=0, description="이 문서에서 찾은 작업 수.")
    requirements: int = Field(default=0, ge=0, description="이 문서에서 찾은 요구 수.")


class ParsedRequirement(ContractModel):
    """요구 역할 문서에서 찾은 요구 하나."""

    id: NonEmptyStr
    title: str = Field(default="", description="그 줄의 나머지 글(요구 제목 추정).")
    document: NonEmptyStr = Field(description="문서 id.")
    line: int = Field(ge=1)


class StageRef(ContractModel):
    """단계 하나를 가리키는 키와 제목."""

    id: NonEmptyStr
    title: str = ""


class ParsedStage(StageRef):
    """작업 문서의 단계(제목) 하나와 진행."""

    document: NonEmptyStr
    line: int = Field(ge=1)
    done: int = Field(default=0, ge=0, description="끝난 작업 수.")
    total: int = Field(default=0, ge=0, description="작업 수.")


class TaskLink(ContractModel):
    """작업과 이어진 외부 항목 하나(작업 연동 X43이 낸다). 기본 연동은 실행(`kind=run`, `ref`=Run
    id)."""

    integration: NonEmptyStr = Field(description="연동 id(열린 문자열).")
    kind: NonEmptyStr = Field(description="항목 종류(열린 문자열, 알려진 값 `KnownTaskLinkKinds`).")
    ref: NonEmptyStr = Field(description="항목 id(실행이면 루트 Run id).")
    task_key: str | None = Field(default=None, description="이 연결이 가리키는 작업 키.")
    status: str | None = Field(default=None, description="항목 상태(실행이면 Run 상태).")
    at: float | None = Field(default=None, description="항목 시각(Unix epoch 초).")
    purpose: str | None = Field(default=None, description="실행 프로필 목적(있으면).")
    profile: str | None = Field(default=None, description="실행 프로필 id(있으면).")
    totals: Usage | None = Field(default=None, description="토큰·비용 합(실행이면 `Run.totals`).")


class ParsedTask(ContractModel):
    """작업 문서에서 찾은 작업 하나."""

    key: NonEmptyStr = Field(description="작업 키(작업 id, 없으면 `@문서:순번`).")
    id: str | None = Field(default=None, description="작업 줄 머리의 작업 id(없으면 null).")
    title: str = ""
    status: NonEmptyStr = Field(description="작업 상태 id(`TaskStatusInfo.id`).")
    fields: dict[str, str] = Field(default_factory=dict, description="`[키: 값]` 필드 원문.")
    requirements: list[str] = Field(default_factory=list, description="요구 역할 필드의 요구 id.")
    dependencies: list[str] = Field(
        default_factory=list, description="의존 역할 필드의 작업 키(범위는 풀어 둠)."
    )
    stage: StageRef | None = None
    document: NonEmptyStr = Field(description="문서 id.")
    line: int = Field(ge=1, description="머리 줄 번호(1부터).")
    line_hash: NonEmptyStr = Field(description="머리 줄 해시(상태 고치기 `expected_line_hash`).")
    ready: bool = Field(default=False, description="끝나지 않았고 의존 작업이 모두 끝났다(준비됨).")
    body: str = Field(default="", description="작업 본문(하위 목록·문단 원문).")
    links: list[TaskLink] = Field(
        default_factory=list, description="이어진 항목(최근 순, 연동이 없으면 빈 값)."
    )
    issues: list[SpecIssue] = Field(
        default_factory=list,
        description=(
            "작업 이슈: 파싱 이슈 + 작업 연동(X43)의 선택 메서드 `task_issues`가 낸 것"
            "(예: `sdd.status_not_applied`·`sdd.automation_skipped`)."
        ),
    )


class SpecIndex(ContractModel):
    """스펙 문서를 파싱한 결과(읽을 때마다 계산, 저장하지 않음)."""

    documents: list[ParsedDocument] = Field(default_factory=list)
    requirements: list[ParsedRequirement] = Field(default_factory=list)
    stages: list[ParsedStage] = Field(default_factory=list)
    tasks: list[ParsedTask] = Field(default_factory=list)
    issues: list[SpecIssue] = Field(default_factory=list)


class EffectiveSyntax(ContractModel):
    """`GET /sdd/specs/{id}/syntax`: 병합한 작업 문법과 값마다 출처.

    `sources` 키 = 문법 문서 기준 위치(예: `/task/id_pattern`), 값 = 출처(열린 문자열, 알려진 값
    `KnownSyntaxSources` default·settings·spec). 기본 문법이 꺼졌으면 `default`는 나오지 않는다.
    """

    syntax: SpecSyntax = Field(default_factory=SpecSyntax)
    sources: dict[str, str] = Field(default_factory=dict)
    statuses: list[TaskStatusInfo] = Field(default_factory=list)
    empty: bool = Field(
        default=False, description="작업 문법이 비었다(작업·계획·추적 탭은 '작업 문법 없음')."
    )


# ---------------------------------------------------------------- 계획·추적


class TaskPlan(ContractModel):
    """`GET /sdd/specs/{id}/plan`: 끝나지 않은 작업의 의존 계획."""

    ready: list[str] = Field(default_factory=list, description="지금 시작할 수 있는 작업 키.")
    layers: list[list[str]] = Field(
        default_factory=list, description="위상 층(= 병렬 묶음), 앞에서부터 차례."
    )
    critical_path: list[str] = Field(
        default_factory=list, description="가장 긴 의존 사슬(= 병목), 시작 → 끝."
    )
    blocked: list[str] = Field(
        default_factory=list, description="끝나지 않은 의존이 있어 기다리는 작업 키."
    )
    cycles: list[list[str]] = Field(default_factory=list, description="순환 의존(이슈로도 낸다).")


class VerificationRef(ContractModel):
    """검증 결과의 근거: 실행 또는 프로젝트 폴더 안 파일."""

    run_id: str | None = None
    path: str | None = Field(default=None, description="프로젝트 폴더 기준 상대 경로.")


class VerificationResult(ContractModel):
    """검증 결과 하나(검증 결과 출처 X42가 낸다)."""

    source: NonEmptyStr = Field(description="출처 id(기본 `runs`).")
    status: NonEmptyStr = Field(description="결과(열린 문자열, 예: pass·fail·unknown).")
    task_key: str | None = None
    requirement_ids: list[str] = Field(default_factory=list)
    label: str = ""
    at: float | None = None
    ref: VerificationRef = Field(default_factory=VerificationRef)
    detail: str | None = None


class TraceVerification(ContractModel):
    """추적 행의 마지막 검증 결과 요약."""

    status: NonEmptyStr
    at: float | None = None
    source: str | None = None


class TraceRow(ContractModel):
    """추적 표의 요구 하나: 요구 → 작업 → 실행 → 검증."""

    id: NonEmptyStr = Field(description="요구 id.")
    title: str = ""
    document: NonEmptyStr
    line: int = Field(ge=1)
    tasks: list[str] = Field(default_factory=list, description="이 요구를 참조하는 작업 키.")
    runs: list[TaskLink] = Field(default_factory=list, description="이 작업들의 최근 실행.")
    totals: Usage | None = Field(default=None, description="이 작업들 실행의 토큰 합.")
    verification: TraceVerification | None = None
    results: list[VerificationResult] = Field(default_factory=list)
    gaps: list[str] = Field(
        default_factory=list, description="빈 곳 코드(열린 문자열, `KnownTraceGaps`)."
    )


class TraceUnknownRef(ContractModel):
    """작업이 참조했지만 요구 문서에 없는 요구 id."""

    task_key: NonEmptyStr
    requirement_id: NonEmptyStr


class TraceOrphans(ContractModel):
    """추적 표 밖의 빈 곳."""

    tasks_without_requirements: list[str] = Field(default_factory=list)
    unknown_requirement_refs: list[TraceUnknownRef] = Field(default_factory=list)
    unknown_task_links: list[TaskLink] = Field(
        default_factory=list, description="지금 문서에 없는 작업 키를 가리키는 연결(이름 바뀜 등)."
    )


class TraceMatrix(ContractModel):
    """`GET /sdd/specs/{id}/trace`."""

    rows: list[TraceRow] = Field(default_factory=list)
    orphans: TraceOrphans = Field(default_factory=TraceOrphans)
    issues: list[SpecIssue] = Field(default_factory=list)


# ---------------------------------------------------------------- 자동 진행·스펙 보기


class AutomationState(ContractModel):
    """자동 진행 상태(실행 연동이 메모리에 가짐, 스펙에 저장하지 않는다)."""

    enabled: bool = Field(description="스펙 규칙의 자동 진행이 켜져 있다.")
    running: bool = Field(description="지금 새 작업을 시작하고 있다(멈춤이면 false).")
    active_runs: list[str] = Field(default_factory=list, description="진행 중인 실행 id.")
    skipped_keys: list[str] = Field(
        default_factory=list, description="실패 상한을 넘어 건너뛴 작업 키."
    )
    failures: dict[str, int] = Field(default_factory=dict, description="작업 키 → 연속 실패 수.")
    stopped_reason: str | None = Field(
        default=None,
        description="멈춘 이유(열린 문자열, `KnownAutomationStopReasons`). 진행 중이면 null.",
    )


class SpecDocumentSummary(ContractModel):
    """스펙 목록의 문서 상태 칩 하나."""

    id: NonEmptyStr
    title: str = ""
    state: str | None = None
    state_label: str | None = Field(default=None, description="풀린 상태 라벨(상태가 있으면).")
    tone: str | None = None


class SpecSummary(ContractModel):
    """`GET /sdd/specs` 목록 항목."""

    id: NonEmptyStr
    name: str = ""
    description: str = ""
    directory: str = Field(
        default="", description="문서 폴더(프로젝트 폴더 기준 상대 경로, 화면은 그대로 보인다)."
    )
    documents: list[SpecDocumentSummary] = Field(default_factory=list)
    task_counts: dict[str, int] = Field(default_factory=dict, description="작업 상태 id → 작업 수.")
    tasks_total: int = Field(default=0, ge=0)
    tasks_done: int = Field(default=0, ge=0)
    ready: int = Field(default=0, ge=0, description="준비된 작업 수.")
    current_stage: StageRef | None = Field(
        default=None, description="끝나지 않은 첫 단계(없으면 null)."
    )
    updated_at: float | None = Field(default=None, description="마지막 저장 시각(Unix epoch 초).")
    issues: int = Field(default=0, ge=0, description="오류 이슈 수(자세한 것은 스펙 보기).")


class SpecView(ContractModel):
    """`GET /sdd/specs/{id}`: 스펙 정의 + 파싱 결과 + 풀린 라벨."""

    spec: SpecDefinition
    index: SpecIndex = Field(default_factory=SpecIndex)
    version_hash: NonEmptyStr = Field(description="정의 버전 해시(`If-Match`용).")
    directory: str = Field(
        default="", description="문서 폴더(프로젝트 폴더 기준 상대 경로, 화면은 그대로 보인다)."
    )
    task_statuses: list[TaskStatusInfo] = Field(
        default_factory=list, description="유효 작업 상태(규칙 → 문법 순, 라벨 채움)."
    )
    document_states: list[DocumentStateInfo] = Field(
        default_factory=list, description="유효 문서 상태(라벨 채움)."
    )
    automation_state: AutomationState | None = Field(
        default=None, description="자동 진행 상태. 실행 연동이 없으면 null."
    )
    issues: list[SpecIssue] = Field(default_factory=list, description="규칙 검사 이슈.")


class RunProfileSummary(ContractModel):
    """문서 틀 목록의 실행 프로필 요약."""

    id: NonEmptyStr
    title: str = ""
    graph: str = ""
    purpose: str | None = None


class SpecTemplateSummary(ContractModel):
    """`GET /sdd/templates` 항목: 이 공간의 문서 틀 하나."""

    id: NonEmptyStr
    name: str = ""
    description: str = ""
    documents: list[SpecDocument] = Field(default_factory=list)
    run_profiles: list[RunProfileSummary] = Field(default_factory=list)
    issues: list[SpecIssue] = Field(default_factory=list)


# ---------------------------------------------------------------- 화면 정보·변수·가져오기


class SddLimits(ContractModel):
    """스펙 기능 한도(설치자 옵션)."""

    max_bulk_start: int = Field(ge=1, description="한꺼번에 시작할 수 있는 작업 수.")
    max_tasks: int = Field(ge=1, description="스펙 하나의 작업 수 상한.")
    max_doc_bytes: int | None = Field(
        default=None, ge=1, description="문서 본문 크기 상한(바이트). null = 정하지 않음."
    )


class SddCapabilities(ContractModel):
    """켜진 연동에 따라 쓸 수 있는 기능(포트 유무로 계산)."""

    runs: bool = Field(default=False, description="작업 실행·실행 칩(실행 연동 있음).")
    templates: bool = Field(default=False, description="문서 틀 저장·편집(정의 모듈 있음).")
    verification: bool = Field(default=False, description="검증 결과 열(검증 출처 하나 이상).")
    automation: bool = Field(default=False, description="자동 진행(연동이 지원).")
    import_export: bool = Field(
        default=False, description="폴더에서 가져오기·폴더로 내보내기(폴더 접근 있음)."
    )


class SddInfo(ContractModel):
    """`GET /sdd/info?project=`: 스펙 화면 정보(웹이 모듈 id를 몰라도 켜짐·한도를 안다)."""

    spec_root: str = Field(
        default="", description="스펙 폴더(프로젝트 폴더 기준 상대 경로, 화면은 그대로 보인다)."
    )
    writable: bool = Field(default=True, description="이 공간에 쓸 수 있다(false면 보기만).")
    limits: SddLimits
    capabilities: SddCapabilities = Field(default_factory=SddCapabilities)
    label_display: list[LabelDisplay] = Field(
        default_factory=list,
        description="실행 라벨 표시 규칙(`ModuleInfo.label_display`와 같은 값의 사본).",
    )


class TemplateVariable(ContractModel):
    """실행 프로필 입력 틀 변수 하나(`{이름}`)."""

    name: NonEmptyStr
    description: str = ""
    example: str | None = None


class ImportFile(ContractModel):
    """가져오기용 폴더 안 마크다운 파일 하나."""

    name: NonEmptyStr = Field(description="파일 이름(폴더 기준).")
    size: int = Field(ge=0, description="바이트.")
    title_guess: str = Field(default="", description="첫 큰 제목, 없으면 파일 이름.")


class ImportDir(ContractModel):
    """가져오기용 폴더 안 하위 폴더 하나(그 아래는 다시 `?path=`로 연다)."""

    name: NonEmptyStr = Field(description="폴더 이름(목록 폴더 기준).")


class ImportFileListing(ContractModel):
    """`GET /sdd/import/files`: 프로젝트 폴더 안 한 폴더의 마크다운 파일과 하위 폴더(재귀하지
    않음)."""

    path: str = Field(default="", description="프로젝트 폴더 기준 상대 경로(빈 값 = 폴더 루트).")
    files: list[ImportFile] = Field(default_factory=list)
    dirs: list[ImportDir] = Field(
        default_factory=list,
        description=(
            "바로 아래 하위 폴더(이름 순). 숨김·링크·예약 폴더(앱 구성 폴더 등)는 뺀다. 0.13.2 전 "
            "서버는 보내지 않는다(빈 목록)."
        ),
    )
    truncated: bool = Field(
        default=False, description="파일이나 하위 폴더가 상한을 넘어 일부만 보였다."
    )


class SddChanged(ContractModel):
    """WS `sdd.changed` payload: 스펙이 바뀜(본문 없음). 화면은 그 스펙을 다시 불러온다."""

    space: SpaceRef = Field(default_factory=SpaceRef, description="그 스펙의 공간.")
    spec_id: NonEmptyStr
    version_hash: str | None = Field(default=None, description="새 정의 버전(삭제면 null).")
    automation: bool = Field(default=False, description="자동 진행 상태만 바뀌었다.")
    deleted: bool = False


__all__ = [
    "AutomationState",
    "DocumentStateInfo",
    "EffectiveSyntax",
    "ImportDir",
    "ImportFile",
    "ImportFileListing",
    "ParsedDocument",
    "ParsedRequirement",
    "ParsedStage",
    "ParsedTask",
    "RunProfileSummary",
    "SddCapabilities",
    "SddChanged",
    "SddInfo",
    "SddLimits",
    "SpecDocumentSummary",
    "SpecIndex",
    "SpecIssue",
    "SpecSummary",
    "SpecTemplateSummary",
    "SpecView",
    "StageRef",
    "TaskLink",
    "TaskPlan",
    "TaskStatusInfo",
    "TemplateVariable",
    "TraceMatrix",
    "TraceOrphans",
    "TraceRow",
    "TraceUnknownRef",
    "TraceVerification",
    "VerificationRef",
    "VerificationResult",
]
