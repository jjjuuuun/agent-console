"""단독 실행(개발·재사용).

``python -m agent_console_mod_projects [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 ``testing.local_definitions_module``(워크스페이스 파일 저장소)을 붙인다
(정의 옮기기·범위 검사까지 동작). 참조 추출(``definitions.references``)은 없으므로 범위 검사는
"참조를 알 수 없음" 정보를 낸다.
"""

import sys

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_projects.module import module
from agent_console_mod_projects.testing import local_definitions_module
from agent_console_modkit.standalone import run

raise SystemExit(
    run(
        module,
        argv=sys.argv[1:],
        default_with=[local_definitions_module()],
        error_status=HTTP_STATUS_BY_ERROR_CODE,
    )
)
