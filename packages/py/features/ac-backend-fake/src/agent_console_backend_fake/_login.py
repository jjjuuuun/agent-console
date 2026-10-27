"""fake 백엔드의 대본 로그인(ux-overhaul §15.9, 5.2R.83) — PTY·네트워크·파일 없음.

e2e와 웹 개발에서 로그인 흐름 전체(URL, 코드, 성공·실패·취소·시간 초과)를 재현한다. 대본은 설치자
설정 ``login``(``FakeLoginScript``) 데이터다.

- 시작 → (``start_delay_s``) → ``waiting_user``(``open_url``, ``needs_code``, 화면 줄).
- 코드가 ``success_code``면 ``verifying`` → (``verify_delay_s``) → ``succeeded``, 그 밖은 ``failed``
  (``fail_reason``, 기본 ``verify_failed``).
- ``needs_code=false``이고 ``callback_after_s``가 있으면 그 초 뒤 코드 없이 성공(콜백 경로).
- 취소·시간 초과는 서비스가 한다(대본은 기다리기만 한다).
- 로그인 상태는 백엔드 인스턴스 메모리에만 있다(``FakeLoginState``). 서버를 다시 띄우면
  ``start_logged_in``으로 돌아간다.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import LoginMethodInfo, ReadinessAction
from agent_console_runtime import LoginProgress

FAKE_LOGIN_METHOD_ID = "script"
"""대본 로그인 방법 기본 id."""

FAKE_LOGIN_REQUIRED_STATE = "login_required"
"""대본 로그인이 켜졌고 로그인하지 않은 상태(``BackendReadiness.state``)."""


class FakeLoginTexts(BaseModel):
    """대본 로그인 문구(데이터)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="구독으로 로그인", min_length=1)
    relogin_label: str = Field(default="다시 로그인", min_length=1)
    logout_label: str = Field(default="로그아웃(연결 해제)", min_length=1)
    description: str = "체험용 대본 로그인입니다(실제 계정·파일을 쓰지 않음)."
    notice: str = "체험용: 실제 로그인이 아닙니다. 코드에 ok를 넣으면 성공합니다."
    writes: list[str] = Field(
        default_factory=lambda: ["바뀌는 파일 없음(체험용 메모리 상태)"],
        description="시작 확인 창의 쓰기 범위 줄.",
    )
    starting: str = "로그인을 준비하고 있습니다."
    waiting_browser: str = "브라우저에서 로그인하세요(체험용 주소)."
    waiting_code: str = "브라우저에 보이는 코드를 붙여 넣으세요(체험용: ok)."
    code_label: str = "인증 코드"
    verifying: str = "로그인을 확인하고 있습니다."
    succeeded: str = "로그인됨 — 체험용"
    failed: str = "로그인을 확인하지 못했습니다. 다시 시도하세요."
    status_required_summary: str = "로그인 필요 (체험용)"
    status_required_short: str = "로그인 필요"
    status_ready_summary: str = "로그인됨 (체험용)"
    status_ready_short: str = "로그인됨"
    logout_ok: str = "로그아웃했습니다(체험용)."
    logout_failed: str = "로그아웃하지 못했습니다(체험용)."


class FakeLoginScript(BaseModel):
    """설치자 설정 ``login``(``backends.fake.login``): 대본 로그인. 없으면(null) 능력 없음."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="대본 로그인·로그아웃을 제공한다.")
    method_id: str = Field(default=FAKE_LOGIN_METHOD_ID, min_length=1, description="방법 id.")
    open_url: str | None = Field(
        default="https://login.example.com/oauth/authorize?fake=1",
        description="waiting_user에서 보일 주소(https). null = 주소 없음.",
    )
    needs_code: bool = Field(default=True, description="코드 붙여 넣기를 기다린다.")
    success_code: str = Field(default="ok", min_length=1, description="성공으로 볼 코드.")
    fail_reason: str = Field(
        default="verify_failed", min_length=1, description="코드가 틀렸을 때 사유 코드."
    )
    start_delay_s: float = Field(default=0.0, ge=0, le=60, description="starting에 머무는 초.")
    verify_delay_s: float = Field(default=0.0, ge=0, le=60, description="verifying에 머무는 초.")
    callback_after_s: float | None = Field(
        default=None,
        ge=0,
        le=600,
        description="needs_code=false일 때 이 초 뒤 코드 없이 성공(콜백 경로). null = 기다리기만.",
    )
    accepts_keys: list[str] = Field(
        default_factory=list, description="받는 키(비면 서비스 기본: enter·up·down·escape)."
    )
    screen: list[str] = Field(
        default_factory=lambda: [
            "Browser didn't open? Use the url below to sign in",
            "https://login.example.com/oauth/authorize?fake=1",
            "Paste code here if prompted >",
        ],
        description="CLI 화면 줄(체험용).",
    )
    start_logged_in: bool = Field(default=False, description="처음부터 로그인된 상태로 시작한다.")
    logout_ok: bool = Field(default=True, description="로그아웃이 성공한다.")
    texts: FakeLoginTexts = Field(default_factory=FakeLoginTexts, description="문구.")

    def method(self) -> LoginMethodInfo:
        """디스크립터 ``login_methods`` 항목."""
        t = self.texts
        return LoginMethodInfo(
            id=self.method_id,
            label=t.label,
            description=t.description,
            notice=t.notice,
            writes=list(t.writes),
            needs_browser=self.open_url is not None,
        )

    def actions(self, logged_in: bool) -> list[ReadinessAction]:
        """상태 카드 동작: 로그인 전 = 주 버튼 [로그인], 로그인 뒤 = 메뉴의 다시 로그인·로그아웃."""
        t = self.texts
        if not logged_in:
            return [
                ReadinessAction(kind="login", method_id=self.method_id, label=t.label, primary=True)
            ]
        return [
            ReadinessAction(kind="login", method_id=self.method_id, label=t.relogin_label),
            ReadinessAction(kind="logout", method_id=self.method_id, label=t.logout_label),
        ]


@dataclass
class FakeLoginState:
    """메모리 로그인 상태(백엔드 인스턴스 하나에 하나)."""

    logged_in: bool = False


class FakeScriptedLoginDriver:
    """``FakeLoginScript``대로 움직이는 ``LoginDriver``(PTY·네트워크 없음).

    Args:
        script: 대본.
        on_success: 성공했을 때 부른다(백엔드가 로그인 상태를 바꾼다).
    """

    def __init__(self, script: FakeLoginScript, *, on_success: Callable[[], None]) -> None:
        self._s = script
        self._t = script.texts
        self._on_success = on_success
        self._changed = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._inputs: list[str] = []
        self.keys: list[str] = []
        self._phase = "starting"
        self._message = self._t.starting
        self._reason: str | None = None
        self._needs_code = False
        self._screen: list[str] = []
        self._details: dict[str, Any] = {}

    def begin(self) -> None:
        """대본을 시작한다(루프 안에서). ``start_delay_s``가 0이면 바로 ``waiting_user``다."""
        if not self._s.start_delay_s:
            self._enter_waiting()
        self._spawn(self._run_start())

    def _spawn(self, coro: Any) -> None:
        self._tasks.append(asyncio.ensure_future(coro))

    def _bump(self) -> None:
        self._changed.set()

    def _enter_waiting(self) -> None:
        self._phase = "waiting_user"
        self._needs_code = self._s.needs_code
        self._message = self._t.waiting_code if self._s.needs_code else self._t.waiting_browser
        self._screen = list(self._s.screen)
        self._bump()

    async def _run_start(self) -> None:
        if self._s.start_delay_s:
            await asyncio.sleep(self._s.start_delay_s)
            self._enter_waiting()
        if not self._s.needs_code and self._s.callback_after_s is not None:
            await asyncio.sleep(self._s.callback_after_s)
            self._enter_verifying()
            await self._verify(ok=True)

    def _enter_verifying(self) -> None:
        self._phase = "verifying"
        self._needs_code = False
        self._message = self._t.verifying
        self._bump()

    async def _verify(self, *, ok: bool) -> None:
        if self._s.verify_delay_s:
            await asyncio.sleep(self._s.verify_delay_s)
        if ok:
            self._phase = "succeeded"
            self._message = self._t.succeeded
            self._on_success()
        else:
            self._phase = "failed"
            self._message = self._t.failed
            self._reason = self._s.fail_reason
            self._details = {"scripted": True}
        self._bump()

    # LoginDriver
    def progress(self) -> LoginProgress:
        """지금 상태."""
        waiting = self._phase == "waiting_user"
        return LoginProgress(
            phase=self._phase,
            message=self._message,
            open_url=self._s.open_url if waiting else None,
            needs_code=self._needs_code,
            code_label=self._t.code_label,
            accepts_keys=list(self._s.accepts_keys),
            screen=list(self._screen),
            reason=self._reason,
            details=dict(self._details),
        )

    async def wait_changed(self, timeout: float) -> None:
        """바뀌거나 ``timeout``초가 지날 때까지."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._changed.wait(), timeout)
        self._changed.clear()

    async def send_text(self, text: str) -> None:
        """코드를 받는다(``success_code``면 성공, 그 밖은 ``fail_reason``)."""
        if self._phase != "waiting_user":
            raise RuntimeError("코드를 받을 단계가 아닙니다")
        self._inputs.append(text)
        self._enter_verifying()
        self._spawn(self._verify(ok=text == self._s.success_code))

    async def send_key(self, key: str) -> None:
        """키를 기록만 한다(체험용)."""
        self.keys.append(key)

    async def cancel(self) -> None:
        """대본을 멈춘다(로그인 상태는 바꾸지 않는다)."""
        for task in self._tasks:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    def secrets_to_mask(self) -> list[str]:
        """받은 코드."""
        return list(self._inputs)


__all__ = [
    "FAKE_LOGIN_METHOD_ID",
    "FAKE_LOGIN_REQUIRED_STATE",
    "FakeLoginScript",
    "FakeLoginState",
    "FakeLoginTexts",
    "FakeScriptedLoginDriver",
]
