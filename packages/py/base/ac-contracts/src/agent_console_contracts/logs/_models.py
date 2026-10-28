"""정규화 로그 이벤트와 로그 REST DTO(design §4R.3·§4R.6·§4R.9 표 1·§4R.10).

이벤트 모양은 agent_bench `log_events.normalize`를 잇는다. `from`은 Python 예약어라 필드 이름은
`from_`이고 JSON·YAML 키는 `from`(별칭)이다. 범주·단계·근거·태그·차원·지표는 모두 열린 문자열이다
(알려진 범주는 문서 상수 `KnownLogCategories`).
"""

from typing import Any, Final

from pydantic import Field

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr

from ._settings import LogTaxonomy


class LogDocumentRef(ContractModel):
    """이벤트가 가리키는 문서(SKILL.md·SPEC.md 등). 이름만 언급된 것은 읽음으로 보지 않는다."""

    path: str = Field(description="문서 경로(출처가 준 그대로, 원본 기준 상대 경로 권장).")
    kind: str = Field(default="document", description="문서 종류(예: skill, spec, document).")
    action: str = Field(
        default="mentioned", description="이벤트와의 관계(예: mentioned, read, written)."
    )


class LogEvent(ContractModel):
    """정규화 로그 이벤트 하나(색인 사본, 비밀 가림 후).

    목록(`LogEventPage`·`LogTimeline`)에서는 `detail`·`raw`가 null이고 `summary`만 있다.
    본문은 상세(`LogEventDetail.event`)에서만 싣는다.
    원본 경로는 출처 기준 상대 경로(`ref`)만 싣는다.
    """

    uid: NonEmptyStr = Field(description="안정 식별자(identity의 sha256 앞 24자).")
    seq: int = Field(ge=0, description="색인 순번(키셋 페이지 커서의 기준).")
    source: NonEmptyStr = Field(description="로그 출처 id(진단 이벤트는 `diagnostic`).")
    ref: str = Field(default="", description="출처 안 단위(루트 기준 상대 경로, run id 등).")
    observed_at: float = Field(description="색인에 들어온 시각(Unix epoch 초).")
    category: NonEmptyStr = Field(description="범주 id(열린 문자열, 분류 체계로 표시).")
    title: str = ""
    summary: str = Field(default="", description="목록용 짧은 본문(최대 수백 자).")
    stage: str = Field(default="info", description="단계(예: info, start, complete).")
    status: str = Field(
        default="",
        description="출처가 준 상태(열린 문자열, 예: ok, failed). 오류 판정에 쓰지 않는다.",
    )
    thread: str = Field(default="", description="에이전트 줄 id(메인·서브에이전트 세션 등).")
    role: str = ""
    actor: str = ""
    from_: list[str] = Field(default_factory=list, alias="from", description="보낸 쪽.")
    to: list[str] = Field(default_factory=list, description="받는 쪽.")
    via: str = Field(default="", description="전달 수단(예: 위임 도구 이름).")
    tool: str = ""
    call_id: str = Field(default="", description="도구 호출 id(start·complete 짝의 키).")
    turn_id: str = ""
    message_id: str = Field(default="", description="모델 응답 id(여러 행으로 나뉜 응답을 묶음).")
    session: str = ""
    cwd: str = ""
    repo_root: str = Field(default="", description="worktree면 본 저장소 경로(수집 때 계산).")
    model: str = ""
    run_id: str = Field(default="", description="플랫폼 실행 id(플랫폼 실행 출처·상관).")
    node_path: list[str] = Field(default_factory=list)
    time: float | None = Field(default=None, description="원본 시각(Unix epoch 초). 모르면 null.")
    duration_ms: float | None = Field(
        default=None,
        description="명시 id 짝(같은 thread+call_id의 start/complete)으로 계산한 소요 시간.",
    )
    evidence: str = Field(default="observed", description="근거(observed·inferred 등).")
    tags: list[str] = Field(default_factory=list, description="범주 + 분류기 태그.")
    documents: list[LogDocumentRef] = Field(default_factory=list)
    correlation: dict[str, str | list[str]] = Field(
        default_factory=dict, description="상관 근거 이름 → 값(명시 id만, 시간상 이웃은 잇지 않음)."
    )
    detail: Any = Field(default=None, description="표시용 본문(상세에서만, 크기 제한 적용).")
    raw: Any = Field(default=None, description="원문(상세에서만, 크기 제한·비밀 가림 적용).")


class LogEvidenceLink(ContractModel):
    """같은 명시 id를 공유하는 다른 이벤트(agent_bench `link_events`)."""

    uid: NonEmptyStr
    title: str = ""
    basis: NonEmptyStr = Field(description="상관 근거 이름(예: call_id, session).")
    value: str


class LogEventPage(ContractModel):
    """`GET /logs/events` 응답(키셋 페이지)."""

    items: list[LogEvent] = Field(default_factory=list)
    total: int | None = Field(default=None, ge=0, description="전체 개수(계산하지 않으면 null).")
    next_cursor: str | None = Field(default=None, description="다음 페이지 커서. null = 끝.")


class TokenSample(ContractModel):
    """응답(thread, message_id) 하나의 토큰 표본(F-8: 같은 응답이 여러 행이어도 한 번만 센다)."""

    thread: str = ""
    message_id: str = ""
    model: str = ""
    time: float | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cache_read_input_tokens: int | None = Field(default=None, ge=0)
    cache_creation_input_tokens: int | None = Field(default=None, ge=0)


class LogEventDetail(ContractModel):
    """`GET /logs/events/{uid}` 응답: 본문 포함 이벤트 + 관련 이벤트 + 근거 연결."""

    event: LogEvent
    related: list[LogEvent] = Field(
        default_factory=list, description="같은 호출·응답의 다른 이벤트(본문 없음)."
    )
    evidence_links: list[LogEvidenceLink] = Field(default_factory=list)
    truncated: bool = Field(
        default=False, description="근거 후보가 한도(1000)를 넘어 잘림(본문 잘림과 별개)."
    )
    detail_truncated: bool = Field(
        default=False, description="detail·raw가 본문 크기 한도(max_detail_bytes)로 잘림."
    )
    usage: TokenSample | None = Field(default=None, description="이 이벤트의 토큰 표본(있으면).")


# ---------------------------------------------------------------- 출처·분류기


class LogSourceDescriptor(ContractModel):
    """로그 출처 디스크립터."""

    id: NonEmptyStr
    title: NonEmptyStr
    format: NonEmptyStr = Field(description="기본 분류기 id.")
    description: str | None = None
    config_schema: JsonObject = Field(default_factory=dict)
    default_enabled: bool = Field(
        default=False, description="설정에 없을 때 켤지(개인 대화 원문을 복사하는 출처는 끔)."
    )
    reads_paths: bool = Field(
        default=True, description="원본 파일을 읽는다(화면이 '원본은 읽기만 함'을 보인다)."
    )
    setup_help: str | None = Field(default=None, description="설정 방법 안내(마크다운).")
    docs_url: str | None = Field(default=None, description="자세한 문서 링크(http(s) URL).")


class LogClassifierDescriptor(ContractModel):
    """로그 분류기 디스크립터(X6). 분류기는 행 단위 무상태다(F-7)."""

    id: NonEmptyStr
    formats: list[str] = Field(default_factory=list, description="다룰 수 있는 출처 형식.")
    title: NonEmptyStr
    description: str | None = None
    config_schema: JsonObject = Field(default_factory=dict)


class LogSourceStatus(ContractModel):
    """출처 하나의 수집 상태."""

    last_scan_at: float | None = None
    refs: int = Field(default=0, ge=0, description="알고 있는 단위(파일·Run) 수.")
    pending_bytes: int | None = Field(
        default=None, ge=0, description="예산 때문에 다음 수집으로 미룬 바이트(모르면 null)."
    )
    error_code: str | None = Field(default=None, description="마지막 수집 실패 코드.")


class LogSourceInfo(ContractModel):
    """`GET /logs/sources` 항목."""

    descriptor: LogSourceDescriptor
    enabled: bool
    origin: NonEmptyStr = Field(
        default="plugin",
        description="plugin = entry point 출처, runtime = 다른 모듈이 준 출처(열린 문자열).",
    )
    status: LogSourceStatus = Field(default_factory=LogSourceStatus)


class LogSourceScanResult(ContractModel):
    """수집 한 번에서 출처 하나의 결과."""

    source_id: NonEmptyStr
    new_events: int = Field(default=0, ge=0, description="새로 색인한 이벤트 수.")
    error_code: str | None = Field(default=None, description="이 출처의 실패 코드(없으면 성공).")
    message: str | None = Field(default=None, description="실패 설명(비밀을 가린 문장).")
    refs: int = Field(default=0, ge=0, description="읽은 단위 수.")
    read_bytes: int = Field(default=0, ge=0)
    records: int = Field(default=0, ge=0, description="읽은 원본 행 수.")
    diagnostics: int = Field(default=0, ge=0, description="해석·분류 실패로 진단 이벤트가 된 행.")
    pending_bytes: int | None = Field(default=None, ge=0)


class LogScanReport(ContractModel):
    """`POST /logs/scan` 응답(수집 한 번의 결과)."""

    started_at: float
    finished_at: float
    sources: list[LogSourceScanResult] = Field(default_factory=list)
    new_events: int = Field(default=0, ge=0, description="새로 색인한 이벤트 합.")
    max_seq: int | None = Field(default=None, ge=0, description="지금 색인의 최대 seq.")


# ---------------------------------------------------------------- 세션·타임라인


class LogLane(ContractModel):
    """에이전트 줄(thread)의 표시 정보. 서브에이전트면 부모가 있다. label이 없으면 id를 보인다."""

    id: NonEmptyStr
    label: str | None = None
    parent_id: str | None = None


class LogTokenTotals(ContractModel):
    """토큰 합 분해. 값이 없으면 null(0으로 채우지 않음)."""

    input: int | None = Field(default=None, ge=0)
    output: int | None = Field(default=None, ge=0)
    cache_read: int | None = Field(default=None, ge=0)
    cache_creation: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)


class LogProjectRef(ContractModel):
    """프로젝트 묶음(묶기 규칙을 적용한 결과). 0.11.0 deprecated(K33-15), `project_id`를 쓴다."""

    id: NonEmptyStr
    label: str = ""


class LogSessionSummary(ContractModel):
    """`GET /logs/sessions` 항목: 세션 하나의 요약."""

    session: NonEmptyStr
    sources: list[str] = Field(default_factory=list)
    title: str = Field(default="", description="첫 입력 등에서 뽑은 짧은 제목.")
    cwd: str = ""
    repo_root: str = ""
    project: LogProjectRef | None = Field(
        default=None,
        description="이전 형식의 프로젝트 묶음(0.11.0 deprecated, K33-15). `project_id`를 쓴다.",
        json_schema_extra={"deprecated": True},
    )
    project_id: str | None = Field(
        default=None,
        description=(
            "세션 작업 폴더가 들어 있는 등록 프로젝트의 id(불투명 문자열, 0.11.0). "
            "어느 등록 폴더에도 들지 않으면 null."
        ),
    )
    first_time: float | None = None
    last_time: float | None = None
    events: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    thread_count: int = Field(default=0, ge=0, description="에이전트 줄(thread) 수.")
    models: list[str] = Field(default_factory=list)
    tokens: LogTokenTotals | None = Field(
        default=None, description="응답(message_id)별 한 번만 센 토큰 합."
    )


class LogTimeline(ContractModel):
    """`GET /logs/sessions/{session}/timeline`: 세션의 보이는 이벤트(time → seq 순), 줄 = thread."""

    session: LogSessionSummary
    lanes: list[LogLane] = Field(
        default_factory=list, description="줄(thread). parent_id로 서브에이전트 관계를 그린다."
    )
    events: list[LogEvent] = Field(default_factory=list)
    total: int | None = Field(
        default=None, ge=0, description="세션의 보이는 이벤트 전체 수(잘렸을 때 비교용)."
    )
    truncated: bool = Field(default=False, description="서버 상한으로 앞부분만 실었다.")


# ---------------------------------------------------------------- 집계·보관본


class LogAggregateRequest(ContractModel):
    """`POST /logs/aggregate` 본문. 차원·지표·필터 이름은 열린 문자열."""

    group_by: list[str] = Field(default_factory=list)
    metric: NonEmptyStr
    filter: JsonObject = Field(default_factory=dict)
    tz: str | None = Field(default=None, description="day·hour 차원의 시간대(IANA). 없으면 서버.")


class LogAggregateRow(ContractModel):
    """집계 결과 한 줄. 값이 없는 지표는 null이다(0으로 채우지 않음)."""

    keys: dict[str, str | None] = Field(default_factory=dict, description="차원 이름 → 값.")
    value: float | None = None


class LogDimensionInfo(ContractModel):
    """집계 차원 하나(`GET /logs/schema`). 화면은 이름을 몰라도 이 목록으로 고른다."""

    id: NonEmptyStr
    title: str | None = None
    description: str | None = None
    kind: str | None = Field(
        default=None, description="차원 성격(예: time = 시간 차원). 모르는 값은 무시한다."
    )


class LogMetricInfo(ContractModel):
    """집계 지표 하나(`GET /logs/schema`)."""

    id: NonEmptyStr
    title: str | None = None
    description: str | None = None
    unit: str | None = Field(default=None, description="값 단위(예: count, tokens, ms).")


class LogFilterFieldInfo(ContractModel):
    """필터 이름 하나(`GET /logs/schema`). 모르는 필터 이름은 서버가 422로 답한다."""

    id: NonEmptyStr
    title: str | None = None
    description: str | None = None
    multi: bool | None = Field(default=None, description="여러 값을 받는다(쉼표 목록).")


class LogQuerySchema(ContractModel):
    """`GET /logs/schema`: 위젯 질의·필터 막대가 고를 차원·지표·필터 목록(서버 데이터)."""

    dimensions: list[LogDimensionInfo] = Field(default_factory=list)
    metrics: list[LogMetricInfo] = Field(default_factory=list)
    filters: list[LogFilterFieldInfo] = Field(default_factory=list)


class LogArchive(ContractModel):
    """오프라인 보관본(`GET /logs/archive?format=json`, 형식 버전 1)."""

    version: int = Field(default=1, description="보관본 형식 버전.")
    exported_at: float
    filter: JsonObject = Field(default_factory=dict)
    taxonomy: LogTaxonomy = Field(default_factory=LogTaxonomy)
    lanes: list[LogLane] = Field(default_factory=list)
    sessions: list[LogSessionSummary] = Field(default_factory=list)
    events: list[LogEvent] = Field(default_factory=list)
    evidence_links: dict[str, list[LogEvidenceLink]] = Field(
        default_factory=dict, description="이벤트 uid → 근거 연결."
    )
    truncated: bool = False


class KnownLogCategories:
    """기본 분류기가 쓰는 범주 id(design §4R.2). **문서 상수**다.

    목록·enum이 아니다. 분류기는 다른 범주를 만들 수 있고, 화면은 분류 체계에 없는 범주를
    이름 = id로 보인다. 스키마·TS 상수로 내보내지 않는다(표시 정보는 분류 체계 데이터).
    오류 판정에 쓰지 않는다. 오류 표시는 분류 체계 항목의 tone == "danger"만 근거로 한다(F-25).
    """

    INPUT: Final = "input"
    CONTEXT: Final = "context"
    LLM: Final = "llm"
    TOOL: Final = "tool"
    TOOL_CALL: Final = "tool_call"
    TOOL_RESULT: Final = "tool_result"
    MCP: Final = "mcp"
    HOOK: Final = "hook"
    EXTERNAL: Final = "external"
    AGENT: Final = "agent"
    HANDOFF: Final = "handoff"
    MERGE: Final = "merge"
    SKILL: Final = "skill"
    SPEC: Final = "spec"
    AGENTS_MD: Final = "agents_md"
    DOCUMENT: Final = "document"
    WORKSPACE: Final = "workspace"
    USAGE: Final = "usage"
    CONTROL: Final = "control"
    SYSTEM: Final = "system"
    ERROR: Final = "error"
    OTHER: Final = "other"


class KnownLogTones:
    """분류 체계 항목 `tone`의 알려진 값(design §4R.9). **문서 상수**다(열린 문자열).

    화면은 `danger`인 범주의 이벤트만 오류로 표시한다(F-25). 모르는 값은 무시한다.
    """

    DANGER: Final = "danger"
    WARNING: Final = "warning"
    SUCCESS: Final = "success"
    INFO: Final = "info"
    NEUTRAL: Final = "neutral"


class KnownLogDimensions:
    """기본 집계 차원 이름. **문서 상수**다(목록은 `GET /logs/schema`가 준다)."""

    PROJECT: Final = "project"
    CWD: Final = "cwd"
    SESSION: Final = "session"
    AGENT: Final = "agent"
    MODEL: Final = "model"
    DAY: Final = "day"
    HOUR: Final = "hour"
    SOURCE: Final = "source"
    CATEGORY: Final = "category"
    TOOL: Final = "tool"
    TAG: Final = "tag"


class KnownLogMetrics:
    """기본 집계 지표 이름. **문서 상수**다(목록은 `GET /logs/schema`가 준다)."""

    EVENTS: Final = "events"
    TOOL_CALLS: Final = "tool_calls"
    ERRORS: Final = "errors"
    TOKENS_INPUT: Final = "tokens.input"
    TOKENS_OUTPUT: Final = "tokens.output"
    TOKENS_CACHE_READ: Final = "tokens.cache_read"
    TOKENS_CACHE_CREATION: Final = "tokens.cache_creation"
    TOKENS_TOTAL: Final = "tokens.total"
    DURATION_SUM: Final = "duration_ms.sum"
    DURATION_AVG: Final = "duration_ms.avg"
    DURATION_P95: Final = "duration_ms.p95"


__all__ = [
    "KnownLogCategories",
    "KnownLogDimensions",
    "KnownLogMetrics",
    "KnownLogTones",
    "LogAggregateRequest",
    "LogAggregateRow",
    "LogArchive",
    "LogClassifierDescriptor",
    "LogDimensionInfo",
    "LogDocumentRef",
    "LogEvent",
    "LogEventDetail",
    "LogEventPage",
    "LogEvidenceLink",
    "LogFilterFieldInfo",
    "LogLane",
    "LogMetricInfo",
    "LogProjectRef",
    "LogQuerySchema",
    "LogScanReport",
    "LogSessionSummary",
    "LogSourceDescriptor",
    "LogSourceInfo",
    "LogSourceScanResult",
    "LogSourceStatus",
    "LogTimeline",
    "LogTokenTotals",
    "TokenSample",
]
