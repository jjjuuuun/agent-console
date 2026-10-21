"""단독 실행(개발·재사용).

``python -m agent_console_link_runs_trace [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 ``testing.local_runs_module``(상태 폴더 DB의 실행 기록 읽기)을 붙인다.
실행 모듈과 함께 띄우려면 ``--with mod-runs --with mod-definitions``.
"""

import sys

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_runs_trace.module import module
from agent_console_link_runs_trace.testing import local_runs_module
from agent_console_modkit.standalone import run
from agent_console_store import SqliteDatabase

DATABASE_FILE = "console.sqlite3"

raise SystemExit(
    run(
        module,
        argv=sys.argv[1:],
        default_with=[local_runs_module()],
        error_status=HTTP_STATUS_BY_ERROR_CODE,
        database=lambda paths: SqliteDatabase.open(paths.state / DATABASE_FILE),
    )
)
