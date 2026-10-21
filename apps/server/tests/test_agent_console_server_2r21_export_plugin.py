"""2R.21 확장성: 새 내보내기 형식을 플러그인 모듈 하나로 추가한다(서버 코드 수정 없음).

`plugins.modules`의 `register(registries)`가 `exporters` 확장 묶음에 형식 공장을 등록하면
`/exporters`에 보이고 계획·보관 파일(zip)·폴더 쓰기가 같은 규칙을 따른다
(경로 탈출 거부·평문 비밀 가림).
"""

from __future__ import annotations

import io
import textwrap
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_console_server.testing import API, make_settings, seed, server

_PLUGIN = """
from agent_console_contracts import ExporterDescriptor
from agent_console_exports import OutputFile, ExportOutput


class Lines:
    descriptor = ExporterDescriptor(
        id="t-lines",
        title="줄 목록",
        config_schema={"type": "object"},
        kinds=["agent", "resource", "graph"],
    )

    def plan(self, items, catalog, options):
        text = "".join(f"{i.kind}:{i.id}\\n" for i in items)
        body = (text + "token=ghp_plain_value_123456\\n").encode()
        files = [OutputFile("list.txt", body, "text/plain")]
        if options.get("escape"):
            files.append(OutputFile("../evil.txt", b"x"))
        return ExportOutput(files=files)


def register(registries):
    registries.extension("exporters").register("t-lines", lambda options: Lines(), source="module")
"""


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    source = textwrap.dedent(_PLUGIN)
    (plugin_dir / "ac_server_test_2r21_exporter.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(plugin_dir))
    (tmp_path / "out").mkdir()
    settings = make_settings(
        tmp_path,
        plugins={"modules": ["ac_server_test_2r21_exporter:register"]},
        options={"mod-exports": {"roots": [{"id": "out", "path": str(tmp_path / "out")}]}},
    )
    with server(settings) as c:
        yield c


def test_new_export_format_plugin_works_without_code_changes(
    client: TestClient, tmp_path: Path
) -> None:
    seed(client)
    ids = {e["id"] for e in client.get(f"{API}/exporters").json()}
    assert {"claude-dir", "t-lines"} <= ids
    agent = client.get(f"{API}/agents").json()[0]["id"]
    request = {"exporter": "t-lines", "items": [{"kind": "agent", "id": agent}]}
    plan = client.post(f"{API}/exports/plan", json=request)
    assert plan.status_code == 200, plan.text
    assert [f["path"] for f in plan.json()["files"]] == ["list.txt"]
    archive = client.post(f"{API}/exports/archive", json=request)
    assert archive.status_code == 200, archive.text
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        data = z.read("list.txt").decode()
    assert f"agent:{agent}" in data
    assert "ghp_plain_value_123456" not in data  # 마지막 비밀 안전망이 형식과 무관하게 적용된다


def test_plugin_format_output_paths_are_still_checked(client: TestClient, tmp_path: Path) -> None:
    seed(client)
    agent = client.get(f"{API}/agents").json()[0]["id"]
    request = {
        "exporter": "t-lines",
        "items": [{"kind": "agent", "id": agent}],
        "options": {"escape": True},
        "root": "out",
        "subdir": "p",
    }
    response = client.post(f"{API}/exports/write", json=request)
    assert response.status_code >= 400, response.text
    assert not (tmp_path / "out" / "evil.txt").exists()
    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path / "out" / "p" / "list.txt").exists()
