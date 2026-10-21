"""단독 실행(개발·재사용).

``python -m agent_console_link_logs_runs [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 ``testing.local_logs_module``(메모리 색인)·``testing.runs_module``
(빈 메모리 실행 기록)을 붙인다. 실제 실행·로그와 함께 띄우려면
``--with mod-logs --with mod-runs --with mod-definitions``.
"""

import sys

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_logs_runs.module import module
from agent_console_link_logs_runs.testing import MemoryRunRecords, local_logs_module, runs_module
from agent_console_modkit.standalone import run

raise SystemExit(
    run(
        module,
        argv=sys.argv[1:],
        default_with=[local_logs_module(), runs_module(MemoryRunRecords())],
        error_status=HTTP_STATUS_BY_ERROR_CODE,
    )
)
