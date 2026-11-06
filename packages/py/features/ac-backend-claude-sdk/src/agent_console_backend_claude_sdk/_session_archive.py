"""Claude Code 세션 기록 보관·복원(X38 ``SessionArchive``, design §PI.4.6.4·K33-29).

Claude Code는 세션 원본을 설정 폴더(``CLAUDE_CONFIG_DIR``)의
``projects/<작업 폴더 키>/<세션>.jsonl``(+ ``<세션>/`` 아래 서브에이전트 기록)에 둔다. 키는 작업
폴더 경로에서 나온다(``agent_console_claude_format.project_key`` — 로그 출처와 같은 함수).

- 보관할 파일은 그 세션 파일과 ``<세션>/`` 아래뿐이다. 같은 폴더의 ``.credentials.json``·
  ``settings.json``·다른 세션 파일은 넣지 않는다.
- 복원은 ``projects/<지금 키>/``에만 쓴다.
- **앱 전용 자격 폴더가 있을 때만** 쓴다(``ClaudeSdkBackend.session_archive``). 없으면(단독
  사용·``auth_dir.config_dir: null``) None이라 ``~/.claude``를 읽지도 쓰지도 않는다.
"""

from __future__ import annotations

from pathlib import Path

from agent_console_claude_format import project_key
from agent_console_runtime import JsonlFolderSessionArchive

CLAUDE_PROJECTS_DIR = "projects"
"""설정 폴더 안 세션 기록 폴더 이름."""

CLAUDE_SESSION_SUFFIX = ".jsonl"
"""세션 파일 확장자."""


def claude_session_archive(
    config_dir: Path, *, projects_dir: str = CLAUDE_PROJECTS_DIR
) -> JsonlFolderSessionArchive:
    """설정 폴더(``CLAUDE_CONFIG_DIR``)의 세션 기록 보관·복원.

    >>> archive = claude_session_archive(Path("/data/app/.state/claude"))
    >>> archive.root.as_posix()
    '/data/app/.state/claude/projects'
    """
    return JsonlFolderSessionArchive(
        Path(config_dir) / projects_dir, project_key, suffix=CLAUDE_SESSION_SUFFIX
    )


__all__ = ["CLAUDE_PROJECTS_DIR", "CLAUDE_SESSION_SUFFIX", "claude_session_archive"]
