"""웹 빌드 산출물 정적 서빙(SPA)과 빌드가 없을 때의 안내 페이지."""

from __future__ import annotations

from pathlib import Path

from agent_console_server.testing import make_settings, server


def test_agent_console_server_static_missing_build(tmp_path: Path) -> None:
    with server(
        make_settings(tmp_path, web={"serve_static": True, "static_dir": str(tmp_path / "nope")})
    ) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "pnpm --filter @agent-console/web build" in page.text
        assert '<meta charset="UTF-8">' in page.text
        assert client.get("/graphs/flow").status_code == 200  # 같은 안내
        api = client.get("/api/v2/whatever")
        assert api.status_code == 404
        assert api.json()["error"]["code"] == "not_found"


def test_agent_console_server_static_serves_build(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    with server(
        make_settings(tmp_path, web={"serve_static": True, "static_dir": "dist"})
    ) as client:
        assert "<title>app</title>" in client.get("/").text
        assert client.get("/assets/app.js").text == "console.log(1)"
        assert "<title>app</title>" in client.get("/graphs/flow/edit").text  # 클라이언트 라우팅
        assert "outside" not in client.get("/../secret.txt").text
        assert "outside" not in client.get("/assets/..%2F..%2Fsecret.txt").text
        # 예약 경로는 첫 조각이 정확히 `api`/`ws`일 때만(phase2r-review D10)
        for web_path in ("/wsfoo", "/ws-guide", "/apifoo", "/graphs/ws"):
            res = client.get(web_path)
            assert res.status_code == 200, web_path
            assert "<title>app</title>" in res.text, web_path
        for reserved in ("/ws/x", "/api", "/api/v9/none"):
            res = client.get(reserved)
            assert res.status_code == 404, reserved
            assert res.json()["error"]["code"] == "not_found", reserved


def test_agent_console_server_static_reserved_path_rule() -> None:
    from agent_console_server._static import is_reserved_path

    assert is_reserved_path("ws")
    assert is_reserved_path("ws/")
    assert is_reserved_path("ws/sub")
    assert is_reserved_path("api/v1/health")
    assert not is_reserved_path("wsfoo")
    assert not is_reserved_path("")
    assert not is_reserved_path("graphs/ws")


def test_agent_console_server_static_off_by_default(tmp_path: Path) -> None:
    """정적 서빙은 보류 기능이라 기본 꺼짐(design §R7): 웹 경로는 JSON 404, API는 그대로."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    with server(make_settings(tmp_path, web={"static_dir": "dist"})) as client:
        page = client.get("/")
        assert page.status_code == 404
        assert page.json()["error"]["code"] == "not_found"
        assert client.get("/api/v1/node-types").status_code == 200


def test_qa_3r30_reserved_json_404(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    with server(make_settings(tmp_path, web={"serve_static": True, "static_dir": "dist"})) as c:
        for p in ("/ws/x", "/api", "/api/v9/none", "/ws/"):
            r = c.get(p)
            assert r.status_code == 404, p
            assert r.json()["error"]["code"] == "not_found", p
        for p in ("/wsfoo", "/ws-guide", "/apifoo", "/graphs/ws", "/api2/x"):
            assert "<title>app</title>" in c.get(p).text, p
