"""5.7R.33i: 하위 폴더 세션과 손실 키의 확정(세션 cwd), 두 루트 같은 규칙.

Claude Code `projects/<키>`는 경로의 영문자·숫자 밖 글자를 `-`로 바꾼 손실 변환이다. 그래서
등록 폴더 `/work/demo`의 하위 폴더 `/work/demo/src` 세션(키 `-work-demo-src`)과 등록 안 된
`/work/demo-x`(키 `-work-demo-x`)는 키만으로 가를 수 없다. 키 접두로 후보를 고르고 세션 cwd로
확정한다. 키가 접두에도 맞지 않는 폴더는 열지 않는다(메타도 안 읽음).
실제 `~/.claude`는 읽지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_console_contracts.logs import LogSettings
from agent_console_logs import LogFilter, LogIngestor, LogRegistries, ProjectFolders, query_context
from agent_console_logs.testing import MemoryLogIndex, RecordingOpen
from agent_console_logs_claude import project_key

SOURCE = "claude-code-jsonl"


def _write(root: Path, cwd: str, session: str, *, with_meta: bool = False) -> Path:
    folder = root / project_key(cwd)
    folder.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "summary", "summary": "앞 줄에는 cwd가 없다"},
        {
            "sessionId": session,
            "cwd": cwd,
            "type": "user",
            "uuid": f"{session}-u",
            "timestamp": "2026-10-01T00:00:00.000Z",
            "message": {"role": "user", "content": "안녕"},
        },
    ]
    path = folder / f"{session}.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    if with_meta:
        sub = folder / session / "subagents"
        sub.mkdir(parents=True)
        (sub / "agent-x.meta.json").write_text("{}", encoding="utf-8")
    return path


def _settings() -> LogSettings:
    return LogSettings.model_validate({"sources": [{"id": SOURCE, "enabled": True}]})


def _project_for(folders: dict[str, str]) -> Any:
    def project_for(cwd: str) -> str | None:
        for pid, folder in folders.items():
            if cwd == folder or cwd.startswith(folder + "/"):
                return pid
        return None

    return project_for


def _scan(home: Path, workspace: Path, folders: ProjectFolders, opened: RecordingOpen) -> Any:
    registries = LogRegistries()
    registries.load()
    index = MemoryLogIndex()
    LogIngestor(
        index,
        registries,
        environ={"HOME": str(home)},
        clock=lambda: 1.0,
        paths={"workspace": workspace},
        open_read=opened,
        projects=lambda: folders,
    ).scan(_settings())
    return index


def test_subfolder_included_lookalike_excluded_both_roots(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cli_root = home / ".claude" / "projects"
    workspace = tmp_path / "app"
    app_root = workspace / ".state" / "claude" / "projects"
    _write(cli_root, "/work/demo", "s-root")
    _write(cli_root, "/work/demo/src", "s-sub")  # 하위 폴더: 포함
    _write(cli_root, "/work/demo-x", "s-look", with_meta=True)  # 접두만 같음: 제외
    _write(cli_root, "/elsewhere", "s-other", with_meta=True)  # 접두도 아님: 열지 않음
    _write(app_root, "/work/demo", "s-app")  # 앱 실행 세션: 같은 규칙
    _write(app_root, "/work/demo.x", "s-app-look")  # 앱 루트의 손실 키 → 제외
    _write(cli_root, "/work/b", "s-b")
    resolver = _project_for({"demo": "/work/demo", "b": "/work/b"})
    folders = ProjectFolders(registered=(Path("/work/demo"), Path("/work/b")), project_for=resolver)
    opened = RecordingOpen()
    index = _scan(home, workspace, folders, opened)

    sessions = {s.session for s in index.list_sessions(LogFilter(), query_context(None))}
    assert sessions == {"s-root", "s-sub", "s-app", "s-b"}  # 등록 안 된 폴더 세션 0건
    opened_text = [str(p) for p in opened.opened]
    assert not any("-elsewhere" in p for p in opened_text)  # 키가 맞지 않으면 열지 않는다
    assert not any(p.endswith(".meta.json") for p in opened_text)  # 확정 전 메타 안 읽음

    ctx = query_context(None, project_for=resolver)
    by_id = {s.session: s.project_id for s in index.list_sessions(LogFilter(), ctx)}
    # 두 루트(CLI·앱)의 같은 프로젝트 세션이 같은 project_id, 하위 폴더도 그 프로젝트
    assert by_id == {"s-root": "demo", "s-sub": "demo", "s-app": "demo", "s-b": "b"}
    demo = {e.session for e in index.query_events(LogFilter(project=("demo",)), ctx).items}
    only_b = {e.session for e in index.query_events(LogFilter(project=("b",)), ctx).items}
    assert demo == {"s-root", "s-sub", "s-app"}
    assert only_b == {"s-b"}  # 두 프로젝트 필터 분리


def test_simple_containment_without_resolver(tmp_path: Path) -> None:
    """`project_for` 없이(단독 사용) 등록 폴더만 줘도 하위 폴더·손실 키를 같은 규칙으로 가른다."""
    home = tmp_path / "home"
    root = home / ".claude" / "projects"
    _write(root, "/work/demo/src", "s-sub")
    _write(root, "/work/demo-x", "s-look")
    folders = ProjectFolders(registered=(Path("/work/demo"),))
    index = _scan(home, tmp_path / "app", folders, RecordingOpen())
    assert {s.session for s in index.list_sessions(LogFilter(), query_context(None))} == {"s-sub"}
