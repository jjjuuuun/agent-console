"""4R.22 서버 수준 통합: 예제 로그 출처 설치·제거, 모듈 끄기 매트릭스, 분류 체계 비우기·템플릿 삭제.

서버는 `agent_console_server.testing.server`로 직접 띄운다(포트 없음, 로컬 TestClient).
예제 패키지는 공용 환경에 설치하지 않고 임시 폴더에 `--target`으로 설치해 `sys.path`에만 건다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from agent_console_server.testing import API, make_settings, server

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "extensions" / "agent-console-example-log-source"
LINKS = ("link-logs-runs", "link-logs-trace", "link-logs-usage")
LOG = (
    "2026-10-17T09:00:00Z INFO [worker] 작업 시작\n"
    "2026-10-17T09:00:02Z error 연결 실패\n"
    "2026-10-17T09:00:03Z INFO [worker] 끝\n"
)


def _modules(client: Any) -> dict[str, str]:
    return {m["id"]: m["status"] for m in client.get(f"{API}/modules").json()}


def _install_example(target: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv 없음")
    done = subprocess.run(
        [uv, "pip", "install", "--quiet", "--python", sys.executable, "--target", str(target),
         "--no-deps", str(EXAMPLE)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr


def _source_ids(client: Any) -> set[str]:
    return {s["descriptor"]["id"] for s in client.get(f"{API}/logs/sources").json()}


def test_example_source_install_and_remove_needs_no_code_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """설치하면 /logs/sources·/logs/classifiers에 나타나 수집되고, 제거하면 사라진다."""
    with server(make_settings(tmp_path / "before")) as client:
        before = _source_ids(client)
    assert "example.text_log" not in before
    assert before  # 기본 출처는 있다

    site = tmp_path / "site"
    _install_example(site)
    root = tmp_path / "logs"
    root.mkdir()
    (root / "app.log").write_text(LOG, encoding="utf-8")
    monkeypatch.syspath_prepend(str(site))
    with server(make_settings(tmp_path / "with")) as client:
        assert "example.text_log" in _source_ids(client)
        classifiers = client.get(f"{API}/logs/classifiers").json()
        assert any("example.text_log" in json.dumps(c) for c in classifiers)
        body = {
            "logs": {
                "sources": [
                    {"id": "example.text_log", "enabled": True, "config": {"roots": [str(root)]}}
                ]
            }
        }
        put = client.put(f"{API}/settings", json=body)
        assert put.status_code == 200, put.text
        scan = client.post(f"{API}/logs/scan", json={"source_ids": ["example.text_log"]})
        assert scan.status_code == 202, scan.text
        events: list[dict[str, Any]] = []
        for _ in range(100):
            events = client.get(f"{API}/logs/events").json().get("items", [])
            if len(events) >= 3:
                break
            time.sleep(0.1)
        assert len(events) == 3
        assert {e["category"] for e in events} == {"system", "error"}
    assert (root / "app.log").read_text(encoding="utf-8") == LOG  # 원본 불변

    monkeypatch.undo()
    for name in list(sys.modules):
        if name.startswith("agent_console_example_log_source"):
            del sys.modules[name]
    with server(make_settings(tmp_path / "after")) as client:
        assert "example.text_log" not in _source_ids(client)


def test_mod_logs_alone_and_links_off(tmp_path: Path) -> None:
    """mod-logs만 켜도, 연동 3개만 꺼도 로그 REST는 동작하고 나머지 기능은 정상이다."""
    with server(make_settings(tmp_path / "all")) as client:
        status = _modules(client)
    assert status["mod-logs"] == "active"
    assert all(status.get(link) == "active" for link in LINKS)

    # mod-logs만 켜기(R0.5 기능 독립): 다른 모듈 REST는 404, 로그는 200, health 200
    only = make_settings(tmp_path / "only", modules={"enabled": ["mod-logs"]})
    with server(only) as client:
        assert client.get(f"{API}/health").status_code == 200
        st = _modules(client)
        assert st["mod-logs"] == "active"
        assert [k for k, v in st.items() if v == "active" and k != "mod-logs"] == []
        for path in ("sources", "taxonomy", "dashboard-templates", "schema", "classifiers"):
            assert client.get(f"{API}/logs/{path}").status_code == 200, path
        assert client.get(f"{API}/logs/events").status_code == 200
        assert client.get(f"{API}/runs").status_code == 404

    # 연동 3개 끄기: 기능은 그대로, 연동 경로만 404
    off = make_settings(tmp_path / "off", modules={"disabled": list(LINKS)})
    with server(off) as client:
        st = _modules(client)
        assert all(st[link] == "disabled" for link in LINKS)
        assert st["mod-logs"] == "active"
        assert client.get(f"{API}/logs/sources").status_code == 200
        assert client.get(f"{API}/runs").status_code == 200
        assert client.get(f"{API}/usage").status_code in (200, 404)
        assert client.get(f"{API}/logs/sessions/none/trace").status_code == 404

    # 각 모듈을 하나씩 꺼도 서버가 뜨고 health 200(끄기 매트릭스, 새 모듈 포함)
    for module_id in sorted(status):
        s = make_settings(tmp_path / f"d-{module_id}", modules={"disabled": [module_id]})
        with server(s) as client:
            assert client.get(f"{API}/health").status_code == 200, module_id
            assert _modules(client)[module_id] == "disabled"


def test_empty_taxonomy_and_deleted_templates(tmp_path: Path) -> None:
    """분류 체계를 비우고 대시보드 템플릿 폴더가 비어도(없어도) 동작한다. 분류 체계는 데이터다."""
    empty_dir = tmp_path / "no-templates"
    s = make_settings(
        tmp_path / "ws1", options={"mod-logs": {"dashboard_templates_dir": str(empty_dir)}}
    )
    with server(s) as client:
        assert client.get(f"{API}/logs/dashboard-templates").json() == []
        assert client.get(f"{API}/logs/events").status_code == 200
        assert client.get(f"{API}/logs/taxonomy").status_code == 200
        # 설정으로 범주를 새로 정의해도, 0개 대시보드여도 질의가 동작한다
        body = {"logs": {"taxonomy": {"categories": {"zzz": {"label": "임의"}}}, "dashboards": []}}
        assert client.put(f"{API}/settings", json=body).status_code == 200
        cats = client.get(f"{API}/logs/taxonomy").json()["categories"]
        assert "zzz" in cats
        agg = client.post(
            f"{API}/logs/aggregate", json={"dimensions": ["category"], "metric": "count"}
        )
        assert agg.status_code in (200, 422), agg.text
        assert agg.status_code != 500
