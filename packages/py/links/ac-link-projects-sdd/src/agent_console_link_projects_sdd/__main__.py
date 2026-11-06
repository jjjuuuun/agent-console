"""단독 실행(개발·재사용).

``python -m agent_console_link_projects_sdd [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 빈 폴더 목록 모듈(``testing.folder_spaces_module``)을 붙인다. 실제로 쓰려면
``--with mod-projects --with mod-sdd``.
"""

import sys

from agent_console_link_projects_sdd.module import module
from agent_console_link_projects_sdd.testing import standalone_modules
from agent_console_modkit.standalone import run

raise SystemExit(run(module, argv=sys.argv[1:], default_with=standalone_modules()))
