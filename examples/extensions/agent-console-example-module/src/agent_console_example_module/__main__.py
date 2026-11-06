"""단독 실행.

``python -m agent_console_example_module [--with ID] [--config PATH] [--port 0] [--check]``
"""

import sys

from agent_console_example_module.standalone import main

raise SystemExit(main(sys.argv[1:]))
