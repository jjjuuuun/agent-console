"""``POST /logs/index/purge``(M-3, 5.7R.6): dry_run 기본, 범위 조합, 재수집, 본문 검사.

단독 실행(``python -m agent_console_mod_logs``와 같은 조립)을 임시 폴더에서 띄운다.
로그와 워크스페이스 설정은 저장소 데이터 없이 테스트 안에서 만든다.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_logs.testing import tree_digest
from agent_console_mod_logs.standalone import main
from agent_console_modkit.host import HostSettings

TOKEN = "p" * 32
API = "/api/v1"

# 합성 정규화 로그(normalized-v1). 같은 응답(m1)을 나눈 두 행은 사용량 표본 하나다.
SESSION_A: list[dict[str, Any]] = [
    {
        "schema_version": 1,
        "category": "input",
        "title": "첫 요청",
        "session": "sess-a",
        "thread": "main",
        "cwd": "/work/proj-a",
        "time": 1760000000,
        "tags": ["session_title"],
    },
    {
        "schema_version": 1,
        "category": "llm",
        "title": "답변",
        "session": "sess-a",
        "thread": "main",
        "cwd": "/work/proj-a",
        "model": "model-x",
        "message_id": "m1",
        "time": 1760000001,
        "usage": {"input_tokens": 10, "output_tokens": 3},
    },
    {
        "schema_version": 1,
        "category": "llm",
        "title": "답변(이어짐)",
        "session": "sess-a",
        "thread": "main",
        "cwd": "/work/proj-a",
        "model": "model-x",
        "message_id": "m1",
        "time": 1760000002,
        "usage": {"input_tokens": 10, "output_tokens": 8},
    },
    {
        "schema_version": 1,
        "category": "tool_call",
        "title": "검색 호출",
        "session": "sess-a",
        "thread": "main",
        "cwd": "/work/proj-a",
        "tool": "search",
        "call_id": "c1",
        "stage": "start",
        "time": 1760000003,
        "tags": ["tool"],
    },
    {
        "schema_version": 1,
        "category": "tool_result",
        "title": "검색 결과",
        "session": "sess-a",
        "thread": "main",
        "cwd": "/work/proj-a",
        "tool": "search",
        "call_id": "c1",
        "stage": "complete",
        "time": 1760000005,
        "tags": ["tool"],
    },
    {
        "schema_version": 1,
        "category": "handoff",
        "title": "위임",
        "session": "sess-a",
        "thread": "main",
        "cwd": "/work/proj-a",
        "from": ["main"],
        "to": ["helper"],
        "via": "delegate",
        "time": 1760000006,
    },
    {
        "schema_version": 1,
        "category": "error",
        "title": "실패",
        "session": "sess-a",
        "thread": "helper",
        "cwd": "/work/proj-a",
        "time": 1760000007,
        "agent": {"label": "도우미", "parent_id": "main"},
    },
]
SESSION_B: list[dict[str, Any]] = [
    {
        "schema_version": 1,
        "category": "input",
        "title": "다른 곳 요청",
        "session": "sess-b",
        "thread": "main",
        "cwd": "/elsewhere/tool",
        "time": 1760100000,
    },
    {
        "schema_version": 1,
        "category": "llm",
        "title": "답변",
        "session": "sess-b",
        "thread": "main",
        "cwd": "/elsewhere/tool",
        "model": "model-y",
        "message_id": "m9",
        "time": 1760100001,
        "usage": {"input_tokens": 1, "output_tokens": 2},
    },
]

SETTINGS = """\
logs:
  sources:
    - id: normalized-v1
      enabled: true
      config:
        roots: [ROOT]
  projects:
    groups:
      - id: proj-a
        label: 프로젝트 A
        match: ["/work/proj-a/**"]
"""


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "fixture-logs"
    root.mkdir()
    _write_rows(root / "session-a.jsonl", SESSION_A)
    _write_rows(root / "session-b.jsonl", SESSION_B)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "settings.yaml").write_text(
        SETTINGS.replace("ROOT", json.dumps(str(root))), encoding="utf-8"
    )
    config = tmp_path / "standalone.json"
    config.write_text(
        json.dumps(
            {
                "port": 0,
                "workspace": "ws",
                "state": "state",
                "security": {"token": TOKEN},
                "modules": {"options": {"mod-logs": {"startup_scan": False}}},
            }
        ),
        encoding="utf-8",
    )
    return config, root


def _run(tmp_path: Path, body: Any) -> None:
    config, _ = _layout(tmp_path)
    out = io.StringIO()
    code = main(["--config", str(config)], serve=body, out=out, environ={})
    assert code == 0, out.getvalue()


def _categories(client: TestClient) -> list[str]:
    items = client.get(f"{API}/logs/events", params={"limit": 200}).json()["items"]
    return sorted(e["category"] for e in items)


def test_purge_dry_run_default_then_delete_and_rescan(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def serve(app: Any, settings: HostSettings) -> None:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            client.headers["X-Console-Token"] = TOKEN
            assert client.post(f"{API}/logs/scan").status_code == 202
            seen["before"] = _categories(client)
            body = {"categories": ["llm"]}
            dry = client.post(f"{API}/logs/index/purge", json=body)
            seen["dry"] = dry.json()
            seen["after_dry"] = _categories(client)
            empty = client.post(f"{API}/logs/index/purge")  # 본문 없음 = 전체, dry_run
            seen["empty"] = empty.json()
            real = client.post(f"{API}/logs/index/purge", json={**body, "dry_run": False})
            seen["real"] = real.json()
            seen["after_real"] = _categories(client)
            again = client.post(f"{API}/logs/scan").json()
            seen["rescan_new"] = again["new_events"]
            seen["after_rescan"] = _categories(client)

    _run(tmp_path, serve)
    llm = seen["before"].count("llm")
    assert llm >= 2
    assert seen["dry"]["dry_run"] is True
    assert seen["dry"]["events"] == llm
    assert 1 <= seen["dry"]["usage"] < llm  # 같은 응답(m1) 두 행은 표본 하나
    assert seen["after_dry"] == seen["before"]
    assert seen["empty"]["dry_run"] is True
    assert seen["empty"]["events"] == len(seen["before"])
    assert seen["real"]["dry_run"] is False
    assert seen["real"]["events"] == llm
    assert seen["real"]["cursors"] >= 1
    assert "llm" not in seen["after_real"]
    # 커서를 지웠으니 다시 읽어 지운 것만 다시 들어간다(남은 것은 같은 uid라 건너뜀).
    assert seen["rescan_new"] == llm
    assert seen["after_rescan"] == seen["before"]


def test_purge_without_rescan_keeps_cursors(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def serve(app: Any, settings: HostSettings) -> None:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            client.headers["X-Console-Token"] = TOKEN
            client.post(f"{API}/logs/scan")
            seen["real"] = client.post(
                f"{API}/logs/index/purge",
                json={"sources": ["normalized-v1"], "rescan": False, "dry_run": False},
            ).json()
            seen["rescan_new"] = client.post(f"{API}/logs/scan").json()["new_events"]
            seen["after"] = _categories(client)

    _run(tmp_path, serve)
    assert seen["real"]["events"] > 0
    assert seen["real"]["cursors"] == 0
    assert seen["rescan_new"] == 0
    assert seen["after"] == []


def test_purge_rejects_bad_body_and_keeps_source_files(tmp_path: Path) -> None:
    config, root = _layout(tmp_path)
    digest = tree_digest(root)
    seen: dict[str, Any] = {}

    def serve(app: Any, settings: HostSettings) -> None:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            client.headers["X-Console-Token"] = TOKEN
            client.post(f"{API}/logs/scan")
            purge = f"{API}/logs/index/purge"
            bodies: list[dict[str, Any]] = [
                {"sources": []},
                {"categories": [""]},
                {"unknown": 1},
                {"before": "yesterday"},
            ]
            seen["codes"] = [client.post(purge, json=body).status_code for body in bodies]
            seen["count"] = len(_categories(client))
            refused = client.post(purge, json={"dry_run": False})
            seen["refused"] = (refused.status_code, refused.json()["error"]["details"]["path"])
            seen["kept"] = len(_categories(client))
            seen["reset"] = client.post(purge, json={"dry_run": False, "all": True}).json()
            seen["after"] = _categories(client)

    out = io.StringIO()
    assert main(["--config", str(config)], serve=serve, out=out, environ={}) == 0
    assert seen["codes"] == [422, 422, 422, 422]
    assert seen["count"] > 0
    # 범위 없이 실제로 지우려면 all: true 확인이 있어야 한다(없으면 아무것도 지우지 않고 422).
    assert seen["refused"] == (422, "all")
    assert seen["kept"] == seen["count"]
    assert seen["reset"]["events"] == seen["count"]
    assert seen["reset"]["agents"] >= 1
    assert seen["after"] == []
    assert tree_digest(root) == digest  # 원본은 읽기 전용


def test_purge_all_confirmation_only_for_unscoped_real_delete() -> None:
    """``all``은 범위 없는 실제 비우기에만 필요하다(dry_run·범위가 있으면 없어도 된다)."""
    from agent_console_mod_logs.purge import LogPurgeRequest

    assert LogPurgeRequest(dry_run=False).needs_confirmation
    assert not LogPurgeRequest(dry_run=False, all=True).needs_confirmation
    assert not LogPurgeRequest().needs_confirmation  # dry_run 기본
    assert not LogPurgeRequest(dry_run=False, categories=["llm"]).needs_confirmation
    assert not LogPurgeRequest(dry_run=False, before=1.0).needs_confirmation


def test_purge_unsupported_index_is_client_error() -> None:
    """비우기를 지원하지 않는 색인이면 500이 아니라 400 ``logs.purge_unsupported``."""
    from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
    from agent_console_logs import LogIndex
    from agent_console_logs.testing import MemoryLogIndex
    from agent_console_mod_logs import module as logs_module
    from agent_console_mod_logs.errors import PURGE_UNSUPPORTED
    from agent_console_mod_logs.ports import LOGS_QUERY
    from agent_console_modkit import assemble
    from agent_console_modkit.host import SecurityPolicy, create_host_app

    class _NoPurge:
        """``LogIndex``만 있고 ``purge``가 없는 색인(감싸서 넘긴다)."""

        def __init__(self, inner: LogIndex) -> None:
            self._inner = inner

        def __getattr__(self, name: str) -> Any:
            if name == "purge":
                raise AttributeError(name)
            return getattr(self._inner, name)

    assembly = assemble([logs_module])
    svc = assembly.port(LOGS_QUERY)
    svc._index = _NoPurge(MemoryLogIndex())  # type: ignore[union-attr]  # 비우기 없는 색인으로 바꿔 끼움
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        response = client.post(f"{API}/logs/index/purge", json={"categories": ["llm"]})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == PURGE_UNSUPPORTED
