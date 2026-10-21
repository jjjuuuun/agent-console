"""단독 실행(개발·재사용).

``python -m agent_console_link_definitions_teams [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 ``testing.local_definitions_module``(워크스페이스 파일 저장소)을 붙인다.
정의 모듈과 함께 띄우려면 ``--with mod-definitions``(리소스까지 ``--with mod-resources``).
"""

import sys

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_definitions_teams.module import module
from agent_console_link_definitions_teams.testing import local_definitions_module
from agent_console_modkit.standalone import run

raise SystemExit(
    run(
        module,
        argv=sys.argv[1:],
        default_with=[local_definitions_module()],
        error_status=HTTP_STATUS_BY_ERROR_CODE,
    )
)
