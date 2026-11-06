"""페이지 기록 저장소 열기(X49, design §7R.6·`[7R.11 구현]`).

- ``BRANCH``: 계보 ``wiki``(리비전은 ``agent_console_wiki.sqlite``가 소유, 이 모듈은 감싸기만 한다).
  범위 ``("app", "project")`` — 호스트 DB와 프로젝트 기록 DB에 같은 리비전. 모듈을 끄면 호스트가
  계보를 올리지 않는다(build 직전만 올림).
- 단독 공간: 호스트 DB 파일에 붙는 ``SqliteWikiHistory``(호스트가 이미 계보를 올렸다,
  ``create=False``). 호스트 DB가 없거나 메모리 DB면 ``InMemoryWikiHistory``(프로세스가 끝나면 사라짐
  — ``kind="memory"``).
- 프로젝트 공간: ``records.spaces`` 포트의 그 공간 기록 DB 파일(``RecordsWikiHistory`` — 읽기는
  파일이
  없으면 빈 결과, 쓰기는 부를 때마다 ``writable_engine()``으로 계보를 확인·파일을 만든다). 포트가
  없으면 기록 없음(호스트 DB에 대신 쓰지 않는다).
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Collection, Sequence
from pathlib import Path
from typing import Any, Literal

from agent_console_contracts.wiki import WikiChangePage, WikiHistoryPage, WikiPageVersion
from agent_console_modkit import MigrationBranch
from agent_console_store import RecordsSpaces
from agent_console_wiki import HistoryEntry, HistorySummary, InMemoryWikiHistory, WikiHistory
from agent_console_wiki.sqlite import BRANCH_NAME, MIGRATIONS_DIR, SqliteWikiHistory

BRANCH = MigrationBranch(BRANCH_NAME, MIGRATIONS_DIR, scopes=("app", "project"))
"""모듈 서술자 ``migrations``에 넣는 계보(앱 DB + 프로젝트 기록 DB 범위)."""

type HistoryKind = Literal["host", "memory"]


def database_file(engine: Any) -> Path | None:
    """SQLAlchemy 엔진(또는 ``engine`` 속성이 있는 DB 핸들)이 가리키는 SQLite 파일.

    없거나 메모리 DB면 None."""
    if engine is None:
        return None
    engine = getattr(engine, "engine", engine)
    url = getattr(engine, "url", None)
    if url is None or not str(getattr(url, "drivername", "")).startswith("sqlite"):
        return None
    name = getattr(url, "database", None)
    if not name or name == ":memory:" or str(name).startswith("file::memory:"):
        return None
    return Path(str(name))


def open_host_history(database: Any | None) -> tuple[WikiHistory, HistoryKind]:
    """단독 공간 기록 저장소: 호스트 DB 파일(계보는 호스트가 올렸다) → 없으면 메모리."""
    path = database_file(database)
    if path is None:
        return InMemoryWikiHistory(), "memory"
    return SqliteWikiHistory(path, create=False), "host"


class RecordsWikiHistory:
    """프로젝트 기록 DB 위의 ``WikiHistory``(공간 하나).

    Args:
        spaces: 지금 ``records.spaces`` 포트(부를 때마다).
        space: 기록 공간 이름(``접두 + 프로젝트 id``).

    읽기는 기록 DB 파일이 없으면 빈 결과(파일을 만들지 않는다). 쓰기(``record``·``prune``)는 부를
    때마다 ``writable_engine()``(계보 확인·없으면 파일 만들기). 못 쓰면 ``RecordsUnavailable``
    (저장소는 쓰기를 그대로 두고 ``wiki.history_unavailable`` 이슈를 단다).
    """

    def __init__(self, spaces: Callable[[], RecordsSpaces | None], space: str) -> None:
        self._spaces = spaces
        self.space = space
        self._opened: dict[str, SqliteWikiHistory] = {}
        self._lock = threading.Lock()

    def _of(self, engine: Any, journal: str) -> SqliteWikiHistory:
        path = database_file(engine)
        if path is None:
            raise LookupError("기록 DB가 파일이 아닙니다")
        key = str(path)
        with self._lock:
            found = self._opened.get(key)
            if found is None:
                found = SqliteWikiHistory(path, create=False, journal=journal)
                self._opened[key] = found
            return found

    def _handle(self) -> Any:
        port = self._spaces()
        if port is None:
            raise LookupError("기록 공간 연동이 꺼져 있습니다")
        return port.open(self.space)

    def _journal(self, handle: Any) -> str:
        state = getattr(handle, "state", None)
        return str(getattr(state, "journal_mode", None) or "WAL")

    def _reader(self) -> SqliteWikiHistory | None:
        handle = self._handle()
        engine = handle.read_engine()
        return None if engine is None else self._of(engine, self._journal(handle))

    def _writer(self) -> SqliteWikiHistory:
        handle = self._handle()
        return self._of(handle.writable_engine(), self._journal(handle))

    def record(self, entries: Sequence[HistoryEntry]) -> list[WikiPageVersion]:
        return self._writer().record(entries)

    def prune(self, wiki: str, path: str, *, keep: int) -> int:
        return self._writer().prune(wiki, path, keep=keep)

    def list(self, wiki: str, path: str, *, limit: int | None = None) -> WikiHistoryPage:
        reader = self._reader()
        return WikiHistoryPage() if reader is None else reader.list(wiki, path, limit=limit)

    def get(self, wiki: str, path: str, version: int) -> WikiPageVersion | None:
        reader = self._reader()
        return None if reader is None else reader.get(wiki, path, version)

    def read(self, wiki: str, path: str, version: int) -> bytes | None:
        reader = self._reader()
        return None if reader is None else reader.read(wiki, path, version)

    def latest(self, wiki: str, path: str) -> WikiPageVersion | None:
        reader = self._reader()
        return None if reader is None else reader.latest(wiki, path)

    def summaries(self, wiki: str) -> dict[str, HistorySummary]:
        reader = self._reader()
        return {} if reader is None else reader.summaries(wiki)

    def changes(
        self,
        wiki: str | None = None,
        *,
        author_run: str | None = None,
        ops: Collection[str] = (),
        limit: int = 50,
        cursor: str | None = None,
    ) -> WikiChangePage:
        reader = self._reader()
        if reader is None:
            return WikiChangePage()
        return reader.changes(wiki, author_run=author_run, ops=ops, limit=limit, cursor=cursor)

    def close(self) -> None:
        """열어 둔 SQLite 저장소를 닫는다(기록 DB 핸들은 제공자가 닫는다)."""
        with self._lock:
            opened = list(self._opened.values())
            self._opened.clear()
        for item in opened:
            item.close()


def close_history(history: Any) -> None:
    """``close()``가 있으면 부른다(실패는 무시 — 종료 중)."""
    close = getattr(history, "close", None)
    if callable(close):
        with contextlib.suppress(Exception):  # 종료 중 오류는 삼킨다
            close()


__all__ = [
    "BRANCH",
    "HistoryKind",
    "RecordsWikiHistory",
    "close_history",
    "database_file",
    "open_host_history",
]
