"""단독 실행(개발·재사용).

``python -m agent_console_mod_definitions [--with ID] [--config PATH] [--port 0] [--check]``

정의 버전 기록은 상태 폴더의 SQLite 파일(``<state>/console.sqlite3``)에 둔다.
"""

import sys

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_definitions.module import module
from agent_console_modkit.standalone import run
from agent_console_store import SqliteDatabase

DATABASE_FILE = "console.sqlite3"

raise SystemExit(
    run(
        module,
        argv=sys.argv[1:],
        error_status=HTTP_STATUS_BY_ERROR_CODE,
        database=lambda paths: SqliteDatabase.open(paths.state / DATABASE_FILE),
    )
)
