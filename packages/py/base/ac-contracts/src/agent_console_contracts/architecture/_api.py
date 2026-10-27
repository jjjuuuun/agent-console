"""구조도 REST DTO와 문서 상수.

경로(구조도 모듈 `mod-architecture`): `GET /architecture/profiles` → `ArchitectureProfileList`,
`GET /architecture/profiles/{id}` → `ArchitectureProfileDetail`, `POST /architecture/profiles/check`
(`ArchitectureProfileCheckRequest` → `ArchitectureProfileCheckResult`), `POST /architecture/project`
(`ArchitectureProjectRequest` → `ArchitectureView`). 로그 연동(`link-logs-architecture`)은
`GET /logs/architecture` → `ArchitectureView`, `GET /logs/events/{uid}/architecture` →
`ArchitectureMembership`을 낸다.
"""

from typing import Final

from pydantic import Field

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr
from agent_console_contracts.definitions import Issue
from agent_console_contracts.logs import LogEvent, TokenSample

from ._profile import ArchitectureProfile


class ArchitectureProfileInfo(ContractModel):
    """프로필 목록 항목(병합 결과 하나)."""

    id: NonEmptyStr
    title: str = Field(default="", description="제목(없으면 id).")
    origin: NonEmptyStr = Field(
        description=(
            "출처(열린 문자열): `default`(패키지 기본), `plugin:<배포 이름>`, `user`(사용자 설정)."
        )
    )
    overrides: str | None = Field(
        default=None,
        description="같은 id의 기본·플러그인 프로필을 덮어썼으면 그 출처(origin 값). 아니면 null.",
    )
    disabled: bool = Field(
        default=False,
        description="사용자 설정에서 null로 끈 프로필(목록에 함께 실을 때만 true).",
    )
    issues: int = Field(default=0, ge=0, description="프로필 검사 문제 수.")
    cells: int = Field(default=0, ge=0, description="칸 수.")
    edges: int = Field(default=0, ge=0, description="연결 수.")


class ArchitectureProfileList(ContractModel):
    """`GET /architecture/profiles` 응답."""

    profiles: list[ArchitectureProfileInfo] = Field(
        default_factory=list, description="병합 순서(기본 → 플러그인 → 사용자)."
    )
    default_profile: str | None = Field(
        default=None,
        description=(
            "실제로 먼저 열 프로필 id(설정 값이 없거나 지워졌으면 첫 프로필). 프로필이 없으면 null."
        ),
    )
    include_defaults: bool = Field(default=True, description="설정의 기본 프로필 사용 값.")


class ArchitectureProfileDetail(ArchitectureProfileInfo):
    """`GET /architecture/profiles/{id}` 응답: 목록 항목 + 프로필 본문 + 검사 결과."""

    profile: ArchitectureProfile
    problems: list[Issue] = Field(
        default_factory=list, description="프로필 검사 결과(`issues`는 이 목록의 길이)."
    )


class ArchitectureProfileCheckRequest(ContractModel):
    """`POST /architecture/profiles/check` 본문. 형식이 틀린 프로필도 받아 문제로 알린다."""

    id: str | None = Field(default=None, description="검사할 프로필 id(id 글자 규칙도 본다).")
    profile: JsonObject = Field(
        description="프로필 본문(편집 중인 YAML을 읽은 객체). 형식 오류도 문제로 알린다."
    )


class ArchitectureProfileCheckResult(ContractModel):
    """프로필 검사 결과. 문제가 있어도 저장은 막지 않는다."""

    issues: list[Issue] = Field(default_factory=list)


class ArchitectureProjectRequest(ContractModel):
    """`POST /architecture/project` 본문(로그 모듈 없이 이벤트를 직접 넘겨 투영).

    `profile`(id)와 `inline`(본문) 중 하나를 준다. 둘 다 없으면 기본으로 열 프로필이다.
    이벤트 수는 서버 설치자 상한을 넘을 수 없다.
    """

    profile: str | None = Field(default=None, description="프로필 id.")
    inline: ArchitectureProfile | None = Field(
        default=None, description="저장하지 않은 프로필 본문(설정 미리보기)."
    )
    inline_id: str | None = Field(
        default=None, description="인라인 프로필에 붙일 id(선택 필터 문자열에 쓰인다)."
    )
    events: list[LogEvent] = Field(default_factory=list)
    tokens: list[TokenSample] = Field(default_factory=list)
    source_kinds: dict[str, str] = Field(
        default_factory=dict,
        description="로그 출처 id → 출처 종류(수집 범위·우선순위 판정). 없는 출처는 종류를 모름.",
    )
    error_categories: list[str] = Field(
        default_factory=list, description="오류로 볼 범주 id(분류 체계에서 오류로 표시한 범주)."
    )


class ArchitectureScopeTooLargeDetails(ContractModel):
    """오류 `architecture.scope_too_large`의 `details`."""

    events: int = Field(ge=0, description="범위의 이벤트 수.")
    limit: int = Field(ge=0, description="설치자 상한.")


class KnownArchitectureMetrics:
    """지표 이름(칸·연결의 보일 지표, 투영 결과 `metrics`의 키). **문서 상수**다.

    계산 규칙은 투영 라이브러리의 코드이고 확장 지점이 없다(design K-7). 프로필은 열린
    문자열이므로 모르는 이름은 프로필 검사가 이슈로 알린다. 스키마·TS 상수로 내보내지 않는다.
    """

    COUNT: Final = "count"
    """맞은 이벤트 수."""
    ERRORS: Final = "errors"
    """오류 조건에 맞거나 오류 범주인 이벤트 수."""
    DURATION: Final = "duration"
    """`duration_ms`가 있는 이벤트의 소요(값 = 평균 ms, "
    "`detail`에 표본 요약). 없으면 not_collected."""
    TOKENS: Final = "tokens"
    """맞은 이벤트의 (thread, message_id) 토큰 표본 합(응답당 한 번). 없으면 not_collected."""
    INFERRED_DURATION: Final = "inferred_duration"
    """같은 thread의 앞 이벤트 → 응답 첫 행 간격(늘 inferred). 프로필 추가 선택이 켤 때만."""


class KnownArchitectureEdgeKinds:
    """연결 종류. **문서 상수**다(프로필에서는 열린 문자열, 투영 결과에서는 고정 어휘)."""

    OBSERVED: Final = "observed"
    STRUCTURAL: Final = "structural"


class KnownArchitectureOrigins:
    """프로필 출처(`ArchitectureProfileInfo.origin`). **문서 상수**다."""

    DEFAULT: Final = "default"
    USER: Final = "user"
    PLUGIN_PREFIX: Final = "plugin:"
    """`plugin:<배포 이름>`의 접두."""


class KnownArchitectureTargets:
    """선택 필터 `arch` 문자열(`<프로필 id>:<대상 종류>[:<id>]`)의 대상 종류. **문서 상수**다."""

    CELL: Final = "cell"
    EDGE: Final = "edge"
    UNASSIGNED: Final = "unassigned"


class KnownArchitectureNoteCodes:
    """투영 결과 안내(`ArchitectureNote.code`)의 알려진 값. **문서 상수**다."""

    PROFILE_FALLBACK: Final = "architecture.profile_fallback"
    """요청한 프로필이 없어 다른 프로필로 그렸다. `details.requested`·`details.used`."""
    EVENTS_TRUNCATED: Final = "architecture.events_truncated"
    """범위 이벤트를 일부만 셌다. `details.counted`·`details.total`."""
    PROFILE_ISSUES: Final = "architecture.profile_issues"
    """프로필에 검사 문제가 있어 일부 칸·연결이 빠졌을 수 있다. `details.issues`(수)."""


class KnownArchitectureIssueCodes:
    """프로필 검사 이슈 코드(`Issue.code`) 일부. **문서 상수**다. 조건 연산자 문제는 기존
    `condition.unknown_operator`·`condition.invalid_value`를 쓴다. 이슈 `path`는 프로필 기준
    JSON Pointer(예: `/cells/llm/when`, `/edges/3/to`)."""

    INVALID: Final = "architecture.invalid"
    """프로필 형식이 맞지 않다(검증 오류). `details.errors`."""
    BAD_ID: Final = "architecture.bad_id"
    """칸·연결·영역·프로필 id가 글자 규칙에 맞지 않다."""
    DUPLICATE_ID: Final = "architecture.duplicate_id"
    """연결·영역 id가 겹친다."""
    UNKNOWN_CELL: Final = "architecture.unknown_cell"
    """연결·수집 범위·우선순위가 없는 칸을 가리킨다."""
    UNKNOWN_ZONE: Final = "architecture.unknown_zone"
    """칸이 없는 영역을 가리킨다."""
    UNKNOWN_METRIC: Final = "architecture.unknown_metric"
    """보일 지표 이름을 모른다."""
    UNKNOWN_EDGE_KIND: Final = "architecture.unknown_edge_kind"
    """연결 종류가 observed·structural이 아니다."""
    UNKNOWN_DRILL_FILTER: Final = "architecture.unknown_drill_filter"
    """하위 구조도의 걸러낼 항목 이름을 모른다(받은 필터 이름 목록과 대조)."""
