"""통합 서버 시험(agent-console-server — 기본 모듈 전부): 설치하지 않았으면 설정
`plugins.modules`로 이 형식을 등록하고, 설치했으면(저장소 밖 설치 검사) entry point로 로드되게
둔다(둘 다 같은 레지스트리에 들어가므로 둘을 함께 쓰면 같은 key가 두 번 등록된다).

- 등록 프로젝트 A의 에이전트 하나를 이 형식으로 프로젝트 B 폴더에 내보내면 그 에이전트가 쓰는
  리소스(여러 파일 본문)도 A 공간에서 찾아 함께 담기고 → B에서 같은 형식 출처로 가져오면 → 같은
  정의·같은 본문.
- 원본 파일은 가져오기 뒤에도 그대로다. 비밀 참조(`secret://`)는 참조 그대로 옮겨진다.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_example_transfer import FORMAT_ID, default_format_data
from agent_console_exports import EXPORTERS_GROUP
from agent_console_imports import IMPORT_SOURCES_GROUP
from agent_console_server.testing import API, agent_doc, make_settings, register_project, server

PLUGIN = "agent_console_example_transfer:register"
PACKAGE = PLUGIN.split(":", 1)[0]
SKILL = {"id": "style", "type": "skill", "name": "문체", "config": {"name": "style"}}
FILES = {"SKILL.md": "# 문체\n\n짧게.\n".encode(), "img/dot.bin": bytes([0, 1, 254, 255])}


def _installed() -> bool:
    """이 패키지가 설치되어 entry point로 두 공장을 알리는지(설치하지 않고 돌리면 False)."""
    found = [
        ep
        for group in (EXPORTERS_GROUP, IMPORT_SOURCES_GROUP)
        for ep in importlib.metadata.entry_points(group=group, name=FORMAT_ID)
    ]
    return any(ep.value.split(":", 1)[0] == PACKAGE for ep in found)


@contextmanager
def _server(tmp_path: Path) -> Iterator[TestClient]:
    # 설치했으면 entry point가 이미 등록한다 — 같은 `register`를 또 부르면 중복 key로 실패한다.
    plugins = {"modules": [] if _installed() else [PLUGIN]}
    settings = make_settings(tmp_path, plugins=plugins)
    with server(settings, environ={"CLAUDE_CONFIG_DIR": str(tmp_path / "claude")}) as client:
        yield client


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))  # 실제 ~/.claude를 읽지 않게


def _seed(client: TestClient, project: str) -> None:
    made = client.post(f"{API}/resources?project={project}", json=SKILL)
    assert made.status_code == 201, made.text
    etag = made.headers["ETag"]
    for path, data in FILES.items():
        put = client.put(
            f"{API}/resources/style/files/{path}?project={project}",
            content=data,
            headers={"If-Match": etag},
        )
        assert put.status_code == 200, put.text
        etag = put.headers["ETag"]
    agent = agent_doc("writer", "ok", resources=[{"ref": "style"}])
    agent["backend_options"]["env"] = {"API_TOKEN": "secret://example_token"}  # 참조(값 아님)
    created = client.post(f"{API}/agents?project={project}", json=agent)
    assert created.status_code == 201, created.text


def _definitions(client: TestClient, project: str) -> dict[str, Any]:
    agent = client.get(f"{API}/agents/writer?project={project}")
    resource = client.get(f"{API}/resources/style?project={project}")
    assert agent.status_code == 200, agent.text
    assert resource.status_code == 200, resource.text
    files = {
        f["path"]: client.get(f"{API}/resources/style/files/{f['path']}?project={project}").content
        for f in client.get(f"{API}/resources/style/files?project={project}").json()
    }
    drop = {"project", "scope", "updated_at", "created_at"}
    return {
        "agent": {k: v for k, v in agent.json().items() if k not in drop},
        "resource": {k: v for k, v in resource.json().items() if k not in drop},
        "files": files,
    }


def test_export_then_import_through_the_server(tmp_path: Path) -> None:
    with _server(tmp_path) as client:
        exporters = {e["id"] for e in client.get(f"{API}/exporters").json()}
        assert FORMAT_ID in exporters
        info = client.get(f"{API}/server-info").json()
        assert all(p["status"] != "failed" for p in info["plugins"]), info["plugins"]

        a_dir, b_dir = tmp_path / "proj-a", tmp_path / "proj-b"
        a_dir.mkdir()
        b_dir.mkdir()
        register_project(client, "a", a_dir)
        register_project(client, "b", b_dir)
        _seed(client, "a")

        # 프로젝트 A의 정의 → 프로젝트 B 폴더(등록 폴더 = 내보내기 루트, 루트 id = 등록 id)
        request = {
            "exporter": FORMAT_ID,
            # 에이전트 하나만 고른다 — 쓰는 리소스는 그 프로젝트 공간에서 찾아 함께 담긴다.
            "items": [{"kind": "agent", "id": "writer"}],
            "root": "b",
        }
        written = client.post(f"{API}/exports/write?project=a", json=request)
        assert written.status_code == 200, written.text
        bundle = b_dir / default_format_data()["file_name"]
        assert bundle.is_file()
        before = bundle.read_bytes()

        sources = {s["id"] for s in client.get(f"{API}/resources/import/sources?project=b").json()}
        assert FORMAT_ID in sources
        preview = client.post(
            f"{API}/resources/import/preview?project=b", json={"source": FORMAT_ID}
        )
        assert preview.status_code == 200, preview.text
        candidates = preview.json()["candidates"]
        assert {c["kind"] for c in candidates} == {"agent", "resource"}
        applied = client.post(
            f"{API}/resources/import?project=b",
            json={
                "source": FORMAT_ID,
                "items": [{"candidate_id": c["id"]} for c in candidates],
            },
        )
        assert applied.status_code == 200, applied.text
        actions = sorted((i["kind"], i["target_id"], i["action"]) for i in applied.json()["items"])
        assert actions == [("agent", "writer", "created"), ("resource", "style", "created")]

        source_side, target_side = _definitions(client, "a"), _definitions(client, "b")
        assert target_side == source_side
        assert target_side["files"] == FILES
        env = target_side["agent"]["backend_options"]["env"]
        assert env == {"API_TOKEN": "secret://example_token"}
        assert bundle.read_bytes() == before  # 원본 파일은 읽기만
