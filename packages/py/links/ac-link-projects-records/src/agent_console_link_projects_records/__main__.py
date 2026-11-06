"""단독 실행(개발·재사용).

``python -m agent_console_link_projects_records [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 빈 폴더 목록 모듈(``testing.folder_spaces_module``)을 붙인다.
실제 프로젝트와 함께 띄우려면 ``--with mod-projects``.
"""

import sys

from agent_console_link_projects_records.module import module
from agent_console_link_projects_records.testing import standalone_modules
from agent_console_modkit.standalone import run

raise SystemExit(run(module, argv=sys.argv[1:], default_with=standalone_modules()))
