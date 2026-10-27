"""단독 실행(개발·재사용).

``python -m agent_console_mod_architecture [--with ID] [--config PATH] [--port 0] [--check]``

자세한 동작은 ``agent_console_mod_architecture.standalone``.
"""

import sys

from agent_console_mod_architecture.standalone import main

raise SystemExit(main(sys.argv[1:]))
