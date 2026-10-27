"""로그인 서비스가 꺼졌을 때 응답에서 로그인 흔적을 걷어 내기(ux-overhaul §15.9, F14 수용 1).

설치자 설정 ``mod-runs.backend_login.enabled=false``이면 로그인·로그아웃 경로가 없다. 백엔드는 이
설정을 모르므로 디스크립터(``capabilities.login/logout``·``login_methods``)와 준비 상태
(``actions``의 로그인 동작)를 그대로 낸다. 화면이 없는 경로로 가는 버튼을 그리지 않도록 모듈이
응답을 내보내기 전에 걷어 낸다. 모듈은 동작 종류 이름만 알고 백엔드 id·상태 이름은 모른다.
"""

from __future__ import annotations

from collections.abc import Collection

from agent_console_contracts import BackendDescriptor, BackendReadiness

LOGIN_ACTION_KINDS: frozenset[str] = frozenset({"login", "logout"})
"""로그인 서비스가 처리하는 준비 상태 동작 종류(``ReadinessAction.kind``)."""


def descriptor_without_login(descriptor: BackendDescriptor) -> BackendDescriptor:
    """``capabilities.login/logout``을 거짓으로, ``login_methods``를 비운 사본(원본은 그대로)."""
    caps = descriptor.capabilities
    if not caps.login and not caps.logout and not descriptor.login_methods:
        return descriptor
    return descriptor.model_copy(
        update={
            "capabilities": caps.model_copy(update={"login": False, "logout": False}),
            "login_methods": [],
        }
    )


def readiness_without_login(
    readiness: BackendReadiness, kinds: Collection[str] = LOGIN_ACTION_KINDS
) -> BackendReadiness:
    """``actions``에서 로그인 서비스가 처리하는 종류(기본 ``login``·``logout``)를 뺀 사본."""
    kept = [a for a in readiness.actions if a.kind not in kinds]
    if len(kept) == len(readiness.actions):
        return readiness
    return readiness.model_copy(update={"actions": kept})


__all__ = ["LOGIN_ACTION_KINDS", "descriptor_without_login", "readiness_without_login"]
