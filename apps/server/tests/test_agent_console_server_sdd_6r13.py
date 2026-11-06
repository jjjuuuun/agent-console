"""6R.13: 통합 서버에 `mod-sdd`가 붙는다 — `GET /modules`의 `label_display`(설치자 접두를 바꾸면
키도 바뀜, §6R.18 Q10), 빈 workspace에서 틀 0·스펙 0, 정의 모듈이 있으면
`capabilities.templates`, 모듈을 끄면 경로 404·표시 규칙 없음. 서버는 모듈 이름을 모르고
build 결과를 옮긴다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server

MODULE = "mod-sdd"


def _info(modules: list[dict[str, Any]]) -> dict[str, Any]:
    return next(m for m in modules if m["id"] == MODULE)


def test_label_display_follows_installer_prefix(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        info = _info(client.get(f"{API}/modules").json())
        assert info["status"] == "active"
        assert "sdd" in info["web_roles"]
        assert [d["key"] for d in info["label_display"]][:2] == ["sdd.spec", "sdd.task"]
        sdd = client.get(f"{API}/sdd/info").json()
        assert sdd["label_display"] == info["label_display"]
        assert sdd["capabilities"]["templates"] is True  # 정의 모듈(라이브러리)이 있다
        assert client.get(f"{API}/sdd/templates").json() == []
        assert client.get(f"{API}/sdd/specs").json() == []
    options = {MODULE: {"run_label_prefix": "plan/"}}
    with server(make_settings(tmp_path / "p", options=options)) as client:
        info = _info(client.get(f"{API}/modules").json())
        keys = [d["key"] for d in info["label_display"]]
        assert keys
        assert all(k.startswith("plan/") for k in keys)
        assert all(not k.startswith("sdd.") for k in keys)


def test_disabled_sdd_module_has_no_routes(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, modules={"disabled": [MODULE]})
    with server(settings) as client:
        info = _info(client.get(f"{API}/modules").json())
        assert info["status"] == "disabled"
        assert info["label_display"] == []
        assert client.get(f"{API}/sdd/info").status_code == 404
        assert client.get(f"{API}/sdd/specs").status_code == 404
