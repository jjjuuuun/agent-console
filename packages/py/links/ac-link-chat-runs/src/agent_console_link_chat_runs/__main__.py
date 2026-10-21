"""단독 실행(개발·재사용).

``python -m agent_console_link_chat_runs [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 ``testing.standalone_modules``(메모리 대화 서비스 + 가짜 실행 시작)를
붙인다.
실제 기능 모듈과 함께 띄우려면 ``--with mod-chat --with mod-runs --with mod-definitions``.
"""

import sys

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_chat_runs.module import module
from agent_console_link_chat_runs.testing import standalone_modules
from agent_console_modkit.standalone import run

raise SystemExit(
    run(
        module,
        argv=sys.argv[1:],
        default_with=standalone_modules(),
        error_status=HTTP_STATUS_BY_ERROR_CODE,
    )
)
