"""단독 실행(개발·재사용).

``python -m agent_console_link_logs_usage [--with ID] [--config PATH] [--port 0] [--check]``

``--with``를 주지 않으면 ``testing.local_logs_query_module``(빈 표본)·``testing.local_usage_module``
(자리 채움)을 붙인다. 실제 로그·사용량 경로까지 띄우려면 ``--with mod-logs --with mod-usage``.
"""

import sys

from agent_console_link_logs_usage.module import module
from agent_console_link_logs_usage.testing import local_logs_query_module, local_usage_module
from agent_console_modkit.standalone import run

raise SystemExit(
    run(module, argv=sys.argv[1:], default_with=[local_logs_query_module(), local_usage_module()])
)
