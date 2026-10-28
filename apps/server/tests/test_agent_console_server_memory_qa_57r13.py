"""5.7R.13 QA: 모듈 끄기(경로 404·계보 미적용·DB 파일 없음), 범위 없는 로그 비우기 확인."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server


def _db_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.suffix in {".sqlite", ".sqlite3", ".db"}]


def _tables(path: Path) -> set[str]:
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    finally:
        con.close()


def test_memory_on_applies_lineage_off_does_not(tmp_path: Path) -> None:
    on, off = tmp_path / "on", tmp_path / "off"
    on.mkdir()
    off.mkdir()
    with server(make_settings(on)) as client:
        assert client.get(f"{API}/memory/scope-kinds").status_code == 200
    tables = {t for p in _db_files(on) for t in _tables(p)}
    assert "alembic_version_memory" in tables, tables

    with server(make_settings(off, modules={"disabled": ["mod-memory"]})) as client:
        assert client.get(f"{API}/memory/scope-kinds").status_code == 404
        assert client.get(f"{API}/memory/entries").status_code == 404
    tables = {t for p in _db_files(off) for t in _tables(p)}
    assert not any("memory" in t for t in tables), tables


def test_memory_off_with_every_db_module_off_creates_no_db_file(tmp_path: Path) -> None:
    disabled: list[Any] = [
        "mod-memory", "mod-runs", "mod-chat", "mod-projects", "mod-logs", "mod-versions",
        "mod-definitions", "mod-usage",
    ]  # fmt: skip
    with server(make_settings(tmp_path, modules={"disabled": disabled})) as client:
        assert client.get(f"{API}/memory/scope-kinds").status_code == 404
    leftovers = [p for p in _db_files(tmp_path) if "memory" in p.name]
    assert leftovers == []


def test_logs_purge_over_http_needs_all_for_unscoped_delete(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        bad = client.post(f"{API}/logs/index/purge", json={"dry_run": False})
        assert bad.status_code in (400, 422), bad.text
        assert "all" in bad.text
        ok = client.post(f"{API}/logs/index/purge", json={"dry_run": False, "all": True})
        assert ok.status_code == 200, ok.text
        dry = client.post(f"{API}/logs/index/purge", json={})
        assert dry.status_code == 200
        assert dry.json()["dry_run"] is True
