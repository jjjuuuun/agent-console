"""서버 앱(`agent_console_server`)과 닿는 유일한 모듈.

`serve`는 인자를 서버 `main`에 그대로 넘기고, `statusline`은 서버와 같은 설정 규칙
(설정 파일 + `AGENT_CONSOLE_*` 환경변수)으로 workspace 기록 폴더를 얻는다. 서버 패키지는 필요할 때만
import한다(`statusline` 시작을 가볍게, import-linter는 이 모듈만 예외로 둔다).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path


class ServerConfigError(Exception):
    """서버 설정을 읽지 못했다(메시지에 설정 값은 넣지 않는다)."""


def run_serve(argv: Sequence[str], *, prog: str) -> int:
    """서버 명령행(`agent_console_server.main`)을 실행한다(막힘, Ctrl-C로 정상 종료).

    옵션 정의·해석은 서버 한 곳에 있다(모듈이 선언한 옵션 포함).

    Args:
        argv: `serve` 뒤의 인자 그대로.
        prog: 도움말·오류 줄에 쓸 명령 이름.

    Returns:
        서버 `main`의 종료 코드. 옵션 오류·`--help`는 `SystemExit`로 올라간다.
    """
    import agent_console_server

    return agent_console_server.main(list(argv), prog=prog)


def server_state_dir(config: Path | None, environ: Mapping[str, str] | None = None) -> Path:
    """서버 설정(파일 + 환경변수)의 workspace 시스템 기록 폴더(`<workspace>/.state`).

    Raises:
        ServerConfigError: 설정 오류.
    """
    from agent_console_server import ConfigError, load_settings

    try:
        settings = load_settings(config, environ=environ)
    except ConfigError as exc:
        raise ServerConfigError(str(exc)) from None
    return settings.state_path
