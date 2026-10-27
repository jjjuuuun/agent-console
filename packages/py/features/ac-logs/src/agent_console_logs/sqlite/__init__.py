"""SQLite 로그 색인(design §4R.5).

`SqliteLogIndex`, 테이블 정의 `log_metadata`, 단독 열기 `open_log_index`, 있는 색인만 열기
`open_existing_log_index`(파일·테이블을 만들지 않는다, 도구용).

```python
>>> from agent_console_logs.sqlite import open_log_index
>>> index = open_log_index(":memory:")
>>> index.max_seq() is None
True

```

테이블은 두 길로 만든다. 서버 모듈(`ac-mod-logs`)은 마이그레이션 계보 `logs`(Alembic)로,
단독 사용은 `open_log_index`의 `create_all`로 만든다. 두 모양은 테스트로 같게 지킨다.
"""

from ._index import SqliteLogIndex
from ._open import create_log_engine, open_existing_log_index, open_log_index
from .schema import (
    OBSOLETE_INDEXES,
    TABLE_NAMES,
    log_agents,
    log_bodies,
    log_corr,
    log_cursors,
    log_events,
    log_links,
    log_metadata,
    log_search,
    log_tags,
    log_usage,
)

__all__ = [
    "OBSOLETE_INDEXES",
    "TABLE_NAMES",
    "SqliteLogIndex",
    "create_log_engine",
    "log_agents",
    "log_bodies",
    "log_corr",
    "log_cursors",
    "log_events",
    "log_links",
    "log_metadata",
    "log_search",
    "log_tags",
    "log_usage",
    "open_existing_log_index",
    "open_log_index",
]
