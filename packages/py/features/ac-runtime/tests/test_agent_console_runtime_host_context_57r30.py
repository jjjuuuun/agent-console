"""5.7R.30: 백엔드 설정 훅의 선택 키워드 `host`(`BackendHostContext`)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agent_console_runtime import BACKEND_HOST_PARAM, BackendHostContext, accepts_host_context


def _old(options: Mapping[str, Any], *, secrets: Any, environ: Mapping[str, str]) -> None: ...


def _new(
    options: Mapping[str, Any],
    *,
    secrets: Any,
    environ: Mapping[str, str],
    host: BackendHostContext | None = None,
) -> None: ...


def _kwargs(options: Mapping[str, Any], **kw: Any) -> None: ...


def test_accepts_host_context() -> None:
    assert BACKEND_HOST_PARAM == "host"
    assert not accepts_host_context(_old)
    assert accepts_host_context(_new)
    assert accepts_host_context(_kwargs)
    assert not accepts_host_context(len)  # 서명을 읽을 수 없는 내장 함수도 거짓


def test_host_context_defaults() -> None:
    assert BackendHostContext().workspace_dir is None
    assert BackendHostContext(workspace_dir=Path("/ws")).workspace_dir == Path("/ws")
