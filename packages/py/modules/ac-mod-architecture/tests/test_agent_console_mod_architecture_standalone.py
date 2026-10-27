"""단독 실행(``python -m agent_console_mod_architecture``, ``--with`` 없이).

``--with``를 주지 않으면 ``local-settings``(워크스페이스 ``settings.yaml``)가 붙는다.
사용자 프로필을 그 파일의 ``architecture`` 섹션에 적고 목록·단독 투영을 부른다.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_mod_architecture.standalone import main
from agent_console_modkit.host import HostSettings

TOKEN = "s" * 32


def _layout(tmp_path: Path, flow: dict[str, Any]) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    # JSON은 YAML이기도 하다(설정 파일 형식 그대로 읽힌다)
    # 패키지 기본 프로필(5.5R.8)도 함께 보이므로 먼저 열 프로필을 정한다
    document = {"architecture": {"profiles": {"flow": flow}, "default_profile": "flow"}}
    (workspace / "settings.yaml").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )
    config = tmp_path / "standalone.json"
    config.write_text(
        json.dumps(
            {
                "port": 0,
                "workspace": "ws",
                "state": "state",
                "security": {"token": TOKEN},
                "modules": {"options": {"mod-architecture": {"max_request_events": 10}}},
            }
        ),
        encoding="utf-8",
    )
    return config


def test_standalone_without_with_reads_workspace_settings(
    tmp_path: Path, flow: dict[str, Any], event_rows: list[dict[str, Any]]
) -> None:
    config = _layout(tmp_path, flow)
    seen: dict[str, Any] = {}

    def serve(app: Any, settings: HostSettings) -> None:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            client.headers["X-Console-Token"] = TOKEN
            seen["modules"] = [(m["id"], m["state"]) for m in client.get("/api/v1/modules").json()]
            seen["list"] = client.get("/api/v1/architecture/profiles").json()
            seen["view"] = client.post(
                "/api/v1/architecture/project", json={"events": event_rows}
            ).json()

    out = io.StringIO()
    code = main(["--config", str(config)], serve=serve, out=out, environ={})
    assert code == 0, out.getvalue()
    assert ("mod-architecture", "active") in seen["modules"]
    assert ("local-settings", "active") in seen["modules"]
    assert [p["id"] for p in seen["list"]["profiles"] if p["origin"] == "user"] == ["flow"]
    assert [p["id"] for p in seen["list"]["profiles"] if p["origin"] == "default"] == [
        "agent-architecture"
    ]
    assert seen["view"]["profile"] == "flow"
    assert seen["view"]["event_total"] == 4
