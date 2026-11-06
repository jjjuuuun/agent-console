"""통합 서버(agent-console-server — 기본 모듈 전부) + 이 모듈 조립 시험.

설치 대신 ``create_app(modules=[*installed_modules(), module])``로 이 모듈을 더한다(설치한 서버가
entry point로 모듈을 모으는 일과 같다). 명령행 옵션은 서버 ``main``이 모듈 선언에서 만든다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_example_module import module
from agent_console_modkit import Module
from agent_console_server import (
    create_app,
    flag_overrides,
    installed_modules,
    load_settings,
    main,
    settings_compat,
)
from agent_console_server.testing import register_project

API = "/api/v1"
TOKEN = "test-token-0123456789abcdef"


def _modules() -> list[Module]:
    return [m for m in installed_modules() if m.descriptor.id != module.descriptor.id] + [module]


@contextmanager
def _server(
    tmp_path: Path,
    *,
    flags: Mapping[str, Any] | None = None,
    disabled: Sequence[str] = (),
) -> Iterator[TestClient]:
    mods = _modules()
    compat = settings_compat(mods)
    overrides: dict[str, Any] = {
        "security": {"allowed_hosts": ["testserver"]},
        "modules": {"disabled": list(disabled)},
    }
    overrides.update(flag_overrides(dict(flags or {}), compat))
    config = tmp_path / "agent-console.yaml"
    config.write_text("workspace: ws\n", encoding="utf-8")
    environ = {"CLAUDE_CONFIG_DIR": str(tmp_path / "claude")}  # 실제 ~/.claude를 읽지 않게
    settings = load_settings(config, environ=environ, overrides=overrides, compat=compat)
    app = create_app(settings, environ=environ, token=TOKEN, modules=mods)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


@pytest.fixture(autouse=True)
def _no_real_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_full_server_flag_kind_user_section_and_project(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    _write(ws / "settings.yaml", "example_notes:\n  newest_first: false\n")
    _write(
        ws / "example-note-templates" / "greet.yaml",
        "kind: example-note-template\nid: greet\nname: 인사\ncategory: 일상\ntext: 안녕\n"
        "tags: [인사]\n",
    )
    with _server(tmp_path, flags={"example-notes-max": "2"}) as client:
        mods = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert mods["mod-example-notes"]["status"] == "active"
        options = client.get(f"{API}/modules/mod-example-notes/options")
        assert options.status_code == 200  # 설정 화면이 읽는 옵션(명령행 값이 들어감)
        assert options.json()["values"]["max_notes"] == 2

        # 정의 종류 기여 → 정의 모듈이 등록한 종류의 문서를 틀로 쓴다(definitions.lookup)
        made = client.post(f"{API}/example-notes", json={"template": "greet"})
        assert made.status_code == 201, made.text
        assert (made.json()["text"], made.json()["tags"]) == ("안녕", ["인사"])
        for word in ("b", "c"):
            assert client.post(f"{API}/example-notes", json={"text": word}).status_code == 201
        listed = [n["text"] for n in client.get(f"{API}/example-notes").json()]
        assert listed == ["b", "c"]  # --example-notes-max 2, 사용자 설정 newest_first: false

        # 계보 scopes에 "project" → 프로젝트 기록 DB에 같은 표가 생기고 노트가 그쪽에 간다
        folder = tmp_path / "proj"
        folder.mkdir()
        register_project(client, "p1", folder)
        assert client.get(f"{API}/example-notes?project=p1").json() == []
        added = client.post(f"{API}/example-notes?project=p1", json={"text": "프로젝트 노트"})
        assert added.status_code == 201, added.text
        assert [n["text"] for n in client.get(f"{API}/example-notes?project=p1").json()] == [
            "프로젝트 노트"
        ]
        assert "프로젝트 노트" not in [n["text"] for n in client.get(f"{API}/example-notes").json()]
    records = list(folder.rglob("records.sqlite3"))
    assert records, "프로젝트 기록 DB가 없습니다"
    with sqlite3.connect(records[0]) as conn:
        rows = conn.execute("SELECT text FROM example_notes").fetchall()
    assert rows == [("프로젝트 노트",)]


def test_disabled_module_404_and_rest_ok(tmp_path: Path) -> None:
    with _server(tmp_path, disabled=["mod-example-notes"]) as client:
        assert client.get(f"{API}/example-notes").status_code == 404
        assert client.get(f"{API}/health").status_code == 200
        assert client.get(f"{API}/agents").status_code == 200
        mods = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert mods["mod-example-notes"]["status"] == "disabled"
        assert mods["mod-definitions"]["status"] == "active"


def test_serve_help_shows_module_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--help"], prog="agent-console serve", modules=_modules())
    assert info.value.code == 0
    out = capsys.readouterr().out
    assert "--example-notes-max" in out
    assert "mod-example-notes" in out


def test_uninstalled_module_options_do_not_block_start(tmp_path: Path) -> None:
    """제거 뒤 설정에 이 모듈 옵션이 남아도 서버는 시작한다(나머지 정상)."""
    mods = [m for m in _modules() if m.descriptor.id != module.descriptor.id]
    compat = settings_compat(mods)
    overrides: dict[str, Any] = {
        "security": {"allowed_hosts": ["testserver"]},
        "modules": {"options": {"mod-example-notes": {"max_notes": 5}}},
    }
    config = tmp_path / "agent-console.yaml"
    config.write_text("workspace: ws\n", encoding="utf-8")
    environ = {"CLAUDE_CONFIG_DIR": str(tmp_path / "claude")}
    settings = load_settings(config, environ=environ, overrides=overrides, compat=compat)
    app = create_app(settings, environ=environ, token=TOKEN, modules=mods)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        assert client.get(f"{API}/health").status_code == 200
        assert client.get(f"{API}/example-notes").status_code == 404
    assert any("mod-example-notes" in w for w in app.state.assembly.warnings)
