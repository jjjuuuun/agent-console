"""단독 실행(개발·재사용).

``python -m agent_console_link_projects_runs [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 빈 메모리 프로젝트 모듈(``testing.memory_projects_module``)을 붙인다.
실제 프로젝트·실행과 함께 띄우려면 ``--with mod-projects --with mod-runs``.
"""

import sys

from agent_console_link_projects_runs.module import module
from agent_console_link_projects_runs.testing import standalone_modules
from agent_console_modkit.standalone import run

raise SystemExit(run(module, argv=sys.argv[1:], default_with=standalone_modules()))
