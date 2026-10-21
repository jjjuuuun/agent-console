"""웹 빌드 산출물 정적 서빙(SPA). 빌드가 없으면 안내 페이지를 보여 준다."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response

from agent_console_contracts import ErrorCodes, ErrorInfo

from ._errors import error_response

PACKAGED_WEB_DIR = Path(__file__).parent / "web"
"""배포 패키지에 웹 빌드를 넣을 자리(R10.1). 없으면 설정 `web.static_dir`을 쓴다."""

RESERVED_SEGMENTS = ("api", "ws")
"""서버 자신의 프로토콜 경로(첫 경로 조각). 정확히 같거나 `<이름>/`로 시작할 때만 막는다
(`wsfoo`는 웹 경로)."""


def is_reserved_path(path: str) -> bool:
    """`path`(앞 `/` 없음)가 서버 예약 경로(`api`, `api/…`, `ws`, `ws/…`)인지."""
    first = path.split("/", 1)[0]
    return first in RESERVED_SEGMENTS


_MISSING_PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Console</title>
<style>
  :root { color-scheme: light dark; }
  body {
    margin: 0; padding: 32px 16px;
    font-family: 'Pretendard', 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo',
      system-ui, sans-serif;
    line-height: 1.6; word-break: keep-all; overflow-wrap: break-word;
    background: Canvas; color: CanvasText;
  }
  main { max-width: 640px; margin: 0 auto; }
  code { font-family: ui-monospace, Consolas, monospace; overflow-wrap: anywhere; }
</style>
</head>
<body>
<main>
  <h1>Agent Console 서버가 실행 중입니다</h1>
  <p>웹 화면 빌드를 찾지 못했습니다.
    API(<code>/api/v1</code>)와 WebSocket(<code>/ws</code>)은 정상 동작합니다.</p>
  <ol>
    <li>웹 빌드: <code>pnpm --filter @agent-console/web build</code></li>
    <li>설정 <code>agent-console.yaml</code>의 <code>web.static_dir</code>(또는 환경변수
      <code>AGENT_CONSOLE_WEB_DIR</code>)에 빌드 폴더(예: <code>apps/web/dist</code>)를 지정</li>
    <li>서버를 다시 시작</li>
  </ol>
</main>
</body>
</html>
"""


def resolve_static_dir(configured: Path | None) -> Path | None:
    """설정 폴더 → 패키지 포함 빌드 순으로, `index.html`이 있는 폴더를 고른다."""
    for candidate in (configured, PACKAGED_WEB_DIR):
        if candidate is not None and (candidate / "index.html").is_file():
            return candidate.resolve()
    return None


def mount_static(app: FastAPI, static_dir: Path | None) -> None:
    """`GET /{path}`: 파일이 있으면 그 파일, 없으면 `index.html`(클라이언트 라우팅).

    `/api/…`·`/ws`는 여기서 처리하지 않는다(모르는 API 경로는 JSON 404).
    """

    @app.get("/{path:path}", include_in_schema=False)
    async def static(path: str) -> Response:
        if is_reserved_path(path):
            return error_response(
                ErrorInfo(code=ErrorCodes.NOT_FOUND, message="없는 경로입니다"), 404
            )
        if static_dir is None:
            return HTMLResponse(_MISSING_PAGE, headers={"Cache-Control": "no-store"})
        target = (static_dir / path).resolve() if path else static_dir / "index.html"
        if path and target.is_relative_to(static_dir) and target.is_file():
            return FileResponse(target)
        return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-cache"})
