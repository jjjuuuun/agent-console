"""서버 앱(`agent_console_server`)과 닿는 유일한 모듈.

`serve`는 서버의 `load_settings`·`serve`를 부르기만 하고, `statusline`은 같은 설정 규칙
(설정 파일 + `AGENT_CONSOLE_*` 환경변수)으로 workspace 기록 폴더를 얻는다. 서버 패키지는 필요할 때만
import한다(`statusline` 시작을 가볍게, import-linter는 이 모듈만 예외로 둔다).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

APPLY_PRESET_FLAG = "apply-preset"
"""`serve --apply-preset`가 넘기는 서버 모듈 명령행 옵션 이름(그 옵션을 선언한 모듈이 받는다)."""


class ServerConfigError(Exception):
    """서버 설정을 읽지 못했다(메시지에 설정 값은 넣지 않는다)."""


def serve_overrides(
    *,
    host: str | None,
    port: int | None,
    workspace: str | None,
    apply_presets: Sequence[str] | None,
    open_browser: bool | None = None,
) -> dict[str, Any]:
    """명령행 옵션 → `load_settings(overrides=…)`(서버 `main`과 같은 의미).

    `open_browser`가 None이면 설정(`web.open.enabled`)을 그대로 둔다. `apply_presets`는 그 명령행
    옵션(`apply-preset`)을 선언한 서버 모듈의 설정으로 넣는다(서버 `flag_overrides`, 3R.16 — 어느
    모듈인지는 모듈이 `SettingsCompat.flags`로 알린다).

    Raises:
        ServerConfigError: `apply_presets`를 줬는데 그 옵션을 선언한 모듈이 설치되어 있지 않을 때.
    """
    overrides: dict[str, Any] = {}
    for key, value in (("host", host), ("port", port), ("workspace", workspace)):
        if value is not None:
            overrides[key] = value
    if apply_presets:
        from agent_console_server import ConfigError, flag_overrides

        try:
            overrides.update(flag_overrides({APPLY_PRESET_FLAG: list(apply_presets)}))
        except ConfigError as exc:
            raise ServerConfigError(str(exc)) from None
    if open_browser is not None:
        overrides["web"] = {"open": {"enabled": open_browser}}
    return overrides


def merge_origins(configured: Iterable[str], extra: Iterable[str]) -> list[str]:
    """설정의 허용 출처 뒤에 `extra`를 덧붙인다(순서 유지, 중복·빈 값 제거, 끝의 `/` 무시).

    Args:
        configured: 설정 파일·환경변수에서 읽은 `security.allowed_origins`.
        extra: 명령행 `--allow-origin` 값.

    Returns:
        합친 목록. 비교는 끝의 `/`를 뗀 문자열로 한다(출처에는 경로가 없다).
    """
    merged: list[str] = []
    seen: set[str] = set()
    for origin in (*configured, *extra):
        value = origin.strip().rstrip("/")
        if value and value not in seen:
            seen.add(value)
            merged.append(value)
    return merged


def run_server(
    config: Path | None,
    overrides: Mapping[str, Any],
    *,
    extra_origins: Sequence[str] = (),
    enable_modules: Sequence[str] = (),
    disable_modules: Sequence[str] = (),
) -> None:
    """설정을 읽어 서버를 실행한다(막힘, Ctrl-C로 정상 종료).

    Args:
        config: 설정 파일(None이면 서버 규칙대로 찾음).
        overrides: 명령행 값(`serve_overrides`).
        extra_origins: 설정의 허용 출처에 덧붙일 출처(`merge_origins`).
        enable_modules: 켤 서버 모듈 id(`--enable-module`, 설정 `modules`보다 우선).
        disable_modules: 끌 서버 모듈 id(`--disable-module`, 같은 id면 끄기가 이김).

    Raises:
        ServerConfigError: 설정 오류.
    """
    from agent_console_server import ConfigError, apply_module_flags, load_settings, serve

    try:
        settings = load_settings(config, overrides=overrides)
        if extra_origins:
            origins = merge_origins(settings.security.allowed_origins, extra_origins)
            security = {**overrides.get("security", {}), "allowed_origins": origins}
            settings = load_settings(config, overrides={**overrides, "security": security})
        serve(apply_module_flags(settings, enable=enable_modules, disable=disable_modules))
    except ConfigError as exc:
        raise ServerConfigError(str(exc)) from None


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
