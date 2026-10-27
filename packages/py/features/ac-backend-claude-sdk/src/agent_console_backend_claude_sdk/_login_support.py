"""``ClaudeSdkBackend``의 로그인·로그아웃 능력(ux-overhaul §15.9, 5.2R.82).

백엔드는 이 객체에 위임한다. PTY(선택 추가 기능 ``login``)가 없으면 능력을 선언하지 않고 상태
점검 ``detail``에 설치 안내만 더한다(실패가 아님).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from agent_console_contracts import (
    BackendLogoutResult,
    ErrorCodes,
    LoginMethodInfo,
    ReadinessAction,
)
from agent_console_runtime import BackendLoginContext, LoginDriver, LoginRefusedError

from ._env import EnvPolicy
from ._login import (
    CLI_LOGIN_METHOD_ID,
    ClaudeSdkLoginOptions,
    LoginReasonCodes,
    env_warnings,
    login_env,
    writes_lines,
)
from ._readiness import ClaudeSdkReadinessOptions, ReadinessStates


@dataclass(frozen=True)
class PtySupport:
    """PTY를 쓸 수 있는지(``reason`` = ``missing_package``·``missing_library``·
    ``unsupported_platform``)."""

    available: bool
    reason: str | None = None


def detect_pty(spawner: Any | None) -> PtySupport:
    """``agent-console-pty-session``과 플랫폼 어댑터를 쓸 수 있는지(주입한 어댑터가 있으면 참)."""
    if spawner is not None:
        return PtySupport(True)
    try:
        import agent_console_pty_session as pty
    except ImportError:
        return PtySupport(False, "missing_package")
    try:
        pty.default_spawner()
    except pty.PtyUnavailableError as exc:
        return PtySupport(False, exc.reason)
    return PtySupport(True)


class ClaudeLoginSupport:
    """구독 로그인(``cli-login``)·로그아웃.

    Args:
        options: 설치자 설정 ``login``.
        allow_subscription_auth: 설치자 설정(꺼짐 = 능력 없음, 시작 거절).
        readiness: 실행 파일 경로(``cli_path``)를 쓴다.
        cli_locator: 실행 파일 찾기.
        env_policy: 하위 프로세스 환경 정책(실행과 같은 허용 목록).
        environ: 부모 환경(None = ``ctx.environ``, 그것도 비면 ``os.environ``).
        spawner: PTY 어댑터(테스트 주입, None = 플랫폼 기본).
        pty: PTY 사용 가능 여부(None = ``detect_pty(spawner)``).
    """

    def __init__(
        self,
        options: ClaudeSdkLoginOptions,
        *,
        allow_subscription_auth: bool,
        readiness: ClaudeSdkReadinessOptions,
        cli_locator: Callable[[str | None], str | None],
        env_policy: EnvPolicy,
        environ: Mapping[str, str] | None,
        spawner: Any | None = None,
        pty: PtySupport | None = None,
    ) -> None:
        self.options = options
        self._allow = allow_subscription_auth
        self._readiness = readiness
        self._locate = cli_locator
        self._policy = env_policy
        self._environ = environ
        self._spawner = spawner
        self.pty = (
            pty
            if pty is not None
            else (
                detect_pty(spawner)
                if options.enabled and allow_subscription_auth
                else PtySupport(False)
            )
        )

    @property
    def enabled(self) -> bool:
        """능력을 선언한다(설정 켜짐 + 구독 허용 + PTY 있음)."""
        return self.options.enabled and self._allow and self.pty.available

    @property
    def unavailable_note(self) -> str | None:
        """설정은 켜졌는데 PTY가 없을 때 상태 ``detail``에 더할 안내."""
        if self.options.enabled and self._allow and not self.pty.available:
            return self.options.texts.unavailable_detail
        return None

    def _parent(self, ctx_environ: Mapping[str, str] | None = None) -> Mapping[str, str]:
        if self._environ is not None:
            return self._environ
        return ctx_environ or os.environ

    def methods(self) -> list[LoginMethodInfo]:
        """디스크립터 ``login_methods``(능력이 없으면 빈 목록)."""
        if not self.enabled:
            return []
        t = self.options.texts
        return [
            LoginMethodInfo(
                id=CLI_LOGIN_METHOD_ID,
                label=t.label,
                description=t.description,
                notice=t.notice,
                writes=writes_lines(self.options, self._parent()),
                needs_browser=True,
            )
        ]

    def actions(self, state: str, *, token_auth: bool) -> list[ReadinessAction]:
        """상태 → 동작 버튼. 로그인 파일이 없으면 주 버튼 [로그인], 있으면 메뉴의 다시 로그인·
        로그아웃.

        토큰 비밀(``oauth_token``) 방식이면 앱이 그 비밀을 바꿀 수 없으므로 버튼이 없다.
        """
        if not self.enabled or token_auth:
            return []
        t = self.options.texts
        if state == ReadinessStates.SUBSCRIPTION_UNVERIFIED:
            return [
                ReadinessAction(
                    kind="login", method_id=CLI_LOGIN_METHOD_ID, label=t.label, primary=True
                )
            ]
        if state == ReadinessStates.SUBSCRIPTION_READY:
            return [
                ReadinessAction(kind="login", method_id=CLI_LOGIN_METHOD_ID, label=t.relogin_label),
                ReadinessAction(kind="logout", method_id=CLI_LOGIN_METHOD_ID, label=t.logout_label),
            ]
        return []

    def _argv(self, configured: list[str] | None, verb: str) -> list[str] | None:
        if configured:
            return list(configured)
        cli = self._locate(self._readiness.cli_path)
        return [cli, "auth", verb] if cli else None

    def refusal(self) -> LoginRefusedError | None:
        """능력이 꺼진 이유 중 사용자가 알아야 할 것(구독 방식 꺼짐). 없으면 None."""
        if not self._allow:
            return LoginRefusedError(
                ErrorCodes.BACKEND_SUBSCRIPTION_AUTH_DISABLED,
                "구독 방식이 설치자 설정(allow_subscription_auth)으로 꺼져 있어 로그인할 수 "
                "없습니다.",
            )
        return None

    def _refuse_if_disabled(self) -> None:
        refused = self.refusal()
        if refused is not None:
            raise refused
        if not self.enabled:
            raise LoginRefusedError(
                ErrorCodes.BACKEND_LOGIN_UNSUPPORTED, "이 백엔드의 앱 화면 로그인이 꺼져 있습니다."
            )

    async def start(self, ctx: BackendLoginContext, method_id: str) -> LoginDriver:
        """``claude auth login``을 PTY로 띄운다.

        Raises:
            LoginRefusedError: 구독 방식이 꺼졌거나 능력이 없거나 모르는 방법.
        """
        self._refuse_if_disabled()
        if method_id != CLI_LOGIN_METHOD_ID:
            raise LoginRefusedError(
                ErrorCodes.BACKEND_LOGIN_UNSUPPORTED, "알 수 없는 로그인 방법입니다."
            )
        from ._login_driver import ClaudeCliLoginDriver

        parent = self._parent(ctx.environ)
        return await ClaudeCliLoginDriver.start(
            self.options,
            argv=self._argv(self.options.command, "login"),
            status_argv=self._argv(self.options.status_command, "status"),
            env=login_env(parent, self._policy, self.options),
            warnings=env_warnings(parent, self.options),
            spawner=self._spawner,
        )

    async def logout(self, ctx: BackendLoginContext) -> BackendLogoutResult:
        """``claude auth logout``을 PTY로 실행한다(묻는 화면이 있어도 견딘다)."""
        self._refuse_if_disabled()
        from agent_console_pty_session import PtySession, PtyUnavailableError

        t = self.options.texts
        argv = self._argv(self.options.logout_command, "logout")

        def result(ok: bool, message: str, reason: str | None = None) -> BackendLogoutResult:
            fixes = [t.fix_cli.action()] if reason == LoginReasonCodes.CLI_MISSING else []
            return BackendLogoutResult(
                backend_id=ctx.backend_id,
                ok=ok,
                reason=reason,
                message=message,
                fixes=fixes,
                finished_at=ctx.clock(),
            )

        if argv is None:
            return result(False, t.logout_cli_missing, LoginReasonCodes.CLI_MISSING)
        parent = self._parent(ctx.environ)
        size = self.options.pty_size
        try:
            session = await PtySession.spawn(
                argv,
                env=login_env(parent, self._policy, self.options),
                cwd=self.options.cwd,
                cols=size.cols,
                rows=size.rows,
                spawner=self._spawner,
            )
        except PtyUnavailableError:
            return result(False, t.failed_pty_unavailable, LoginReasonCodes.PTY_UNAVAILABLE)
        except FileNotFoundError:
            return result(False, t.logout_cli_missing, LoginReasonCodes.CLI_MISSING)
        except (OSError, ValueError):
            return result(False, t.failed_start, LoginReasonCodes.START_FAILED)
        try:
            code = await session.wait_exit(self.options.logout_timeout_s)
        finally:
            await session.terminate(self.options.terminate_grace_s)
        if code is None:
            return result(
                False,
                t.logout_timeout.format(seconds=self.options.logout_timeout_s),
                LoginReasonCodes.TIMEOUT,
            )
        if code != 0:
            return result(False, t.logout_failed.format(code=code), LoginReasonCodes.LOGOUT_FAILED)
        return result(True, t.logout_ok)


__all__ = ["ClaudeLoginSupport", "PtySupport", "detect_pty"]
