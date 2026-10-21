"""단독 실행(개발·재사용).

``python -m agent_console_link_runs_teams [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 ``mod-runs``(설치돼 있어야 한다)와 그 단독 실행용 로컬 정의 모듈을 붙인다.
정의 모듈과 함께 띄우려면 ``--with mod-runs --with mod-definitions``.
"""

import sys

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_runs_teams.module import module
from agent_console_link_runs_teams.testing import standalone_modules
from agent_console_modkit.standalone import run
from agent_console_store import SqliteDatabase

DATABASE_FILE = "console.sqlite3"

raise SystemExit(
    run(
        module,
        argv=sys.argv[1:],
        default_with=standalone_modules(),
        error_status=HTTP_STATUS_BY_ERROR_CODE,
        database=lambda paths: SqliteDatabase.open(paths.state / DATABASE_FILE),
    )
)
