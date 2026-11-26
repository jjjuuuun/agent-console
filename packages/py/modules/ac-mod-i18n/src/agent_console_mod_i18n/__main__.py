"""단독 실행(개발·재사용).

``python -m agent_console_mod_i18n [--with ID] [--config PATH] [--port 0] [--check]``
"""

import sys

from agent_console_mod_i18n.module import module
from agent_console_modkit.standalone import run

raise SystemExit(run(module, argv=sys.argv[1:]))
