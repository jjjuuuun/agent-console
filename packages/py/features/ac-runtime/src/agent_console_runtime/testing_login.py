"""로그인 확장 지점 테스트 도우미(공개, 운영 코드에서 쓰지 않는다).

- ``ManualLoginDriver``: 테스트가 ``update``로 진행을 바꾸는 ``LoginDriver``.
  받은 입력·취소를 기록하고, ``on_text``·``on_key``로 입력에 반응하는 대본을 붙일 수 있다.
- ``LoginBackendStub``: ``start_login``·``logout``을 가진 최소 백엔드(디스크립터 능력 선언 포함).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from agent_console_contracts import (
    BackendCapabilities,
    BackendDescriptor,
    BackendLogoutResult,
    LoginMethodInfo,
    ModelInfo,
)

from ._login import BackendLoginContext, LoginProgress


class ManualLoginDriver:
    """테스트가 움직이는 로그인 드라이버.

    Args:
        progress: 처음 상태(기본 ``waiting_user`` + 코드 칸).
        on_text: ``(driver, text)`` — 글자를 받았을 때(``update``로 반응).
        on_key: ``(driver, key)`` — 키를 받았을 때.
        fail_cancel: 참이면 ``cancel``이 예외를 낸다(서비스가 견디는지 확인).
    """

    def __init__(
        self,
        progress: LoginProgress | None = None,
        *,
        on_text: Callable[[ManualLoginDriver, str], None] | None = None,
        on_key: Callable[[ManualLoginDriver, str], None] | None = None,
        fail_cancel: bool = False,
    ) -> None:
        self._progress = progress or LoginProgress(
            phase="waiting_user",
            message="브라우저에서 로그인하세요",
            open_url="https://login.example/authorize",
            needs_code=True,
            code_label="코드",
        )
        self._changed = asyncio.Event()
        self._on_text = on_text
        self._on_key = on_key
        self._fail_cancel = fail_cancel
        self.texts: list[str] = []
        self.keys: list[str] = []
        self.cancel_calls = 0

    def update(self, progress: LoginProgress | None = None, **changes: Any) -> None:
        """상태를 바꾸고 기다리는 쪽을 깨운다(``progress`` 전체 또는 바꿀 필드만)."""
        self._progress = progress if progress is not None else replace(self._progress, **changes)
        self._changed.set()

    @property
    def cancelled(self) -> bool:
        """``cancel``이 한 번 이상 불렸다."""
        return self.cancel_calls > 0

    # LoginDriver
    def progress(self) -> LoginProgress:
        return self._progress

    async def wait_changed(self, timeout: float) -> None:
        try:
            await asyncio.wait_for(self._changed.wait(), timeout)
        except TimeoutError:
            return
        self._changed.clear()

    async def send_text(self, text: str) -> None:
        self.texts.append(text)
        if self._on_text is not None:
            self._on_text(self, text)

    async def send_key(self, key: str) -> None:
        self.keys.append(key)
        if self._on_key is not None:
            self._on_key(self, key)

    async def cancel(self) -> None:
        self.cancel_calls += 1
        if self._fail_cancel:
            raise RuntimeError("cancel failed")

    def secrets_to_mask(self) -> list[str]:
        return list(self.texts)


class LoginBackendStub:
    """로그인·로그아웃 능력을 가진 최소 백엔드(실행은 하지 않는다).

    Args:
        backend_id: 디스크립터 id.
        make_driver: ``(ctx, method_id)`` → 드라이버(기본 ``ManualLoginDriver()``).
        methods: 로그인 방법(디스크립터 ``login_methods``).
        logout_result: ``logout``이 돌려줄 결과를 만드는 함수(기본 성공).
        login: ``capabilities.login`` 선언.
        logout: ``capabilities.logout`` 선언.
    """

    def __init__(
        self,
        backend_id: str = "stub",
        *,
        make_driver: Callable[[BackendLoginContext, str], Any] | None = None,
        methods: Sequence[LoginMethodInfo] = (LoginMethodInfo(id="m1", label="로그인"),),
        logout_result: Callable[[BackendLoginContext], BackendLogoutResult] | None = None,
        login: bool = True,
        logout: bool = True,
    ) -> None:
        self.descriptor = BackendDescriptor(
            id=backend_id,
            title=backend_id,
            capabilities=BackendCapabilities(login=login, logout=logout),
            login_methods=list(methods),
        )
        self._make = make_driver
        self._logout_result = logout_result
        self.drivers: list[Any] = []
        self.contexts: list[BackendLoginContext] = []
        self.logout_calls = 0

    async def start_login(self, ctx: BackendLoginContext, method_id: str) -> Any:
        self.contexts.append(ctx)
        driver = self._make(ctx, method_id) if self._make is not None else ManualLoginDriver()
        self.drivers.append(driver)
        return driver

    async def logout(self, ctx: BackendLoginContext, method_id: str | None) -> BackendLogoutResult:
        self.logout_calls += 1
        if self._logout_result is not None:
            return self._logout_result(ctx)
        return BackendLogoutResult(
            backend_id=ctx.backend_id, ok=True, message="로그아웃했습니다", finished_at=ctx.clock()
        )

    # ExecutionBackend 최소 모양(서비스는 쓰지 않는다)
    async def run(self, request: Any, sink: Any, cancel: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def list_models(self) -> list[ModelInfo]:  # pragma: no cover - 쓰지 않음
        return []


__all__ = ["LoginBackendStub", "ManualLoginDriver"]
