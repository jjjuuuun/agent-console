"""실행 백엔드 계정 로그인·로그아웃(앱 화면에서 시작·완료, 0.8.0 F14, ux-overhaul §15.9).

- ``POST /backends/{id}/login`` (``BackendLoginStartRequest``) → ``BackendLoginSession``.
- ``GET /backends/login/current``·``GET /backends/login/{session_id}``
  → ``BackendLoginSession``(폴링 = 하트비트).
- ``POST /backends/login/{session_id}/input`` (``BackendLoginInput``) → 202.
- ``DELETE /backends/login/{session_id}`` → 취소 후 ``BackendLoginSession``.
- ``POST /backends/{id}/logout`` → ``BackendLogoutResult``.

비밀 값 규칙: 응답에는 토큰·코드를 담을 필드가 없다. 붙여 넣은 코드는 ``BackendLoginInput.text``로만
들어오고(쓰기 전용) 서버가 세션 가림 목록에 넣어 ``screen``·``message``·``details``에서 가린다.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr
from agent_console_contracts.common import FixAction

type BackendLoginPhase = Literal[
    "starting", "waiting_user", "verifying", "succeeded", "failed", "cancelled", "expired"
]
"""로그인 세션 수명 단계(서비스 어휘라 닫힌 목록).

- starting: 하위 과정을 띄우는 중.
- waiting_user: 사용자가 브라우저에서 로그인하거나 코드를 붙여 넣기를 기다림.
- verifying: 결과 확인 중.
- succeeded·failed·cancelled·expired: 끝(더 바뀌지 않음).
"""

BACKEND_LOGIN_TEXT_MAX_CHARS = 2048
"""``BackendLoginInput.text`` 최대 글자 수."""


class BackendLoginStartRequest(ContractModel):
    """``POST /backends/{id}/login`` 요청(본문 생략 가능). 실행 명령은 요청으로 바꿀 수 없다."""

    method_id: str | None = Field(
        default=None,
        description="로그인 방법 id(`BackendDescriptor.login_methods[].id`). null = 첫 방법.",
    )
    timeout_s: float | None = Field(
        default=None,
        gt=0,
        description="최대 진행 시간(초). null = 서버 기본. 서버 상한을 넘으면 상한으로 잘린다.",
    )


class BackendLoginSession(ContractModel):
    """진행 중이거나 끝난 로그인 세션 하나(서버 전체에서 진행 중인 세션은 하나뿐)."""

    session_id: NonEmptyStr
    backend_id: NonEmptyStr
    method_id: NonEmptyStr
    phase: BackendLoginPhase
    message: str = Field(default="", description="지금 단계 안내 또는 결과 문장(사용자 언어).")
    open_url: str | None = Field(
        default=None,
        description=(
            "브라우저에서 열 로그인 페이지(https, 백엔드가 허용한 호스트만). null = 아직 없음."
        ),
    )
    needs_code: bool = Field(
        default=False, description="브라우저에 나온 코드를 붙여 넣어야 하는 단계다."
    )
    code_label: str = Field(default="", description="코드 칸 라벨(사용자 언어).")
    accepts_keys: list[str] = Field(
        default_factory=list,
        description="`input`으로 보낼 수 있는 키 이름(예: enter). 밖의 키는 422.",
    )
    screen: list[str] = Field(
        default_factory=list,
        description="하위 과정 화면의 마지막 줄들(가림 적용, 문제 해결용). 비면 없음.",
    )
    warnings: list[str] = Field(
        default_factory=list, description="주의 문장(예: API 키 환경변수가 우선함)."
    )
    reason: str | None = Field(
        default=None,
        description=(
            "실패 사유 코드(열린 어휘, 예: cli_missing, pty_unavailable, exited, verify_failed, "
            "start_failed, timeout, heartbeat, error). 성공·진행 중이면 null."
        ),
    )
    details: JsonObject = Field(
        default_factory=dict, description="접힌 상세(종료 코드 등). 비밀 값 없음."
    )
    fixes: list[FixAction] = Field(default_factory=list, description="해결 버튼. 비면 없음.")
    started_at: float = Field(description="시작 시각(epoch 초).")
    expires_at: float = Field(description="시간 상한에 닿는 시각(epoch 초).")
    finished_at: float | None = Field(default=None, description="끝난 시각. 진행 중이면 null.")


class BackendLoginInput(ContractModel):
    """``POST /backends/login/{session_id}/input``: 글자 또는 키 하나(둘 중 하나만)."""

    text: str | None = Field(
        default=None,
        max_length=BACKEND_LOGIN_TEXT_MAX_CHARS,
        description=(
            "붙여 넣은 글자(예: 브라우저에 나온 코드). 앞뒤 공백은 서버가 자른다. "
            "인쇄 가능 문자만. 응답·로그에 다시 나오지 않는다."
        ),
        json_schema_extra={"writeOnly": True, "x-secret": True},
    )
    key: str | None = Field(
        default=None, description="보낼 키 이름(세션의 `accepts_keys` 안, 예: enter)."
    )

    @model_validator(mode="after")
    def _one_of(self) -> Self:
        if (self.text is None) == (self.key is None):
            raise ValueError("text와 key 중 하나만 보냅니다")
        return self


class BackendLogoutResult(ContractModel):
    """``POST /backends/{id}/logout`` 결과. 실행 기록·이벤트에 남지 않는다."""

    backend_id: NonEmptyStr
    ok: bool
    reason: str | None = Field(
        default=None, description="실패 사유 코드(열린 어휘). 성공이면 null."
    )
    message: str = Field(default="", description="결과 문장(사용자 언어).")
    fixes: list[FixAction] = Field(default_factory=list, description="해결 버튼. 비면 없음.")
    finished_at: float = Field(description="끝난 시각(epoch 초).")


__all__ = [
    "BACKEND_LOGIN_TEXT_MAX_CHARS",
    "BackendLoginInput",
    "BackendLoginPhase",
    "BackendLoginSession",
    "BackendLoginStartRequest",
    "BackendLogoutResult",
]
