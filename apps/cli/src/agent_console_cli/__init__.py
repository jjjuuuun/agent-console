"""agent-console-cli 앱: `agent-console` 명령.

- `agent-console serve` — 서버 실행(`agent_console_server.load_settings`·`serve` 호출만).
- `agent-console statusline` — Claude Code statusLine stdin JSON → 사용량 상태 줄 + 브리지 파일
  (`agent_console_usage.statusline` 호출만).

`console`(WS 콘솔 클라이언트)은 2R.20에서 삭제했다(design §R5.2).
"""

from ._app import app, main

__all__ = ["app", "main"]
