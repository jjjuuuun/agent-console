"""통합 서버(agent-console-server — 기본 모듈 전부) + 노트 모듈 예제 + 이 연동.

설치 대신 ``create_app(modules=[*installed_modules(), ...])``로 모듈을 더하고, 리소스 종류는 설정
``plugins.modules``(``register(registries)``)로 등록한다. 노트 모듈은 이웃 예제
(``agent-console-example-module``)다. 저장소 밖에 이 폴더만 복사하면 그 모듈이 없어 진짜 모듈을 쓰는
시험은 건너뛴다(대역으로 같은 것을 보는 시험은 ``test_assembly.py``).
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from notes_helpers import of, run_team, slot_warnings, write_workspace

from agent_console_example_link import MODULE_ID, module
from agent_console_modkit import Module
from agent_console_server import create_app, installed_modules, load_settings
from agent_console_server.testing import register_project

API = "/api/v1"
TOKEN = "test-token-0123456789abcdef"
NOTES_MODULE = "agent_console_example_module"
NOTES_ID = "mod-example-notes"


def notes_module() -> Module | None:
    """이웃 예제의 노트 모듈(없으면 None)."""
    try:
        found: Any = importlib.import_module(NOTES_MODULE)
    except ImportError:
        return None
    mod: Module = found.module
    return mod


def _modules(*, with_notes: bool) -> list[Module]:
    extra: list[Module] = [module]
    notes = notes_module() if with_notes else None
    if with_notes:
        if notes is None:
            pytest.skip("이웃 예제 agent-console-example-module이 없다(저장소 밖 복사)")
        extra.insert(0, notes)
    ids = {m.descriptor.id for m in extra}
    return [m for m in installed_modules() if m.descriptor.id not in ids] + extra


@contextmanager
def _server(
    tmp_path: Path, *, with_notes: bool = True, disabled: Sequence[str] = ()
) -> Iterator[TestClient]:
    write_workspace(tmp_path / "ws")
    config = tmp_path / "agent-console.yaml"
    config.write_text("workspace: ws\n", encoding="utf-8")
    environ = {"CLAUDE_CONFIG_DIR": str(tmp_path / "claude")}  # 실제 ~/.claude를 읽지 않게
    overrides: dict[str, Any] = {
        "security": {"allowed_hosts": ["testserver"]},
        "plugins": {"modules": ["agent_console_example_link.resource_type:register"]},
        # 프로젝트 폴더 없이 실행한다(기본은 프로젝트를 고른 실행만 허용).
        "modules": {
            "disabled": list(disabled),
            "options": {"link-projects-runs": {"require_project": False}},
        },
    }
    settings = load_settings(config, environ=environ, overrides=overrides)
    app = create_app(
        settings, environ=environ, token=TOKEN, modules=_modules(with_notes=with_notes)
    )
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


@pytest.fixture(autouse=True)
def _no_real_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))


def _states(client: TestClient) -> dict[str, dict[str, Any]]:
    return {m["id"]: m for m in client.get(f"{API}/modules").json()}


def test_full_server_agent_reads_notes_written_over_rest(tmp_path: Path) -> None:
    with _server(tmp_path) as client:
        assert _states(client)[MODULE_ID]["status"] == "active"
        types = {t["id"] for t in client.get(f"{API}/resource-types").json()}
        assert "example-notes" in types
        # 프로젝트 없는 실행 = 앱 공간 노트(다른 공간 노트는 보이지 않는다)
        (tmp_path / "proj").mkdir()
        register_project(client, "p1", tmp_path / "proj")
        made = client.post(f"{API}/example-notes", json={"text": "배포는 금요일"})
        assert made.status_code == 201, made.text
        other = client.post(f"{API}/example-notes?project=p1", json={"text": "프로젝트 노트"})
        assert other.status_code == 201, other.text
        run, events = run_team(client)
        assert run["status"] == "completed", run
        [reply] = of(events, "run.reply")
        assert "배포는 금요일" in reply["payload"]["text"]
        assert "프로젝트 노트" not in reply["payload"]["text"]
        [event] = of(events, "example_notes.read")
        assert event["payload"]["count"] == 1
        assert "project_id" not in event["payload"]
        assert "배포는 금요일" not in str(event["payload"])
        assert slot_warnings(events) == []


def test_server_without_notes_module_starts_link_unsatisfied(tmp_path: Path) -> None:
    with _server(tmp_path, with_notes=False) as client:
        assert client.get(f"{API}/health").status_code == 200
        states = _states(client)
        assert states[MODULE_ID]["status"] == "unsatisfied"
        assert NOTES_ID not in states
        assert states["mod-runs"]["status"] == "active"
        run, events = run_team(client)
        assert run["status"] == "completed", run
        assert len(slot_warnings(events)) == 1


def test_server_without_runs_module_starts_link_unsatisfied(tmp_path: Path) -> None:
    with _server(tmp_path, disabled=["mod-runs"]) as client:
        assert client.get(f"{API}/health").status_code == 200
        states = _states(client)
        assert states[MODULE_ID]["status"] == "unsatisfied"
        assert states[NOTES_ID]["status"] == "active"
        assert client.get(f"{API}/example-notes").status_code == 200
        assert client.get(f"{API}/agents").status_code == 200
