"""단독 실행(개발·재사용).

``python -m agent_console_link_logs_trace [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 ``testing.local_logs_module``(빈 메모리 색인)을 붙인다. 실제 로그를 보려면
``--with mod-logs``로 로그 모듈과 함께 띄운다.
"""

import sys

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_logs_trace.module import module
from agent_console_link_logs_trace.testing import local_logs_module
from agent_console_modkit.standalone import run

raise SystemExit(
    run(
        module,
        argv=sys.argv[1:],
        default_with=[local_logs_module()],
        error_status=HTTP_STATUS_BY_ERROR_CODE,
    )
)
