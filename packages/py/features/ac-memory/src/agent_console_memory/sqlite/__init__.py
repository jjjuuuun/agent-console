"""메모리 SQLite 저장소(X31 구현, design §5.7R.6).

공개 API:
    - ``open_sqlite_memory_store(path)`` / ``SqliteMemoryStore``: ``MemoryStore`` 구현.
    - ``fts5_trigram_available()``: 이 SQLite에서 FTS5 trigram을 쓸 수 있는지.
    - ``schema``: 표 정의(``schema.metadata``, ``schema.SEARCH_TABLE_DDL``).
"""

from . import schema
from ._store import (
    MIN_FTS_CHARS,
    SearchBackend,
    SqliteMemoryStore,
    fts5_trigram_available,
    open_sqlite_memory_store,
)

__all__ = [
    "MIN_FTS_CHARS",
    "SearchBackend",
    "SqliteMemoryStore",
    "fts5_trigram_available",
    "open_sqlite_memory_store",
    "schema",
]
