"""예제 확장: 모델 없이 규칙 데이터로 답하는 대본 실행 백엔드 ``example.scripted``.

entry point ``agent_console.backends``의 ``example.scripted`` = ``ScriptedBackend``.
"""

from __future__ import annotations

from ._backend import (
    BACKEND_ID,
    SESSION_MISSING_CODE,
    SESSION_SUFFIX,
    InstallOptions,
    ScriptedBackend,
    ScriptOptions,
    ScriptRule,
    render,
    scripted_session_archive,
    session_key,
)

__all__ = [
    "BACKEND_ID",
    "SESSION_MISSING_CODE",
    "SESSION_SUFFIX",
    "InstallOptions",
    "ScriptOptions",
    "ScriptRule",
    "ScriptedBackend",
    "render",
    "scripted_session_archive",
    "session_key",
]
