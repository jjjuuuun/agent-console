"""Claude Code 폴더 규칙(경로 이름만, 파일을 읽거나 쓰지 않는다).

- ``project_key``: 작업 폴더 경로 → 설정 폴더 ``projects`` 아래 폴더 이름. 로그 출처
  (``agent-console-logs-claude``)와 실행 백엔드의 세션 보관(``agent-console-backend-claude-sdk``,
  design §PI.4.6.4 X38)이 같은 함수를 쓴다(5.7R.33y3에서 로그 출처에서 이리로 옮김).
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["project_key"]


def project_key(folder: str | Path, *, keep: str = "", replacement: str = "-") -> str:
    """작업 폴더 경로 → Claude Code `projects` 아래 폴더 이름(영문자·숫자·`keep` 밖 글자를 바꿈).

    Claude Code는 이 규칙을 문서로 정하지 않았다(사용자 보고·도구 구현 기준). 로그 출처는 설정
    `project_key_keep`·`project_key_replacement`로 바꾼다. 이름은 손실 변환이라 되돌리지 않는다.

    >>> project_key("/work/demo"), project_key("/home/u/my.app_x")
    ('-work-demo', '-home-u-my-app-x')
    >>> project_key("C:\\\\git\\\\cc-plus")
    'C--git-cc-plus'
    """
    text = str(folder)
    return "".join(
        ch if (ch.isascii() and ch.isalnum()) or ch in keep else replacement for ch in text
    )
