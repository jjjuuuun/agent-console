"""단독 실행(개발·재사용).

``python -m agent_console_link_memory_runs [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 메모리 저장소 서비스 모듈(``testing.memory_service_module``)을 붙인다.
실제 모듈과 함께 띄우려면 ``--with mod-memory --with mod-runs``.
"""

import sys

from agent_console_link_memory_runs.module import module
from agent_console_link_memory_runs.testing import standalone_modules
from agent_console_modkit.standalone import run

raise SystemExit(run(module, argv=sys.argv[1:], default_with=standalone_modules()))
