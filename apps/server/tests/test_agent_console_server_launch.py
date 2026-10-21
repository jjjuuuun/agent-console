"""2R.23 단일 실행 보강: 준비 신호 `/health`, `web.open`(준비되면 열기), 정적 서빙 선택 기능.

브라우저는 실제로 열지 않는다 — 열기 함수·명령 실행은 모두 가짜를 주입한다.
"""

from __future__ import annotations

import threading
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import uvicorn

import agent_console_server._app as server_app
from agent_console_contracts import CONTRACTS_VERSION, HealthResponse
from agent_console_server import ServerSettings, build_opener, load_settings, main
from agent_console_server._launch import (
    announce_when_ready,
    display_host,
    open_url,
    wait_until,
)
from agent_console_server.testing import TEST_TOKEN, make_settings, server

# ---------------------------------------------------------------- /health


def test_health_is_public_and_matches_contract(tmp_path: Path) -> None:
    with server(make_settings(tmp_path), with_token=False) as client:
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        body = HealthResponse.model_validate(res.json())
        assert body.status == "ok"
        assert body.contracts_version == CONTRACTS_VERSION
        assert TEST_TOKEN not in res.text
        schema = client.get("/api/v1/openapi.json").json()
        assert "/api/v1/health" in schema["paths"]


def test_health_not_shadowed_by_static_serving(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    settings = make_settings(tmp_path, web={"serve_static": True, "static_dir": "dist"})
    with server(settings, with_token=False) as client:
        assert client.get("/api/v1/health").json()["status"] == "ok"
        assert "<title>app</title>" in client.get("/").text


# ---------------------------------------------------------------- 설정


def test_web_open_defaults_off_and_env_flags(tmp_path: Path) -> None:
    default = load_settings(environ={}, cwd=tmp_path)
    assert default.web.serve_static is False
    assert default.web.open.enabled is False
    assert default.web.open.url is None
    assert default.web.open.command is None
    env = {
        "AGENT_CONSOLE_SERVE_STATIC": "1",
        "AGENT_CONSOLE_OPEN": "true",
        "AGENT_CONSOLE_WEB_DIR": "apps/web/dist",
    }
    cfg = load_settings(environ=env, cwd=tmp_path)
    assert cfg.web.serve_static is True
    assert cfg.web.open.enabled is True
    assert cfg.static_path == tmp_path.resolve() / "apps/web/dist"
    off = load_settings(environ={"AGENT_CONSOLE_OPEN": "no"}, cwd=tmp_path)
    assert off.web.open.enabled is False


def test_web_open_from_config_file(tmp_path: Path) -> None:
    (tmp_path / "agent-console.yaml").write_text(
        "web:\n  serve_static: true\n  open:\n    enabled: true\n"
        "    command: [msedge, '--app={url}']\n    wait_seconds: 5\n",
        encoding="utf-8",
    )
    cfg = load_settings(environ={}, cwd=tmp_path)
    assert cfg.web.open.command == ["msedge", "--app={url}"]
    assert cfg.web.open.wait_seconds == 5


# ---------------------------------------------------------------- 열기 함수·주소


def test_build_opener_uses_injected_browser_or_command() -> None:
    opened: list[str] = []
    spawned: list[list[str]] = []
    settings = ServerSettings().web.open
    build_opener(settings, browser=opened.append)("http://localhost:1/")
    assert opened == ["http://localhost:1/"]

    def spawn(args: Sequence[str]) -> None:
        spawned.append(list(args))

    with_command = settings.model_copy(update={"command": ["app", "--app={url}", "x"]})
    build_opener(with_command, browser=opened.append, spawn=spawn)("http://localhost:2/")
    assert spawned == [["app", "--app=http://localhost:2/", "x"]]
    assert opened == ["http://localhost:1/"]  # 명령이 있으면 브라우저는 쓰지 않는다


@pytest.mark.parametrize(
    ("host", "shown"),
    [
        ("127.0.0.1", "localhost"),
        ("::1", "localhost"),
        ("0.0.0.0", "localhost"),
        ("::", "localhost"),
        ("example.lan", "example.lan"),
        ("fd00::1", "[fd00::1]"),
    ],
)
def test_display_host(host: str, shown: str) -> None:
    assert display_host(host) == shown


def test_open_url_rules(tmp_path: Path) -> None:
    base = make_settings(tmp_path)
    assert open_url(base, 9000) is None  # 정적 서빙 꺼짐 + 주소 없음 → 열지 않음
    static = make_settings(tmp_path, web={"serve_static": True})
    assert open_url(static, 9000) == "http://localhost:9000/"
    custom = make_settings(tmp_path, web={"open": {"url": "http://{host}:5173/?api={port}"}})
    assert open_url(custom, 9001) == "http://localhost:5173/?api=9001"


# ---------------------------------------------------------------- 준비되면 열기


class _FakeServer:
    def __init__(self) -> None:
        self.started = False
        self.servers: list[Any] = []


def test_wait_until_stops_on_timeout_and_stop() -> None:
    now = [0.0]

    def clock() -> float:
        now[0] += 1.0
        return now[0]

    stop = threading.Event()
    assert wait_until(lambda: False, timeout=3, stop=stop, interval=0, clock=clock) is False
    stop.set()
    assert wait_until(lambda: False, timeout=1e9, stop=stop, interval=0) is False
    assert wait_until(lambda: True, timeout=0.001, stop=threading.Event()) is True


def test_announce_opens_after_ready(tmp_path: Path) -> None:
    fake = _FakeServer()
    opened: list[str] = []
    settings = make_settings(tmp_path, port=9100, web={"serve_static": True})
    result: list[str | None] = []
    stop = threading.Event()
    thread = threading.Thread(
        target=lambda: result.append(
            announce_when_ready(fake, settings, opener=opened.append, stop=stop, interval=0.01)
        )
    )
    thread.start()
    assert opened == []  # 준비 전에는 열지 않는다
    fake.started = True
    thread.join(5)
    assert opened == ["http://localhost:9100/"]
    assert result == ["http://localhost:9100/"]


def test_announce_skips_when_no_url_or_opener_fails(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fake = _FakeServer()
    fake.started = True
    stop = threading.Event()
    opened: list[str] = []
    no_url = make_settings(tmp_path)
    assert announce_when_ready(fake, no_url, opener=opened.append, stop=stop) is None
    assert opened == []
    assert "web.open.url" in caplog.text

    def broken(url: str) -> None:
        raise OSError("no browser")

    static = make_settings(tmp_path, web={"serve_static": True})
    assert announce_when_ready(fake, static, opener=broken, stop=stop) is None
    assert "웹 화면을 열지 못했습니다" in caplog.text
    assert announce_when_ready(fake, static, opener=None, stop=stop) is None  # 준비 줄만


def test_announce_gives_up_when_server_stops(tmp_path: Path) -> None:
    fake = _FakeServer()
    stop = threading.Event()
    stop.set()
    opened: list[str] = []
    settings = make_settings(tmp_path, web={"serve_static": True})
    assert announce_when_ready(fake, settings, opener=opened.append, stop=stop) is None
    assert opened == []


# ---------------------------------------------------------------- 실제 uvicorn(포트 0)


@contextmanager
def _capture_uvicorn(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[uvicorn.Server]]:
    created: list[uvicorn.Server] = []

    class Recording(uvicorn.Server):
        def __init__(self, config: uvicorn.Config) -> None:
            super().__init__(config)
            created.append(self)

    monkeypatch.setattr(uvicorn, "Server", Recording)
    yield created


def test_serve_single_process_opens_real_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`serve()`가 포트 0으로 떠서 준비되면 주입한 열기 함수에 실제 주소를 넘긴다."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>one</title>", encoding="utf-8")
    settings = make_settings(
        tmp_path,
        port=0,
        log_level="warning",
        web={"serve_static": True, "static_dir": "dist", "open": {"enabled": True}},
    )
    opened: list[str] = []
    fetched: dict[str, str] = {}
    with _capture_uvicorn(monkeypatch) as created:

        def opener(url: str) -> None:
            opened.append(url)
            with urllib.request.urlopen(url + "api/v1/health", timeout=5) as res:
                fetched["health"] = res.read().decode()
            with urllib.request.urlopen(url, timeout=5) as res:
                fetched["page"] = res.read().decode()
            created[0].should_exit = True

        thread = threading.Thread(
            target=server_app.serve, args=(settings,), kwargs={"environ": {}, "opener": opener}
        )
        thread.start()
        thread.join(60)
    assert not thread.is_alive()
    assert len(opened) == 1
    assert opened[0].startswith("http://localhost:")
    assert not opened[0].endswith(":0/")
    assert '"status":"ok"' in fetched["health"]
    assert "<title>one</title>" in fetched["page"]


def test_serve_does_not_open_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`web.open.enabled`가 꺼져 있으면 주입한 열기 함수도 부르지 않는다(기본값)."""
    settings = make_settings(tmp_path, port=0, log_level="warning", web={"serve_static": True})
    opened: list[str] = []
    with _capture_uvicorn(monkeypatch) as created:
        thread = threading.Thread(
            target=server_app.serve,
            args=(settings,),
            kwargs={"environ": {}, "opener": opened.append},
        )
        thread.start()
        never = threading.Event()
        assert wait_until(lambda: bool(created) and created[0].started, timeout=30, stop=never)
        created[0].should_exit = True
        thread.join(30)
    assert not thread.is_alive()
    assert opened == []


def test_server_main_open_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[ServerSettings] = []
    monkeypatch.setattr(server_app, "serve", seen.append)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENT_CONSOLE_CONFIG", raising=False)
    monkeypatch.delenv("AGENT_CONSOLE_OPEN", raising=False)
    assert main(["--open"]) == 0
    assert main(["--no-open"]) == 0
    assert main([]) == 0
    assert [s.web.open.enabled for s in seen] == [True, False, False]
