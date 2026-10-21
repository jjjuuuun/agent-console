"""단독 실행(개발·재사용).

``python -m agent_console_mod_chat [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 ``testing.local_definitions_module``(워크스페이스 파일 저장소)을 붙인다.
대화·대기열은 상태 폴더의 SQLite 파일(``<state>/console.sqlite3``)에 둔다. 턴 실행까지 띄우려면
``--with mod-definitions --with mod-runs --with link-chat-runs``.
"""

import sys

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_chat.module import module
from agent_console_mod_chat.testing import local_definitions_module
from agent_console_modkit.standalone import run
from agent_console_store import SqliteDatabase

DATABASE_FILE = "console.sqlite3"

raise SystemExit(
    run(
        module,
        argv=sys.argv[1:],
        default_with=[local_definitions_module()],
        error_status=HTTP_STATUS_BY_ERROR_CODE,
        database=lambda paths: SqliteDatabase.open(paths.state / DATABASE_FILE),
    )
)
