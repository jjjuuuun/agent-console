"""모듈 혼자 켠 조립(테스트 호스트 = modkit 호스트)과 ``python -m`` 단독 실행."""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_example_module import (
    NOTES_READER,
    STORAGE_MEMORY,
    NotesReader,
    local_settings_module,
    main,
    module,
)
from agent_console_example_module.storage import BRANCH
from agent_console_modkit import (
    DEFINITION_KIND_CONTRIBUTIONS,
    Assembly,
    BaseServices,
    ModulesConfig,
    ModuleState,
    Paths,
    assemble,
)
from agent_console_modkit.host import HostSettings, SecurityPolicy, create_host_app
from agent_console_modkit.testing import RecordingDatabase
from agent_console_store import SqliteDatabase

API = "/api/v1"
TOKEN = "t" * 32
ROOT = Path(__file__).resolve().parents[1]


def _paths(tmp_path: Path) -> Paths:
    return Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def test_alone_rest_port_and_kind(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "app.sqlite3")
    config = ModulesConfig(options={"mod-example-notes": {"max_notes": 2}})
    assembly = assemble([module], config, base=BaseServices(paths=_paths(tmp_path), database=db))
    status = assembly.status("mod-example-notes")
    assert status is not None
    assert status.state is ModuleState.ACTIVE
    assert db.revision(BRANCH.name) == "example_notes_0001"  # 켜질 때 호스트가 계보를 올렸다
    [contribution] = assembly.ports(DEFINITION_KIND_CONTRIBUTIONS)
    assert contribution.kind.name == "example-note-template"
    assert contribution.summary_fields == ("category",)
    with _client(assembly) as client:
        for word in ("a", "b", "c"):
            made = client.post(f"{API}/example-notes", json={"text": word})
            assert made.status_code == 201, made.text
        listed = client.get(f"{API}/example-notes").json()
        assert [n["text"] for n in listed] == ["c", "b"]  # 설치자 옵션 max_notes=2
        one = client.get(f"{API}/example-notes/{listed[0]['id']}")
        assert one.json()["text"] == "c"
        missing = client.get(f"{API}/example-notes/nope")
        assert (missing.status_code, missing.json()["error"]["code"]) == (404, "not_found")
        empty = client.post(f"{API}/example-notes", json={"text": " "})
        assert empty.status_code == 422
        # 선택 포트가 없는 동작만 409(정의 기능·프로젝트 기록 연동 없음)
        tpl = client.post(f"{API}/example-notes", json={"template": "greet"})
        assert tpl.status_code == 409
        assert tpl.json()["error"]["details"]["port"] == "definitions.lookup"
        proj = client.get(f"{API}/example-notes?project=p1")
        assert proj.status_code == 409
        assert proj.json()["error"]["details"]["port"] == "records.spaces"
        no_token = client.post(
            f"{API}/example-notes", json={"text": "x"}, headers={"X-Console-Token": ""}
        )
        assert no_token.status_code == 401  # 보안은 호스트가 한다
    reader = assembly.port(NOTES_READER)
    assert isinstance(reader, NotesReader)
    assert [n.text for n in reader.list_notes()] == ["c", "b"]
    db.close()


def test_without_database_keeps_notes_in_memory(tmp_path: Path) -> None:
    assembly = assemble([module], None, base=BaseServices(paths=_paths(tmp_path)))
    with _client(assembly) as client:
        assert client.post(f"{API}/example-notes", json={"text": "a"}).status_code == 201
        assert len(client.get(f"{API}/example-notes").json()) == 1
    warnings = [w for f in assembly.ports(_warnings_key()) for w in f()]
    assert [w.code for w in warnings] == [STORAGE_MEMORY]


def _warnings_key() -> Any:
    from agent_console_example_module.ports import SERVER_WARNINGS

    return SERVER_WARNINGS


def test_route_is_installer_option(tmp_path: Path) -> None:
    config = ModulesConfig(options={"mod-example-notes": {"route": "/memo"}})
    assembly = assemble([module], config, base=BaseServices(paths=_paths(tmp_path)))
    with _client(assembly) as client:
        assert client.get(f"{API}/memo").status_code == 200
        assert client.get(f"{API}/example-notes").status_code == 404


def test_disabled_module_has_no_route(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "app.sqlite3")
    config = ModulesConfig(disabled=["mod-example-notes"])
    other = local_settings_module(workspace=tmp_path / "ws")
    assembly = assemble([module, other], config, base=BaseServices(database=db))
    status = assembly.status("mod-example-notes")
    assert status is not None
    assert status.state is ModuleState.DISABLED
    with _client(assembly) as client:
        assert client.get(f"{API}/example-notes").status_code == 404
        assert client.get(f"{API}/health").status_code == 200  # 나머지는 그대로
    assert db.revision(BRANCH.name) is None  # 꺼진 모듈의 계보는 올리지 않는다
    db.close()


def test_bad_installer_option_fails_only_this_module(tmp_path: Path) -> None:
    config = ModulesConfig(options={"mod-example-notes": {"max_notes": 0}})
    other = local_settings_module(workspace=tmp_path / "ws")
    assembly = assemble([module, other], config, base=BaseServices(paths=_paths(tmp_path)))
    status = assembly.status("mod-example-notes")
    assert status is not None
    assert not status.active
    assert assembly.status(other.descriptor.id) is not None


def test_project_scope_branch_is_listed_for_project_db(tmp_path: Path) -> None:
    db = RecordingDatabase(tmp_path / "x")
    assembly = assemble([module], None, base=BaseServices(database=db))
    assert ["example_notes"] in db.upgraded
    assert assembly.status("mod-example-notes") is not None


STANDALONE_TOKEN = "s" * 32


def _config(tmp_path: Path, *, settings_yaml: str | None = None) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    if settings_yaml is not None:
        (ws / "settings.yaml").write_text(settings_yaml, encoding="utf-8")
    path = tmp_path / "standalone.yaml"
    path.write_text(
        "workspace: ws\nstate: state\n"
        f"security:\n  token: {STANDALONE_TOKEN}\n  allowed_hosts: [testserver]\n",
        encoding="utf-8",
    )
    return path


def test_standalone_main_serves_with_local_settings(tmp_path: Path) -> None:
    config = _config(tmp_path, settings_yaml="example_notes:\n  newest_first: false\n")
    seen: dict[str, Any] = {}

    def serve(app: Any, settings: HostSettings) -> None:
        seen["port"] = settings.port
        with TestClient(app) as client:
            client.headers["X-Console-Token"] = STANDALONE_TOKEN
            client.post(f"{API}/example-notes", json={"text": "첫째"})
            client.post(f"{API}/example-notes", json={"text": "둘째"})
            seen["texts"] = [n["text"] for n in client.get(f"{API}/example-notes").json()]

    out = io.StringIO()
    code = main(["--config", str(config), "--port", "0"], serve=serve, out=out, environ={})
    assert code == 0, out.getvalue()
    assert "mod-example-notes" in out.getvalue()
    assert seen["texts"] == ["첫째", "둘째"]  # 사용자 설정 섹션(newest_first: false)
    assert (tmp_path / "state" / "example-notes.sqlite3").exists()


def test_python_m_check(tmp_path: Path) -> None:
    config = _config(tmp_path)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_console_example_module",
            *("--config", str(config), "--port", "0", "--check", "--timeout", "60"),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "/health → 200" in done.stdout
