"""단독 실행(개발·재사용).

``python -m agent_console_link_definitions_resources [--with ID] [--config PATH] [--check]``

``--with``를 주지 않으면 ``testing.local_sources_module``(파일 저장소 + 설치된 리소스 종류)을
붙인다.
이 연동은 경로가 없고 ``definitions.checks``만 제공한다.
"""

import sys

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_definitions_resources.module import module
from agent_console_link_definitions_resources.testing import local_sources_module
from agent_console_modkit.standalone import run

raise SystemExit(
    run(
        module,
        argv=sys.argv[1:],
        default_with=[local_sources_module()],
        error_status=HTTP_STATUS_BY_ERROR_CODE,
    )
)
