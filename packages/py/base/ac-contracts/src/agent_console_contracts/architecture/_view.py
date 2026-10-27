"""구조도 투영 결과(`ArchitectureView`)와 그 조각, 클릭 필터(`ArchitectureSelector`), 이벤트 멤버십.

투영 결과는 그리기 완결형이다: 좌표·영역·표시 이름·지표·필터 인자를 모두 싣는다. 웹·보관본·다른
소비자는 프로필을 해석하지 않고 이것만으로 그린다(design K-6).

지표 상태는 세 가지다. `observed` = 재료가 있어 센 값(0 포함), `inferred` = 추정값,
`not_collected` = 재료가 없음(값 null). **null을 0으로 채우지 않는다**(R8.8). 칸·연결의 상태
(`observed`·`partial`·`not_collected`)는 지표 상태와 다른 층이다.
"""

from typing import Literal

from pydantic import Field

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr

from ._profile import ArchitectureCanvas, ArchitecturePoint, ArchitectureZone

type ArchitectureMetricStatus = Literal["observed", "inferred", "not_collected"]
"""지표 상태(고정 어휘). observed = 센 값(0 포함), inferred = 추정값, not_collected = 재료 없음
(값 null)."""

type ArchitectureItemStatus = Literal["observed", "partial", "not_collected"]
"""칸·연결·묶음의 수집 상태(고정 어휘). partial = 일부만 기록됨(이유는 `partial_reason`),
not_collected = 이 범위의 어느 출처도 채울 수 없음."""

type ArchitectureEdgeKind = Literal["observed", "structural"]
"""투영 결과의 연결 종류(고정 어휘). observed = 기록된 전달을 셈, structural = 순서로만 아는 연결
(지표 없음). 프로필의 모르는 종류는 투영이 structural로 다루고 프로필 검사가 이슈로 알린다."""


class ArchitectureMetricDetail(ContractModel):
    """소요 지표의 표본 요약. 모든 값은 표본이 있을 때만 채운다."""

    samples: int = Field(ge=0, description="`duration_ms`가 있는 이벤트 수.")
    total_ms: float | None = Field(default=None, ge=0, description="합(ms).")
    avg_ms: float | None = Field(default=None, ge=0, description="평균(ms).")
    max_ms: float | None = Field(default=None, ge=0, description="최대(ms).")


class ArchitectureMetric(ContractModel):
    """지표 하나의 값과 상태. `value`가 null이면 "수집 안 됨"이고 0이 아니다."""

    status: ArchitectureMetricStatus
    value: float | None = Field(
        default=None,
        description=(
            "값(횟수·오류 수·토큰 수·소요 ms). status가 not_collected면 null. "
            "observed의 0은 0이다(센 결과가 0)."
        ),
    )
    detail: ArchitectureMetricDetail | None = Field(
        default=None, description="소요 지표의 표본 요약(그 밖의 지표는 null)."
    )


class ArchitectureSelector(ContractModel):
    """칸·연결·묶음을 눌렀을 때 이벤트 표 질의에 더할 인자 묶음.

    표 질의에는 이 인자와 함께 같은 결과의 `ArchitectureView.max_seq`를 넘긴다. 그러면 표의 전체
    수가 그 대상의 `count` 지표와 같다.
    """

    arch: NonEmptyStr = Field(
        description=(
            "대상: `<프로필 id>:cell:<칸 id>`, `<프로필 id>:edge:<연결 id>`, "
            "`<프로필 id>:unassigned`(분류 안 됨)."
        )
    )
    arch_group: str | None = Field(
        default=None,
        description="칸 안 묶음 값(묶음을 눌렀을 때). 값이 없는 묶음은 빈 문자열.",
    )
    arch_sources: list[str] | None = Field(
        default=None,
        description=("셀 때 쓴 로그 출처 id(출처 우선순위 적용 결과). null = 출처를 거르지 않음."),
    )


class ArchitectureDrillTarget(ContractModel):
    """하위 구조도로 들어갈 때 지금 필터에 더할 값(묶음 값으로 치환된 결과)."""

    filter: NonEmptyStr = Field(description="로그 질의 필터 이름(예: thread, scope).")
    value: str = Field(description="필터 값(예: 서브에이전트 thread id, `run:<id>`).")


class ArchitectureGroupView(ContractModel):
    """칸 안 묶음 하나(예: MCP 서버 하나, 서브에이전트 thread 하나)."""

    key: str | None = Field(description='묶음 값. null = 값이 없는 이벤트 묶음 "(이름 없음)".')
    label: str | None = Field(default=None, description="표시 이름(없으면 화면이 key를 쓴다).")
    status: ArchitectureItemStatus = "observed"
    metrics: dict[str, ArchitectureMetric] = Field(
        default_factory=dict, description="지표 이름 → 값(칸이 고른 지표만)."
    )
    selector: ArchitectureSelector
    drill: ArchitectureDrillTarget | None = Field(
        default=None, description="하위 구조도로 들어갈 필터. null = 들어갈 수 없음."
    )


class ArchitectureGroupRest(ContractModel):
    """묶음 표시 개수를 넘어 하나로 합친 나머지("그 밖 n")."""

    groups: int = Field(ge=1, description="합친 묶음 수.")
    metrics: dict[str, ArchitectureMetric] = Field(default_factory=dict)


class ArchitectureUnavailableView(ContractModel):
    """수집 불가 항목 하나("수집 안 됨: 항목 — 이유")."""

    cell: str | None = Field(default=None, description="이 항목을 둔 칸 id(전체 목록에서).")
    item: NonEmptyStr
    reason: str = ""


class ArchitectureCellView(ContractModel):
    """그릴 칸 하나(좌표·표시 정보·상태·지표·필터)."""

    id: NonEmptyStr
    label: str = Field(description="표시 이름(프로필에 없으면 칸 id).")
    description: str | None = None
    x: float | None = Field(
        default=None, description="칸 중심 가로 좌표. null이면 화면이 선언 순서대로 놓는다."
    )
    y: float | None = Field(default=None, description="칸 중심 세로 좌표.")
    w: float = Field(gt=0, description="폭(프로필에 없으면 기본값).")
    h: float = Field(gt=0, description="높이(프로필에 없으면 기본값).")
    zone: str | None = None
    tone: str | None = Field(default=None, description="색 이름(열린 문자열).")
    view: str | None = Field(default=None, description="그리는 방식 이름(열린 문자열).")
    status: ArchitectureItemStatus
    partial_reason: str | None = Field(default=None, description="status가 partial일 때 이유.")
    metrics: dict[str, ArchitectureMetric] = Field(
        default_factory=dict, description="지표 이름 → 값(프로필이 고른 지표만, 선언 순서)."
    )
    selector: ArchitectureSelector
    groups: list[ArchitectureGroupView] | None = Field(
        default=None,
        description=(
            "묶음(프로필에 묶을 값이 있을 때). 횟수 내림차순, 표시 개수까지. null = 묶지 않음."
        ),
    )
    groups_rest: ArchitectureGroupRest | None = Field(
        default=None, description="표시 개수를 넘은 묶음의 합. null = 넘지 않음."
    )
    drillable: bool = Field(
        default=False, description="하위 구조도로 들어갈 수 있는 칸(묶음마다 `drill`이 있다)."
    )
    unavailable: list[ArchitectureUnavailableView] = Field(
        default_factory=list, description="이 칸의 수집 불가 항목."
    )


class ArchitectureEdgeView(ContractModel):
    """그릴 연결 하나."""

    id: NonEmptyStr
    from_: NonEmptyStr = Field(alias="from", description="출발 칸 id.")
    to: NonEmptyStr = Field(description="도착 칸 id.")
    label: str | None = None
    kind: ArchitectureEdgeKind
    style: str | None = Field(default=None, description="선 모양 이름(열린 문자열).")
    points: list[ArchitecturePoint] | None = Field(
        default=None, description="꺾은선 꼭짓점(시작·끝 포함). null = 두 칸 경계 사이 직선."
    )
    label_at: ArchitecturePoint | None = Field(default=None, description="라벨 칩 중심.")
    label_max_w: float | None = Field(default=None, gt=0, description="라벨 칩 폭 상한 힌트.")
    status: ArchitectureItemStatus
    partial_reason: str | None = None
    metrics: dict[str, ArchitectureMetric] = Field(
        default_factory=dict, description="지표 이름 → 값. structural 연결은 빈 객체."
    )
    selector: ArchitectureSelector | None = Field(
        default=None, description="클릭 필터. structural 연결은 null(걸러낼 이벤트 없음)."
    )


class ArchitectureUnassignedView(ContractModel):
    """어느 칸에도 맞지 않은 이벤트("분류 안 됨")."""

    metrics: dict[str, ArchitectureMetric] = Field(default_factory=dict)
    selector: ArchitectureSelector


class ArchitectureSourceCount(ContractModel):
    """이 범위에 들어온 로그 출처 하나와 이벤트 수."""

    id: NonEmptyStr = Field(description="로그 출처 id.")
    kind: str | None = Field(default=None, description="출처 종류(등록 이름). 모르면 null.")
    events: int = Field(ge=0)


class ArchitectureNote(ContractModel):
    """투영 결과에 붙는 안내 한 줄(예: 고른 프로필이 없어 다른 프로필로 그림)."""

    code: NonEmptyStr = Field(
        description="안내 종류(열린 문자열, 알려진 값은 `KnownArchitectureNoteCodes`)."
    )
    message: str = Field(description="사용자에게 보일 문구(서버가 만든다).")
    details: JsonObject = Field(default_factory=dict)


class ArchitectureView(ContractModel):
    """구조도 투영 결과. 그리기에 필요한 것을 모두 싣는다(웹은 프로필을 몰라도 그린다)."""

    profile: NonEmptyStr = Field(description="그린 프로필 id.")
    title: str = Field(default="", description="그린 프로필 제목(없으면 id).")
    canvas: ArchitectureCanvas | None = Field(
        default=None, description="캔버스 크기. null = 화면이 칸 위치로 정한다."
    )
    zones: list[ArchitectureZone] = Field(default_factory=list)
    cells: list[ArchitectureCellView] = Field(
        default_factory=list, description="칸(프로필 선언 순서 = Tab 순서)."
    )
    edges: list[ArchitectureEdgeView] = Field(
        default_factory=list, description="연결(프로필 선언 순서)."
    )
    unassigned: ArchitectureUnassignedView | None = Field(
        default=None, description="분류 안 됨. null = 프로필이 세지 않음."
    )
    unavailable: list[ArchitectureUnavailableView] = Field(
        default_factory=list, description="모든 칸의 수집 불가 항목(머리 줄 목록)."
    )
    sources: list[ArchitectureSourceCount] = Field(
        default_factory=list, description="이 범위에 들어온 로그 출처와 이벤트 수."
    )
    event_total: int = Field(ge=0, description="이 범위의 이벤트 수(칸 판정 전).")
    max_seq: int | None = Field(
        default=None,
        ge=0,
        description=(
            "센 이벤트의 최대 색인 순번. 클릭 필터 질의에 같이 넘기면 수집이 이어져도 수가 같다. "
            "null = 이벤트 없음 또는 순번을 모름."
        ),
    )
    notes: list[ArchitectureNote] = Field(default_factory=list, description="안내(배너).")


class ArchitectureGroupRef(ContractModel):
    """이벤트가 속한 칸 안 묶음 하나."""

    cell: NonEmptyStr
    key: str | None = Field(description="묶음 값. null = 값 없음.")


class ArchitectureMembership(ContractModel):
    """이벤트 하나가 맞은 칸·연결·묶음(표에서 고른 이벤트 강조용)."""

    profile: NonEmptyStr
    uid: str | None = Field(default=None, description="로그 이벤트 uid(질의 대상).")
    cells: list[str] = Field(default_factory=list, description="맞은 칸 id(선언 순서).")
    edges: list[str] = Field(default_factory=list, description="맞은 연결 id(선언 순서).")
    groups: list[ArchitectureGroupRef] = Field(default_factory=list)
    unassigned: bool = Field(default=False, description="어느 칸에도 맞지 않음.")
