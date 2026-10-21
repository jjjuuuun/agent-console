"""사용량: 창 스냅샷과 토큰 집계.

창(`window`)은 출처가 주는 문자열 id다. 창 목록·표시 이름은 계약·코드에 없다
(표시 이름은 설정 `usage.window_labels`). 값이 없으면 null이며 화면은 숫자를 지어내지 않는다.
"""

from typing import Any

from pydantic import Field

from ._base import ContractModel, JsonObject, NonEmptyStr
from .common import ErrorInfo, Usage

type UsageTrust = NonEmptyStr
"""사용량 출처 신뢰 등급. 화면 배지에 쓴다.

열린 문자열이다. 서드파티 출처가 새 등급을 선언할 수 있다. 알려진 값은 문서 상수
`KnownUsageTrust`(official·observed·estimated·unofficial)이며,
화면은 모르는 값을 기본 배지로 보인다.
"""


class UsageSetupSnippet(ContractModel):
    """출처 연결 안내 조각 하나(복사해 붙이는 설정·명령, 0.8.0).

    `text`의 자리표시자(예: `{output_path}`·`{agent_console_cmd}`)는 서버가 절대 경로로 채워 준다.
    """

    id: NonEmptyStr
    title: NonEmptyStr = Field(description="조각 제목(예: 상태 줄 설정).")
    shell: str = Field(
        default="", description="어느 셸·환경용인지(예: bash, powershell). 빈 값 = 공통."
    )
    language: str = Field(
        default="", description="코드 강조 언어(예: json, bash). 빈 값 = 일반 글."
    )
    text: str = Field(description="복사할 본문.")


class UsageWindowInfo(ContractModel):
    """출처가 내는 사용량 창 하나의 표시 정보(0.8.0).

    사용자 설정 `usage.window_labels`가 우선한다.
    """

    id: NonEmptyStr = Field(description="창 id(`UsageWindowSnapshot.window`).")
    title: NonEmptyStr = Field(description="창 이름(예: 5시간 창).")
    short_title: str | None = Field(default=None, description="좁은 자리용 짧은 이름(예: 5h).")


class UsageSourceDescriptor(ContractModel):
    """사용량 출처 디스크립터."""

    id: NonEmptyStr
    title: NonEmptyStr
    description: str = ""
    config_schema: JsonObject = Field(default_factory=dict)
    trust: UsageTrust = Field(description="신뢰 등급(화면 배지).")
    setup_help: str | None = Field(
        default=None, description="출처 설정 방법 안내(마크다운). 화면에 그대로 보인다."
    )
    docs_url: str | None = Field(default=None, description="자세한 문서 링크(http(s) URL).")
    # 0.8.0(design §5.2R.3 #7). 사용자 설정 `usage.sources`가 비었을 때만 auto_enable을 본다.
    auto_enable: bool = Field(
        default=False, description="설정에 출처 목록이 없으면 켠 것으로 본다."
    )
    needs_setup: bool = Field(
        default=False, description="값을 받으려면 사용자가 연결 설정을 해야 한다(setup_snippets)."
    )
    test_only: bool = Field(default=False, description="시험용 출처. 자동으로 켜지 않는다.")
    setup_snippets: list[UsageSetupSnippet] = Field(
        default_factory=list, description="연결 안내 조각(복사용)."
    )
    windows: list[UsageWindowInfo] = Field(
        default_factory=list, description="이 출처가 내는 창과 표시 이름. 비우면 모름."
    )


class UsageWindowSnapshot(ContractModel):
    """사용량 창 하나의 관측값."""

    source: NonEmptyStr = Field(description="사용량 출처 id.")
    window: NonEmptyStr = Field(description="창 id(출처가 정함, 고정 목록 아님).")
    used_ratio: float | None = Field(default=None, ge=0, description="사용률(0~1, 넘을 수 있음).")
    used_tokens: int | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, description="출처가 주는 상태 문자열.")
    resets_at: float | None = Field(default=None, description="초기화 시각(Unix epoch 초).")
    observed_at: float = Field(description="관측 시각(Unix epoch 초).")
    raw: Any = Field(default=None, description="출처 원문(비밀 제거 후).")


class TokenRollupRow(ContractModel):
    """플랫폼 실행분 토큰 집계 한 줄. 비어 있는 차원은 그 차원으로 나누지 않은 것이다."""

    agent_id: str | None = None
    graph_id: str | None = None
    model: str | None = None
    day: str | None = Field(default=None, description="YYYY-MM-DD(서버 시간대).")
    usage: Usage
    runs: int | None = Field(default=None, ge=0)
    precision: str | None = Field(
        default=None,
        description="값의 정밀도 메모(예: 총 토큰만 있음). 화면이 그대로 표시한다.",
    )


class UsageSourceInfo(ContractModel):
    """`GET /usage/sources` 항목: 출처 디스크립터와 현재 상태."""

    descriptor: UsageSourceDescriptor
    enabled: bool = True
    config: JsonObject = Field(default_factory=dict)
    last_observed_at: float | None = None
    last_received_at: float | None = Field(
        default=None,
        description=(
            "출처에서 마지막으로 값을 받은 시각(Unix epoch 초, 0.8.0). null = 받은 적 없음."
        ),
    )
    error: ErrorInfo | None = None


class UsageReport(ContractModel):
    """`GET /usage` 응답: 창 스냅샷 + 토큰 집계.

    부분 조회: `GET /usage?parts=windows,tokens`(쉼표 목록).
    알려진 부분 이름은 `USAGE_REPORT_PARTS`(`windows` → `windows`, `tokens` → `rollups`)이고,
    `parts`를 생략하면 전부다. 요청하지 않은 부분은 **null**(= 요청 안 함)이다.
    빈 목록은 "요청했지만 값 없음"이며 둘을 구분한다. 모르는 부분 이름은 무시한다(전방 호환).
    """

    windows: list[UsageWindowSnapshot] | None = Field(
        default_factory=list,
        description="창 스냅샷(부분 windows). null = 요청하지 않음.",
    )
    rollups: list[TokenRollupRow] | None = Field(
        default_factory=list,
        description="플랫폼 실행분 토큰 집계(부분 tokens). null = 요청하지 않음.",
    )
    generated_at: float


__all__ = [
    "TokenRollupRow",
    "UsageReport",
    "UsageSetupSnippet",
    "UsageSourceDescriptor",
    "UsageSourceInfo",
    "UsageTrust",
    "UsageWindowInfo",
    "UsageWindowSnapshot",
]
