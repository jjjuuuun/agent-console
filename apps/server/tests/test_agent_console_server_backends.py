"""백엔드 설치자 설정(통합): 설치된 백엔드 플러그인이 설정 값을 훅으로 받는다(새 위치
`modules.options.mod-runs.backends`, 옛 최상위 `backends`는 옮겨 읽는다)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_console_server.testing import API, make_settings, server


def test_agent_console_server_backend_options_from_settings(tmp_path: Path) -> None:
    """설치된 백엔드 플러그인(fake)이 설정 `backends.fake-agent`를 훅으로 받는다."""
    settings = make_settings(
        tmp_path,
        options={"mod-runs": {"backends": {"fake-agent": {"models": [{"id": "fake-small"}]}}}},
    )
    with server(settings) as client:
        models = client.get(f"{API}/backends/fake-agent/models").json()
    assert [m["id"] for m in models] == ["fake-small"]


def test_agent_console_server_bad_backend_options_fail_start(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path, options={"mod-runs": {"backends": {"fake-agent": {"nope": "value-xyz"}}}}
    )
    with pytest.raises(ValueError, match=r"backends\.fake") as exc, server(settings):
        pass
    assert "value-xyz" not in str(exc.value)
