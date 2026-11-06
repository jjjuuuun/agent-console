"""단독 실행(개발·재사용).

``python -m agent_console_link_runs_sdd [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 가짜 실행 모듈과 메모리 스펙 서비스(``testing.standalone_modules``)를
붙인다. 실제 모듈과 함께 띄우려면 ``--with mod-runs --with mod-sdd``(실행 모듈의 필수 포트도 함께).
"""

import sys

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_runs_sdd.module import module
from agent_console_link_runs_sdd.testing import standalone_modules
from agent_console_modkit.standalone import run

raise SystemExit(
    run(
        module,
        argv=sys.argv[1:],
        default_with=standalone_modules(),
        error_status=HTTP_STATUS_BY_ERROR_CODE,
    )
)
