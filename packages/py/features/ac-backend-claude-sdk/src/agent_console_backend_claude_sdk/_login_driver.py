"""``ClaudeCliLoginDriver``: ``claude auth login``을 PTY로 중계하는 ``LoginDriver``(§15.9).

선택 추가 기능 ``login``(``agent-console-pty-session``)이 있어야 불러올 수 있다. 백엔드는 이 모듈을
지연 import한다.

흐름: 띄움(``starting``) → 화면 글자 규칙으로 URL·코드 요청을 알아봄(``waiting_user``) → 성공 문구면
``on_success_keys``를 보냄 → CLI가 끝나면(또는 성공 문구 뒤 ``exit_wait_s``) 하위 프로세스를
정리하고
``status_command``로 확인(``verifying``) → ``succeeded`` 또는 ``failed``. 판정은 늘 확인 명령이다.

원시 출력은 PTY 세션 메모리에만 있고 세션이 끝나면 버린다. 이 모듈은 아무것도 로그에 남기지 않는다.
붙여 넣은 값은 ``secrets_to_mask``로 서비스에 알려 화면 줄에서 가린다(PTY 에코).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Mapping, Sequence
from typing import Any

from agent_console_pty_session import (
    ExpectRule,
    ExpectRules,
    ExpectWatcher,
    PtySession,
    PtySpawner,
    PtyUnavailableError,
)
from agent_console_runtime import LoginProgress

from ._login import (
    ClaudeSdkLoginOptions,
    LoginReasonCodes,
    allowed_open_url,
    safe_rule_compile,
    verify_login,
)

_IDLE_FLUSH_S = 0.5
"""출력이 이만큼 멈추면 끝나지 않은 줄에서 미뤄 둔 규칙 맞음을 처리한다."""


def build_expect_rules(options: ClaudeSdkLoginOptions) -> ExpectRules:
    """설정 규칙 → ``ExpectRules``(안전 검사 컴파일)."""
    return ExpectRules(
        [ExpectRule(name, pattern) for name, pattern in options.rules.named()],
        compile=safe_rule_compile,
    )


class ClaudeCliLoginDriver:
    """Claude Code CLI 로그인 과정 하나.

    ``start``로 만든다. 띄우지 못하면 이미 ``failed``인 드라이버를 돌려준다(사유 코드와 문구).

    Args:
        options: 설치자 설정 ``login``.
        argv: 로그인 실행 인자(None = 실행 파일을 찾지 못함 → ``cli_missing``).
        status_argv: 확인 실행 인자.
        env: 하위 프로세스 환경 전체.
        warnings: 진행에 늘 실을 안내.
        spawner: PTY 어댑터(None = 플랫폼 기본).
    """

    def __init__(
        self,
        options: ClaudeSdkLoginOptions,
        *,
        argv: Sequence[str] | None,
        status_argv: Sequence[str] | None,
        env: Mapping[str, str],
        warnings: Sequence[str] = (),
        spawner: PtySpawner | None = None,
    ) -> None:
        self._opts = options
        self._t = options.texts
        self._argv = list(argv) if argv else None
        self._status_argv = list(status_argv) if status_argv else None
        self._env = dict(env)
        self._warnings = list(warnings)
        self._spawner = spawner
        self._rules = build_expect_rules(options)
        self._session: PtySession | None = None
        self._task: asyncio.Task[None] | None = None
        self._changed = asyncio.Event()
        self._inputs: list[str] = []
        self._cancelled = False
        self._closed_screen: list[str] = []
        # 진행 상태
        self._phase = "starting"
        self._message = self._t.starting
        self._open_url: str | None = None
        self._needs_code = False
        self._reason: str | None = None
        self._details: dict[str, Any] = {}
        self._fixes: list[Any] = []
        self._success_seen = False
        self._success_deadline: float | None = None
        self._failure_seen = False

    @classmethod
    async def start(
        cls,
        options: ClaudeSdkLoginOptions,
        *,
        argv: Sequence[str] | None,
        status_argv: Sequence[str] | None,
        env: Mapping[str, str],
        warnings: Sequence[str] = (),
        spawner: PtySpawner | None = None,
    ) -> ClaudeCliLoginDriver:
        """로그인 과정을 띄운다(실패해도 예외 대신 ``failed`` 드라이버)."""
        driver = cls(
            options,
            argv=argv,
            status_argv=status_argv,
            env=env,
            warnings=warnings,
            spawner=spawner,
        )
        await driver._begin()
        return driver

    # ------------------------------------------------------------ 시작

    async def _begin(self) -> None:
        if self._argv is None or self._status_argv is None:
            self._fail(LoginReasonCodes.CLI_MISSING, self._t.failed_cli_missing, [self._t.fix_cli])
            return
        size = self._opts.pty_size
        try:
            self._session = await PtySession.spawn(
                self._argv,
                env=self._env,
                cwd=self._opts.cwd,
                cols=size.cols,
                rows=size.rows,
                spawner=self._spawner,
            )
        except PtyUnavailableError as exc:
            self._fail(
                LoginReasonCodes.PTY_UNAVAILABLE,
                self._t.failed_pty_unavailable,
                [self._t.fix_settings],
                {"pty_reason": exc.reason},
            )
            return
        except FileNotFoundError:
            self._fail(LoginReasonCodes.CLI_MISSING, self._t.failed_cli_missing, [self._t.fix_cli])
            return
        except (OSError, ValueError) as exc:
            self._fail(
                LoginReasonCodes.START_FAILED,
                self._t.failed_start,
                [],
                {"error": type(exc).__name__},
            )
            return
        self._task = asyncio.ensure_future(self._pump(self._session))

    # ------------------------------------------------------------ 진행

    def _bump(self) -> None:
        self._changed.set()

    def _fail(
        self,
        reason: str,
        message: str,
        fixes: Sequence[Any] = (),
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self._phase = "failed"
        self._reason = reason
        self._message = message
        self._needs_code = False
        self._open_url = None
        self._fixes = [f.action() for f in fixes]
        self._details.update(details or {})
        self._bump()

    async def _pump(self, session: PtySession) -> None:
        watcher = ExpectWatcher(self._rules)
        offset = 0
        version = 0
        try:
            while True:
                new = await session.wait_changed(version, _IDLE_FLUSH_S)
                idle = new == version
                version = new
                chunk = session.text_since(offset)
                offset = chunk.offset
                matches = watcher.feed(chunk.text)
                if idle or session.output_ended:
                    matches += watcher.flush()
                for link in session.links():
                    matches += [m for m in self._rules.match_line(link) if m.name == "open_url"]
                for found in matches:
                    self._on_signal(session, found.name, found.text)
                self._bump()
                if session.output_ended or not session.is_alive():
                    break
                if self._success_seen and self._success_deadline is not None:
                    loop = asyncio.get_running_loop()
                    if loop.time() >= self._success_deadline:
                        break
            await self._finish(session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 문장은 버리고 형식 이름만(출력이 섞일 수 있다)
            with contextlib.suppress(Exception):
                await self._close(session, 0.0)
            self._fail(
                LoginReasonCodes.START_FAILED,
                self._t.failed_start,
                [],
                {"error": type(exc).__name__},
            )

    def _on_signal(self, session: PtySession, name: str, text: str) -> None:
        if name == "open_url":
            url = allowed_open_url(text, self._opts.allowed_url_hosts)
            if url is not None and self._open_url is None:
                self._open_url = url
                self._enter_waiting(self._t.waiting_browser)
        elif name == "needs_code":
            self._needs_code = True
            self._enter_waiting(self._t.waiting_code)
        elif name == "success" and not self._success_seen:
            self._success_seen = True
            self._needs_code = False
            self._message = self._t.verifying
            for key in self._opts.on_success_keys:
                with contextlib.suppress(Exception):
                    session.send_key(key)
            self._success_deadline = asyncio.get_running_loop().time() + self._opts.exit_wait_s
        elif name == "failure" and not self._success_seen:
            self._failure_seen = True
            self._message = self._t.failure_seen

    def _enter_waiting(self, message: str) -> None:
        if self._phase == "starting":
            self._phase = "waiting_user"
        if not self._success_seen:
            self._message = message

    async def _finish(self, session: PtySession) -> None:
        exit_code = await self._close(session, self._opts.exit_wait_s)
        if self._cancelled:
            return
        self._phase = "verifying"
        self._message = self._t.verifying
        self._needs_code = False
        self._details["exit_code"] = exit_code
        self._bump()
        assert self._status_argv is not None
        try:
            outcome = await verify_login(
                self._status_argv,
                env=self._env,
                cwd=self._opts.cwd,
                timeout_s=self._opts.status_timeout_s,
                success_auth_methods=self._opts.success_auth_methods,
            )
        except FileNotFoundError:
            self._fail(LoginReasonCodes.CLI_MISSING, self._t.failed_cli_missing, [self._t.fix_cli])
            return
        except OSError as exc:
            self._fail(
                LoginReasonCodes.VERIFY_FAILED,
                self._t.failed_verify,
                [],
                {"error": type(exc).__name__},
            )
            return
        self._details.update(outcome.details)
        if outcome.ok:
            self._phase = "succeeded"
            self._message = self._t.succeeded
            self._open_url = None
            self._bump()
            return
        if self._success_seen or exit_code == 0:
            self._fail(LoginReasonCodes.VERIFY_FAILED, self._t.failed_verify)
        else:
            self._fail(LoginReasonCodes.EXITED, self._t.failed_exited)

    async def _close(self, session: PtySession, wait_s: float) -> int | None:
        """하위 프로세스가 끝나기를 ``wait_s``초 기다린 뒤 정리하고(유예 뒤 강제) 마지막 화면 줄을
        남긴다. 스스로 끝났으면 그 종료 코드, 아니면 종료 신호 뒤의 코드."""
        code: int | None = None
        if session.output_ended or not session.is_alive():
            code = await session.wait_exit(wait_s)
        result = await session.terminate(self._opts.terminate_grace_s)
        self._closed_screen = session.screen_lines(self._opts.screen_lines or None)
        return code if code is not None else result

    # ------------------------------------------------------------ LoginDriver

    def progress(self) -> LoginProgress:
        """지금 상태(화면 줄은 서비스가 가린다)."""
        session = self._session
        screen = self._closed_screen
        if session is not None and not screen:
            screen = session.screen_lines(self._opts.screen_lines or None)
        if self._opts.screen_lines == 0:
            screen = []
        return LoginProgress(
            phase=self._phase,
            message=self._message,
            open_url=self._open_url,
            needs_code=self._needs_code,
            code_label=self._t.code_label,
            screen=list(screen),
            warnings=list(self._warnings),
            reason=self._reason,
            details=dict(self._details),
            fixes=list(self._fixes),
        )

    async def wait_changed(self, timeout: float) -> None:
        """상태가 바뀌거나 ``timeout``초가 지날 때까지 기다린다."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._changed.wait(), timeout)
        self._changed.clear()

    async def send_text(self, text: str) -> None:
        """붙여 넣은 글자 + ``submit_keys``를 보낸다.

        Raises:
            RuntimeError: 하위 프로세스가 없거나 끝났다(문장에 값 없음).
        """
        self._inputs.append(text)
        session = self._live()
        session.write(text)
        for key in self._opts.submit_keys:
            session.send_key(key)
        self._needs_code = False
        if not self._success_seen:
            self._message = self._t.code_sent
        self._bump()

    async def send_key(self, key: str) -> None:
        """이름 붙은 키 하나를 보낸다.

        Raises:
            RuntimeError: 하위 프로세스가 없거나 끝났다.
            KeyError: 모르는 키 이름.
        """
        self._live().send_key(key)

    def _live(self) -> PtySession:
        session = self._session
        if session is None or self._phase in {"verifying", "succeeded", "failed"}:
            raise RuntimeError("로그인 과정이 진행 중이 아닙니다")
        return session

    async def cancel(self) -> None:
        """멈추고 하위 프로세스를 정리한다(여러 번 불러도 된다). 로그인 정보는 바꾸지 않는다."""
        self._cancelled = True
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        session = self._session
        if session is not None:
            with contextlib.suppress(Exception):
                await session.terminate(self._opts.terminate_grace_s)
        self._bump()

    def secrets_to_mask(self) -> list[str]:
        """붙여 넣은 값(PTY가 에코하므로 화면 줄에 다시 나올 수 있다)."""
        return list(self._inputs)

    @property
    def pid(self) -> int | None:
        """하위 프로세스 id(테스트·진단용)."""
        return self._session.pid if self._session is not None else None


__all__ = ["ClaudeCliLoginDriver", "build_expect_rules"]
