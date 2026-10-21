"""단독 실행(개발·재사용).

``python -m agent_console_mod_usage [--with ID] [--config PATH] [--port 0] [--check]``

필수 포트가 없어 혼자 켜진다. 관측값 저장소는 상태 폴더의 SQLite 파일(``console.sqlite3``)에 둔다.
실행 기록·저장소 포트가 없으면 토큰 집계는 빈 목록이다.
"""

import sys

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_usage.module import module
from agent_console_modkit import DatabaseHandle, Paths
from agent_console_modkit.standalone import run
from agent_console_store import SqliteDatabase


def _database(paths: Paths) -> DatabaseHandle:
    return SqliteDatabase.open(paths.state / "console.sqlite3")


raise SystemExit(
    run(module, argv=sys.argv[1:], error_status=HTTP_STATUS_BY_ERROR_CODE, database=_database)
)
