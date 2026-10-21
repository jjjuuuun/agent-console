"""실행 백엔드 준비 상태(정적 점검)와 연결 테스트(probe) 응답(ux-overhaul §15.8, 0.8.0).

- ``BackendReadiness``: ``GET /backends/{id}/status``·``GET /backends/status``. 모델을 부르지 않는
  점검 결과다. ``state``는 백엔드가 정하는 열린 어휘이고 화면은 ``tone``으로만 색·아이콘을 고른다.
- ``BackendProbeResult``: ``POST /backends/{id}/probe``. 사용자가 누를 때만 실제 호출 한 번.

비밀 값 규칙: 이 모델들에는 값을 담을 필드가 없다. 점검 항목은 "있음/없음"과 출처 이름(환경변수
이름, ``secret://`` 참조 이름)만 담는다. 글자 필드(``summary``·``detail``·``message``·``note``·
``details``)는 서버가 비밀 가림을 거친 뒤 낸다.
"""

from typing import Literal

from pydantic import Field

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr
from agent_console_contracts.common import FixAction

type ReadinessTone = Literal["ok", "warn", "error", "unknown"]
"""준비 상태 톤(화면 색·아이콘 표의 키). ``ok`` 쓸 수 있음, ``warn`` 쓸 수 있으나 주의,
``error`` 막힘, ``unknown`` 확인할 수 없음(점검을 지원하지 않거나 점검이 실패)."""


class ReadinessCheck(ContractModel):
    """정적 점검 항목 하나(예: "API 키 환경변수: 있음"). 값은 담지 않는다."""

    id: NonEmptyStr = Field(description="항목 id(백엔드가 정함, 열린 문자열).")
    title: NonEmptyStr = Field(description="항목 이름(사용자 언어).")
    ok: bool = Field(description="이 항목이 충족됐는지.")
    note: str | None = Field(
        default=None, description="보충 한 줄(출처 이름 등, 비밀 값 없음). null = 없음."
    )


class BackendReadiness(ContractModel):
    """실행 백엔드의 정적 점검 상태(모델·네트워크 호출 없음)."""

    backend_id: NonEmptyStr
    state: NonEmptyStr = Field(
        description=(
            "상태 이름(백엔드가 정하는 열린 어휘, 예: auth_ready, auth_missing). 화면은 비교하지 "
            "않고 tone·summary로 그린다. 점검을 지원하지 않으면 unknown."
        )
    )
    tone: ReadinessTone = Field(description="화면 톤. 모르는 값은 화면이 unknown으로 그린다.")
    summary: str = Field(default="", description="상태 줄 문구(사용자 언어).")
    short_summary: str = Field(
        default="", description="칩에 쓸 짧은 문구(8자 이하 권장). 비면 화면이 summary를 줄인다."
    )
    detail: str = Field(default="", description="보충 설명(예: 구독 방식 책임 문구).")
    fixes: list[FixAction] = Field(
        default_factory=list, description="해결 버튼(문구 + 이동할 곳). 비면 버튼 없음."
    )
    checked_at: float = Field(description="점검 시각(epoch 초).")
    checks: list[ReadinessCheck] = Field(
        default_factory=list, description="항목별 점검 결과(접힌 상세에 보임). 값 없음."
    )


class BackendProbeRequest(ContractModel):
    """``POST /backends/{id}/probe`` 요청(본문 생략 가능)."""

    timeout_s: float | None = Field(
        default=None,
        gt=0,
        description="기다릴 최대 초. null = 서버 기본. 서버 상한을 넘으면 상한으로 잘린다.",
    )


class BackendProbeResult(ContractModel):
    """연결 테스트 결과. 실행 기록·이벤트에 남지 않는다."""

    backend_id: NonEmptyStr
    ok: bool
    latency_ms: int | None = Field(
        default=None, ge=0, description="호출에 걸린 시간(밀리초). null = 재지 않음."
    )
    reason: str | None = Field(
        default=None,
        description=(
            "실패 사유 코드(열린 어휘, 예: auth_missing, auth_failed, timeout, network). "
            "성공이면 null."
        ),
    )
    message: str = Field(default="", description="결과 문장(사용자 언어, 비밀 가림을 거침).")
    details: JsonObject = Field(
        default_factory=dict,
        description="확인 정보(예: 모델 id). 키·토큰 같은 비밀 값은 넣지 않는다.",
    )
    fixes: list[FixAction] = Field(default_factory=list, description="해결 버튼. 비면 없음.")
    finished_at: float = Field(description="끝난 시각(epoch 초).")


__all__ = [
    "BackendProbeRequest",
    "BackendProbeResult",
    "BackendReadiness",
    "ReadinessCheck",
    "ReadinessTone",
]
