"""`agent-console logs purge`(M-3, 5.7R.6): 임시 색인 DB로만 시험한다(실제 사용자 데이터 없음).

기본은 세기만(dry-run), `--yes`가 있어야 지운다. 색인 위치는 `--index` 또는 서버 설정
(`modules.options.mod-logs.index_path` → 서버 DB). 파일·테이블을 만들지 않는다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from agent_console_cli import main
from agent_console_cli._logs import parse_before
from agent_console_logs import LogFilter, QueryContext
from agent_console_logs._index import IndexBatch, StoredCursor
from agent_console_logs.sqlite import open_log_index
from agent_console_logs.testing import make_record


def _fill(path: Path) -> None:
    index = open_log_index(path)
    try:
        index.write(
            IndexBatch(
                records=[
                    make_record("llm", source="a", time=100.0),
                    make_record("blob", source="a", time=101.0),
                    make_record("llm", source="b", time=300.0),
                ],
                cursors=[StoredCursor(source="a", ref="x.jsonl", offset=5)],
            )
        )
    finally:
        index.close()


def _categories(path: Path) -> list[str]:
    index = open_log_index(path)
    try:
        page = index.query_events(LogFilter(), QueryContext())
        return sorted(f"{e.source}:{e.category}" for e in page.items)
    finally:
        index.close()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "idx.sqlite3"
    _fill(path)
    return path


def test_default_is_dry_run(db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["logs", "purge", "--index", str(db), "--category", "blob"]) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "이벤트 1" in out
    assert "--yes" in out
    assert len(_categories(db)) == 3
    assert main(["logs", "purge", "--index", str(db), "--source", "a", "--dry-run"]) == 0
    assert len(_categories(db)) == 3


def test_yes_deletes_scoped_rows(db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ["logs", "purge", "--index", str(db), "--source", "a", "--category", "llm", "--yes"]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "지웠습니다: 이벤트 1" in out
    assert "커서 1" in out
    assert _categories(db) == ["a:blob", "b:llm"]


def test_before_and_no_rescan(db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ["logs", "purge", "--index", str(db), "--before", "200", "--no-rescan", "-y"]
    assert main(args) == 0
    assert "커서 0" in capsys.readouterr().out
    assert _categories(db) == ["b:llm"]


def test_unscoped_needs_all(db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["logs", "purge", "--index", str(db), "--yes"]) == 2
    assert "--all" in capsys.readouterr().err
    assert len(_categories(db)) == 3
    assert main(["logs", "purge", "--index", str(db), "--all"]) == 0  # dry-run
    assert len(_categories(db)) == 3
    assert main(["logs", "purge", "--index", str(db), "--all", "--yes"]) == 0
    assert _categories(db) == []


def test_option_errors(db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = ["logs", "purge", "--index", str(db), "--source", "a"]
    assert main([*base, "--dry-run", "--yes"]) == 2
    assert main([*base, "--before", "어제"]) == 2
    assert main([*base, "--source", ""]) == 2
    missing = tmp_path / "nope" / "none.sqlite3"
    assert main(["logs", "purge", "--index", str(missing), "--source", "a"]) == 2
    assert not missing.exists()
    assert not missing.parent.exists()
    assert "색인 파일이 없습니다" in capsys.readouterr().err
    assert len(_categories(db)) == 3


def test_index_path_from_server_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in list(os.environ):
        if name.startswith("AGENT_CONSOLE_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "conf"
    folder.mkdir()
    _fill(folder / "state" / "logs.sqlite3")
    config = folder / "agent-console.yaml"
    config.write_text(
        "modules:\n  options:\n    mod-logs:\n      index_path: state/logs.sqlite3\n",
        encoding="utf-8",
    )
    assert main(["logs", "purge", "--config", str(config), "--source", "b", "--yes"]) == 0
    out = capsys.readouterr().out
    assert str(folder / "state" / "logs.sqlite3") in out
    assert _categories(folder / "state" / "logs.sqlite3") == ["a:blob", "a:llm"]
    # index_path가 없으면 서버 DB(<workspace>/.state/console.sqlite3)
    host = folder / "plain.yaml"
    host.write_text("workspace: ws\n", encoding="utf-8")
    db = folder / "ws" / ".state" / "console.sqlite3"
    _fill(db)
    assert main(["logs", "purge", "--config", str(host), "--category", "blob", "-y"]) == 0
    assert _categories(db) == ["a:llm", "b:llm"]
    bad = folder / "bad.yaml"
    bad.write_text("port: nope\n", encoding="utf-8")
    assert main(["logs", "purge", "--config", str(bad), "--source", "a"]) == 2


def test_parse_before() -> None:
    assert parse_before("1760000000") == 1_760_000_000.0
    assert parse_before("2026-10-01T00:00:00+00:00") == 1_790_812_800.0
    assert parse_before("2026-10-01") == datetime(2026, 10, 1).timestamp()
    with pytest.raises(ValueError, match="before"):
        parse_before("soon")


def test_logs_purge_import_scope(db: Path) -> None:
    """`logs purge --index`는 서버·FastAPI를 import하지 않는다."""
    code = (
        "import json, sys, agent_console_cli\n"
        "try:\n"
        f"    agent_console_cli.main(['logs', 'purge', '--index', {str(db)!r}, '--source', 'a'])\n"
        "finally:\n"
        "    names = sorted(m for m in sys.modules if '.' not in m)\n"
        "    print(json.dumps(names), file=sys.stderr)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    loaded = set(json.loads(result.stderr.strip().splitlines()[-1]))
    assert "agent_console_logs" in loaded
    assert loaded.isdisjoint({"agent_console_server", "fastapi", "uvicorn"})
