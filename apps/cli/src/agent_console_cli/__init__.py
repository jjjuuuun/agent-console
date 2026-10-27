"""agent-console-cli: `agent-console` 실행 명령.

- `agent-console serve …` — 서버 실행. 인자를 `agent_console_server.main`에 그대로 넘긴다
  (옵션 정의는 서버 한 곳, 모듈이 선언한 옵션 포함).
- `agent-console statusline` — Claude Code statusLine stdin JSON → 사용량 상태 줄 + 브리지 파일
  (`agent_console_usage.statusline` 호출만).
"""

from ._app import app, main

__all__ = ["app", "main"]
