"""준비 신호와 "준비되면 열기"(`serve --open`, design §2R.13a).

서버가 요청을 받기 시작하면(uvicorn `started`) 준비 줄을 로그에 남기고,
`web.open.enabled`면 URL을 연다.
브라우저·하위 프로세스·시간은 모두 주입받는다(테스트는 가짜로, 실제 브라우저를 열지 않는다).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from ._config import ServerSettings, WebOpenSettings, is_loopback_host

_log = logging.getLogger("agent_console_server")

Opener = Callable[[str], None]
"""URL 하나를 연다(기본 브라우저, 지정 명령 등). 예외는 호출자가 경고로 남긴다."""

_WILDCARD_HOSTS = ("0.0.0.0", "::", "")


class ServerLike(Protocol):
    """uvicorn `Server`에서 쓰는 부분(테스트에서 가짜로 바꿀 수 있게)."""

    started: bool
    servers: Any


def build_opener(
    settings: WebOpenSettings,
    *,
    browser: Callable[[str], object] | None = None,
    spawn: Callable[[Sequence[str]], object] | None = None,
) -> Opener:
    """설정에 맞는 열기 함수를 만든다.

    Args:
        settings: `web.open`. `command`가 있으면 그 명령(셸 없이, `{url}` 치환), 없으면 브라우저.
        browser: 기본 브라우저 열기(기본 `webbrowser.open`, 처음 열 때 import).
        spawn: 명령 실행(기본: 기다리지 않는 하위 프로세스, 표준 입출력 닫음).
    """
    command = settings.command
    if command:
        run = spawn or _spawn_detached
        template = list(command)

        def open_with_command(url: str) -> None:
            run([part.replace("{url}", url) for part in template])

        return open_with_command

    def open_in_browser(url: str) -> None:
        if browser is not None:
            browser(url)
            return
        import webbrowser

        webbrowser.open(url)

    return open_in_browser


def _spawn_detached(args: Sequence[str]) -> object:
    import subprocess

    return subprocess.Popen(
        list(args),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def display_host(host: str) -> str:
    """URL에 쓸 호스트. 루프백·와일드카드 주소는 `localhost`, IPv6는 대괄호로 감싼다."""
    if host in _WILDCARD_HOSTS or is_loopback_host(host):
        return "localhost"
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def server_url(settings: ServerSettings, port: int) -> str:
    """서버 기본 주소(`http://<호스트>:<포트>/`)."""
    return f"http://{display_host(settings.host)}:{port}/"


def open_url(settings: ServerSettings, port: int) -> str | None:
    """열 주소: `web.open.url`(`{host}`·`{port}` 치환) → `serve_static`이면 서버 주소 → 없음."""
    configured = settings.web.open.url
    if configured:
        return configured.replace("{host}", display_host(settings.host)).replace(
            "{port}", str(port)
        )
    if settings.web.serve_static:
        return server_url(settings, port)
    return None


def bound_port(server: ServerLike, fallback: int) -> int:
    """실제로 바인딩된 포트(포트 0이면 OS가 고른 값). 알 수 없으면 `fallback`."""
    try:
        for srv in server.servers or ():
            for sock in srv.sockets or ():
                port = sock.getsockname()[1]
                if isinstance(port, int) and port > 0:
                    return port
    except (AttributeError, OSError, IndexError, TypeError):
        pass
    return fallback


def wait_until(
    predicate: Callable[[], bool],
    *,
    timeout: float,
    stop: threading.Event,
    interval: float = 0.05,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """`predicate()`가 참이 될 때까지 기다린다. 시간 초과나 `stop`이면 거짓."""
    deadline = clock() + timeout
    while not predicate():
        if stop.is_set() or clock() >= deadline:
            return False
        stop.wait(interval)
    return True


def announce_when_ready(
    server: ServerLike,
    settings: ServerSettings,
    *,
    opener: Opener | None,
    stop: threading.Event,
    clock: Callable[[], float] = time.monotonic,
    interval: float = 0.05,
) -> str | None:
    """준비되면 준비 줄을 남기고, `opener`가 있으면 URL을 연다(막힘 — 보통 스레드에서 부른다).

    Returns:
        연 URL(열지 않았으면 None).
    """
    if not wait_until(
        lambda: bool(server.started),
        timeout=settings.web.open.wait_seconds,
        stop=stop,
        interval=interval,
        clock=clock,
    ):
        if not stop.is_set():
            _log.warning("준비 신호를 %.0f초 안에 받지 못했습니다", settings.web.open.wait_seconds)
        return None
    port = bound_port(server, settings.port)
    _log.info("준비됨: %s (준비 신호 GET /api/v1/health)", server_url(settings, port))
    if opener is None:
        return None
    url = open_url(settings, port)
    if url is None:
        _log.warning("열 주소가 없습니다: web.serve_static을 켜거나 web.open.url을 지정하세요")
        return None
    try:
        opener(url)
    except Exception as exc:  # 열기 실패는 서버를 멈추지 않는다
        _log.warning("웹 화면을 열지 못했습니다: %s", exc.__class__.__name__)
        return None
    return url


def start_ready_watch(
    server: ServerLike,
    settings: ServerSettings,
    *,
    opener: Opener | None,
    stop: threading.Event,
) -> threading.Thread:
    """`announce_when_ready`를 데몬 스레드로 시작한다(서버가 끝나면 `stop`을 세운다)."""
    thread = threading.Thread(
        target=announce_when_ready,
        args=(server, settings),
        kwargs={"opener": opener, "stop": stop},
        name="agent-console-ready",
        daemon=True,
    )
    thread.start()
    return thread
