"""SQLite FTS5 검색 색인 `SqliteFtsSearchIndex`(X48 `sqlite-fts`).

저장 구조(버전 `SCHEMA_VERSION`, 파일 하나):

- `meta(key, value)`: `config` = 스키마 버전·토크나이저·대소문자·비밀 가리기 서명(JSON).
- `docs(id, path UNIQUE, hash, title, meta, body)`: 페이지 한 줄.
  `meta` = 태그·별칭을 공백으로 이은 글.
  `body`는 **비밀을 가린 본문**(상한 적용).
- `doc_tags(doc_id, tag)`: 접은 태그(태그 거르기).
- `fts`: FTS5 외부 내용 표(`content='docs'`)로 경로·제목·meta·본문을 색인한다(본문은 한 번만 저장).

색인은 캐시다: 열 때 파일이 깨졌거나 `config`가 다르면
**버리고 빈 색인으로 다시 짓는다**(계보 없음 —
호출자가 `sync_search_index`로 채운다). 토크나이저가 `trigram`이면 3글자 이상 낱말은 FTS5로, 그보다
짧은 낱말은 접은 글 포함 검사(LIKE식)로 찾는다. 쓸 수 없는 환경은
`ScanSearchIndex`(메모리)로 대신하고
`degraded=True`다.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from collections.abc import Callable, Collection, Iterable, Sequence
from functools import cache
from pathlib import Path

from agent_console_contracts.wiki import WikiSearchResult
from agent_console_wiki._search import (
    Redactor,
    ScanSearchIndex,
    SearchLimits,
    WikiSearchDocument,
    _identity,
    clamp_limit,
    clip_body,
    default_redactor,
    make_hit,
    meta_score,
    prepared,
)

__all__ = ["FTS_BACKEND_ID", "SCHEMA_VERSION", "SqliteFtsSearchIndex", "fts_tokenizer_available"]

FTS_BACKEND_ID = "sqlite-fts"
SCHEMA_VERSION = 1
_TRIGRAM = "trigram"
_UNICODE61 = "unicode61"
_SQL_VAR_CHUNK = 500


@cache
def fts_tokenizer_available(tokenizer: str) -> bool:
    """이 SQLite에서 FTS5와 `tokenizer`를 쓸 수 있는가(메모리 DB에 시험 표를 만들어 본다)."""
    try:
        con = sqlite3.connect(":memory:")
    except sqlite3.Error:  # pragma: no cover
        return False
    try:
        con.execute(f"CREATE VIRTUAL TABLE t USING fts5(x, tokenize='{tokenizer}')")
        return True
    except sqlite3.Error:
        return False
    finally:
        con.close()


def _quote(term: str) -> str:
    return '"' + term.replace("\x00", "").replace('"', '""') + '"'


class _Prepared:
    __slots__ = ("body", "hash", "meta", "path", "tags", "title")

    def __init__(self, path: str, hash_: str, title: str, meta: str, body: str, tags: set[str]):
        self.path, self.hash, self.title, self.meta, self.body, self.tags = (
            path,
            hash_,
            title,
            meta,
            body,
            tags,
        )


class SqliteFtsSearchIndex:
    """FTS5 검색 색인(X48 `sqlite-fts`). 의미는 `ScanSearchIndex`와 같다(계약 묶음 통과).

    Args:
        path: 색인 파일. None이면 메모리(시험용). 위치는 호출자가 정한다(프로젝트 공간이면 폴더 기록
            DB 옆, 단독이면 호스트 쪽 — 7R.12).
        tokenizer: `trigram`(기본, 부분 일치) 또는 `unicode61`(낱말 앞부분 일치 — 한국어 부분 일치
            불가, 항상 `degraded`).
        case_insensitive: 대소문자 무시(위키 문법 값).
        redact: 본문·제목을 넣기 전에 비밀을 가리는 함수(생략 = 기본 비밀 규칙
            `default_redactor()`).
        redact_signature: 가리기 규칙이 바뀌었는지 알아보는 글. 다르면 색인을 버리고 다시 짓는다.
        limits: 검색 상한.
        assume_missing: 쓸 수 없다고 치는 기능(`fts5`·`trigram`·`unicode61`) — 폴백 시험용.

    FTS5나 토크나이저를 쓸 수 없으면 `trigram` → `unicode61` → 메모리 훑기 순으로 내려가고
    `degraded`가 True다. 스레드 안전(잠금 하나).
    """

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        tokenizer: str = _TRIGRAM,
        case_insensitive: bool = True,
        redact: Redactor | None = None,
        redact_signature: str = "",
        limits: SearchLimits | None = None,
        assume_missing: Collection[str] = (),
    ) -> None:
        self._path = None if path is None else Path(path)
        self._ci = case_insensitive
        self._redact = redact or default_redactor()
        self._sig = redact_signature
        self._limits = limits or SearchLimits()
        self._lock = threading.RLock()
        self._fold: Callable[[str], str] = str.casefold if case_insensitive else _identity
        self._con: sqlite3.Connection | None = None
        self._fallback: ScanSearchIndex | None = None
        self.tokenizer, self._degraded = self._choose(tokenizer, set(assume_missing))
        if self.tokenizer == "":
            self._fallback = ScanSearchIndex(
                case_insensitive=case_insensitive,
                redact=redact,
                limits=self._limits,
                degraded=True,
                backend_id="scan",
            )
        else:
            self._open()

    # ----------------------------------------------------------------- 열기

    @staticmethod
    def _choose(wanted: str, missing: set[str]) -> tuple[str, bool]:
        def ok(name: str) -> bool:
            return "fts5" not in missing and name not in missing and fts_tokenizer_available(name)

        if ok(wanted):
            return wanted, wanted != _TRIGRAM
        if wanted != _UNICODE61 and ok(_UNICODE61):
            return _UNICODE61, True
        return "", True

    @property
    def id(self) -> str:
        return FTS_BACKEND_ID if self._fallback is None else self._fallback.id

    @property
    def degraded(self) -> bool:
        return self._degraded

    def _config(self) -> str:
        return json.dumps(
            {
                "schema": SCHEMA_VERSION,
                "tokenizer": self.tokenizer,
                "case_insensitive": self._ci,
                "redact": self._sig,
            },
            sort_keys=True,
        )

    def _connect(self) -> sqlite3.Connection:
        target = ":memory:" if self._path is None else str(self._path)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(target, check_same_thread=False, isolation_level=None)
        con.execute("PRAGMA synchronous=OFF")
        con.create_function("ac_fold", 1, self._fold, deterministic=True)
        return con

    def _open(self) -> None:
        for attempt in (0, 1):
            con = None
            try:
                con = self._connect()
                stored = self._stored_config(con)
                if stored != self._config():
                    if stored is not None:
                        raise sqlite3.DatabaseError("색인 설정이 달라 다시 짓는다")
                    self._create(con)
                self._con = con
                return
            except sqlite3.Error:
                if con is not None:
                    con.close()
                if attempt == 1 or self._path is None:
                    raise
                self._drop_files()
        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    def _stored_config(con: sqlite3.Connection) -> str | None:
        try:
            row = con.execute("SELECT value FROM meta WHERE key='config'").fetchone()
        except sqlite3.OperationalError:
            return None  # 표 없음 = 새 파일
        return None if row is None else str(row[0])

    def _drop_files(self) -> None:
        assert self._path is not None
        for suffix in ("", "-wal", "-shm", "-journal"):
            with contextlib.suppress(OSError):
                Path(str(self._path) + suffix).unlink()

    def _create(self, con: sqlite3.Connection) -> None:
        tok = self.tokenizer
        if tok == _TRIGRAM:
            tok_sql = "trigram" + ("" if self._ci else " case_sensitive 1")
        else:
            tok_sql = "unicode61"
        con.execute("BEGIN")
        for stmt in (
            "CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE,"
            " hash TEXT NOT NULL, title TEXT NOT NULL, meta TEXT NOT NULL, body TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS doc_tags(doc_id INTEGER NOT NULL, tag TEXT NOT NULL,"
            " PRIMARY KEY(doc_id, tag)) WITHOUT ROWID",
            "CREATE INDEX IF NOT EXISTS doc_tags_tag ON doc_tags(tag)",
            "CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(path, title, meta, body,"
            f" content='docs', content_rowid='id', tokenize='{tok_sql}')",
        ):
            con.execute(stmt)
        con.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('config', ?)", (self._config(),)
        )
        con.execute("COMMIT")

    def _db(self) -> sqlite3.Connection:
        if self._con is None:
            raise RuntimeError("색인이 닫혔다")
        return self._con

    # ----------------------------------------------------------------- 쓰기

    def hashes(self) -> dict[str, str]:
        if self._fallback is not None:
            return self._fallback.hashes()
        with self._lock:
            return {p: h for p, h in self._db().execute("SELECT path, hash FROM docs")}

    def _prepare(self, doc: WikiSearchDocument) -> _Prepared:
        meta = " ".join((*doc.tags, *doc.aliases))
        return _Prepared(
            doc.path,
            doc.content_hash,
            self._redact(doc.title),
            meta,
            self._redact(clip_body(doc.text, self._limits)),
            {self._fold(t) for t in doc.tags},
        )

    def update(self, documents: Iterable[WikiSearchDocument]) -> int:
        if self._fallback is not None:
            return self._fallback.update(documents)
        known = self.hashes()
        todo = [
            self._prepare(d)
            for d in documents
            if not (d.content_hash and known.get(d.path) == d.content_hash)
        ]
        return self._write(todo, clear=False)

    def rebuild(self, documents: Iterable[WikiSearchDocument]) -> int:
        if self._fallback is not None:
            return self._fallback.rebuild(documents)
        return self._write([self._prepare(d) for d in documents], clear=True)

    def _write(self, todo: list[_Prepared], *, clear: bool) -> int:
        if not todo and not clear:
            return 0
        with self._lock:
            con = self._db()
            con.execute("BEGIN IMMEDIATE")
            try:
                if clear:
                    con.execute("DELETE FROM docs")
                    con.execute("DELETE FROM doc_tags")
                    con.execute("INSERT INTO fts(fts) VALUES('delete-all')")
                for item in todo:  # 같은 경로가 두 번 오면 뒤의 것이 남는다
                    self._delete_one(con, item.path)
                    cur = con.execute(
                        "INSERT INTO docs(path, hash, title, meta, body) VALUES(?,?,?,?,?)",
                        (item.path, item.hash, item.title, item.meta, item.body),
                    )
                    rowid = cur.lastrowid
                    con.execute(
                        "INSERT INTO fts(rowid, path, title, meta, body) VALUES(?,?,?,?,?)",
                        (rowid, item.path, item.title, item.meta, item.body),
                    )
                    con.executemany(
                        "INSERT INTO doc_tags(doc_id, tag) VALUES(?,?)",
                        [(rowid, t) for t in sorted(item.tags)],
                    )
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
        return len(todo)

    @staticmethod
    def _delete_one(con: sqlite3.Connection, path: str) -> bool:
        row = con.execute(
            "SELECT id, path, title, meta, body FROM docs WHERE path=?", (path,)
        ).fetchone()
        if row is None:
            return False
        con.execute(
            "INSERT INTO fts(fts, rowid, path, title, meta, body) VALUES('delete',?,?,?,?,?)", row
        )
        con.execute("DELETE FROM doc_tags WHERE doc_id=?", (row[0],))
        con.execute("DELETE FROM docs WHERE id=?", (row[0],))
        return True

    def remove(self, paths: Iterable[str]) -> int:
        if self._fallback is not None:
            return self._fallback.remove(paths)
        items = list(paths)
        if not items:
            return 0
        with self._lock:
            con = self._db()
            con.execute("BEGIN IMMEDIATE")
            try:
                n = sum(1 for p in items if self._delete_one(con, p))
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
        return n

    # ----------------------------------------------------------------- 검색

    def search(
        self,
        query: str,
        *,
        prefix: str | None = None,
        tags: Sequence[str] = (),
        limit: int = 20,
    ) -> WikiSearchResult:
        if self._fallback is not None:
            return self._fallback.search(query, prefix=prefix, tags=tags, limit=limit)
        q = prepared(query, self._ci, self._limits)
        backend = FTS_BACKEND_ID
        if not q.terms:
            return WikiSearchResult(items=[], backend=backend, degraded=self._degraded)
        where: list[str] = []
        params: list[object] = []
        long_terms = [t for t in q.terms if self._fts_usable(t)]
        like_terms = [t for t in q.terms if t not in long_terms]
        if long_terms:
            suffix = "*" if self.tokenizer == _UNICODE61 else ""
            match = " AND ".join(_quote(t) + suffix for t in long_terms)
            where.append("d.id IN (SELECT rowid FROM fts WHERE fts MATCH ?)")
            params.append(match)
        for term in like_terms:
            where.append(
                "(instr(ac_fold(d.path),?)>0 OR instr(ac_fold(d.title),?)>0"
                " OR instr(ac_fold(d.meta),?)>0 OR instr(ac_fold(d.body),?)>0)"
            )
            params.extend([term] * 4)
        if prefix:
            where.append("substr(d.path,1,?)=?")
            params.extend([len(prefix), prefix])
        want = sorted({self._fold(t) for t in tags})
        if want:
            marks = ",".join("?" * len(want))
            where.append(
                f"(SELECT COUNT(*) FROM doc_tags t WHERE t.doc_id=d.id AND t.tag IN ({marks}))=?"
            )
            params.extend([*want, len(want)])
        sql = "SELECT d.id, d.path, d.title, d.meta FROM docs d WHERE " + " AND ".join(where)
        with self._lock:
            rows = self._db().execute(sql, params).fetchall()
        scored = sorted(
            ((meta_score(q.terms, self._fold, p, t, m), p, i, t) for i, p, t, m in rows),
            key=lambda s: (-s[0], s[1]),
        )
        cap = clamp_limit(limit, self._limits)
        top = scored[:cap]
        bodies = self._bodies([i for _s, _p, i, _t in top])
        items = [
            make_hit(
                path=path,
                title=title,
                body=bodies.get(rowid, ""),
                query=query,
                score=score,
                case_insensitive=self._ci,
                chars=self._limits.snippet_chars,
            )
            for score, path, rowid, title in top
        ]
        return WikiSearchResult(
            items=items, backend=backend, degraded=self._degraded, truncated=len(scored) > cap
        )

    def _fts_usable(self, folded_term: str) -> bool:
        """이 낱말을 FTS5 MATCH로 찾을 수 있는가(trigram은 3글자 이상, unicode61은 늘)."""
        return self.tokenizer != _TRIGRAM or len(folded_term) >= 3

    def _bodies(self, ids: list[int]) -> dict[int, str]:
        out: dict[int, str] = {}
        with self._lock:
            for i in range(0, len(ids), _SQL_VAR_CHUNK):
                chunk = ids[i : i + _SQL_VAR_CHUNK]
                marks = ",".join("?" * len(chunk))
                for rowid, body in self._db().execute(
                    f"SELECT id, body FROM docs WHERE id IN ({marks})", chunk
                ):
                    out[int(rowid)] = str(body)
        return out

    def close(self) -> None:
        with self._lock:
            if self._con is not None:
                self._con.close()
                self._con = None
            if self._fallback is not None:
                self._fallback.close()
