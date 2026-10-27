"""단독 실행(개발·재사용).

``python -m agent_console_link_logs_architecture [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 ``testing.local_logs_module``(빈 메모리 색인)과
``testing.local_catalog_module``(패키지 기본 프로필)을 붙인다. 실제 로그·프로필은
``--with mod-logs --with mod-architecture``로 함께 띄운다.
"""

import sys

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_logs_architecture.module import module
from agent_console_link_logs_architecture.testing import local_catalog_module, local_logs_module
from agent_console_modkit.standalone import run

raise SystemExit(
    run(
        module,
        argv=sys.argv[1:],
        default_with=[local_logs_module(), local_catalog_module()],
        error_status=HTTP_STATUS_BY_ERROR_CODE,
    )
)
