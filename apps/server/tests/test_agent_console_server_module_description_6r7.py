"""6R.7(L-18): `GET /modules`의 `ModuleInfo.description`은 모듈 서술자 데이터다.

설치된 모듈마다 사용자 언어 한 줄 설명이 있고, 경로·WS 토픽 같은 개발자용 이름은 담지 않는다.
서버는 모듈 이름을 모르고 서술자 값을 그대로 옮긴다.
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_console_server.testing import API, make_settings, server

_DEVELOPER_TEXT = re.compile(r"/|\bWS\b|CRUD|포트|\w+\.\w+\*?|\{")
"""경로(`/`)·WS 토픽·포트 이름(`a.b`)처럼 사용자에게 보이면 안 되는 표기(예외는 `_ALLOWED`)."""

_ALLOWED = (".claude",)


def test_every_module_reports_user_language_description(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        modules = client.get(f"{API}/modules").json()
    assert modules
    for info in modules:
        text = info.get("description")
        assert isinstance(text, str), info["id"]
        assert text.strip(), info["id"]
        cleaned = text
        for word in _ALLOWED:
            cleaned = cleaned.replace(word, "")
        assert not _DEVELOPER_TEXT.search(cleaned), (info["id"], text)
