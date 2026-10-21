"""`GET /server-info`(호스트 경로, design §3R.1.3): 서버·계약 버전, 플러그인 로딩 보고, 속성, 경고.

모듈은 포트로 기여한다(이름으로만 맞춘다): `server.warnings`(경고 — 평문 비밀 점검, 팀 규칙 없음
등)·`server.attributes`(속성 — 복구한 Run 수 등)·`secrets.redact`(플러그인 오류 메시지 가리기).
제공자 오류는 기록하고 건너뛴다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from agent_console_contracts import CONTRACTS_VERSION, ErrorInfo, Issue, PluginInfo, ServerInfo
from agent_console_modkit import Assembly
from agent_console_registry import LoadReport

from ._config import SETTINGS_MOVED_KEY, ServerSettings
from ._ports import SECRET_REDACT, SERVER_ATTRIBUTES, SERVER_WARNINGS

_log = logging.getLogger("agent_console_server")


def moved_key_issues(settings: ServerSettings) -> list[Issue]:
    """옛 위치에서 옮긴 설정 키 → 경고 이슈(`settings.moved_key`, details `{old, new}`)."""
    return [
        Issue(
            severity="warning",
            code=SETTINGS_MOVED_KEY,
            message=m.message(),
            details={"old": m.old, "new": m.new, "overridden": list(m.overridden)},
        )
        for m in settings.moved_keys
    ]


def plugin_infos(
    reports: Sequence[tuple[str, LoadReport]], redact: Callable[[str], str]
) -> list[PluginInfo]:
    infos: list[PluginInfo] = []
    for group, report in reports:
        error = (
            ErrorInfo(code="plugin_load_failed", message=redact(report.error or ""))
            if not report.ok
            else None
        )
        infos.append(
            PluginInfo(
                name=report.key or report.source,
                group=group,
                loaded=report.status == "loaded",
                status=report.status,
                error=error,
            )
        )
    return infos


def redactor(assembly: Assembly) -> Callable[[str], str]:
    """`secrets.redact` 포트(없으면 그대로)."""

    def redact(text: str) -> str:
        port = assembly.port(SECRET_REDACT)
        return str(port(text)) if port is not None else text

    return redact


def server_info(
    settings: ServerSettings,
    *,
    server_version: str,
    reports: Sequence[tuple[str, LoadReport]],
    assembly: Assembly,
) -> ServerInfo:
    """`ServerInfo`(읽기 전용, 비밀 값 없음).

    `security.expose_paths`가 꺼지면 workspace 경로를 뺀다.
    """
    attributes: dict[str, Any] = {
        "host": settings.host,
        "port": settings.port,
        "allow_remote": settings.security.allow_remote,
        "allowed_origins": list(settings.security.allowed_origins),
        "serve_static": settings.web.serve_static,
    }
    for source in assembly.ports(SERVER_ATTRIBUTES):
        try:
            attributes.update(source())
        except Exception:
            _log.exception("서버 속성 제공자 실패")
    if settings.security.expose_paths:
        attributes["workspace"] = str(settings.workspace_path)
    warnings: list[Issue] = []
    for warning_source in assembly.ports(SERVER_WARNINGS):
        try:
            warnings.extend(warning_source())
        except Exception:
            _log.exception("서버 경고 제공자 실패")
    return ServerInfo(
        server_version=server_version,
        contracts_version=CONTRACTS_VERSION,
        plugins=plugin_infos(reports, redactor(assembly)),
        attributes=attributes,
        warnings=[*warnings, *moved_key_issues(settings)],
    )


__all__ = ["moved_key_issues", "plugin_infos", "redactor", "server_info"]
