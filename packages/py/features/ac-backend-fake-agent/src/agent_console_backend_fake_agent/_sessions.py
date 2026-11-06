"""가짜 세션 기록 파일(X38 보관·복원 흉내, design §PI.4.6.4).

설치자 설정 ``session_dir``을 주면 실행마다 ``<session_dir>/<cwd 키>/<세션>.jsonl``에 한 줄을
더하고, 이어 쓰는 요청(``AgentRequest.session``)인데 그 파일이 없으면 실패한다(실제 백엔드가
세션 기록을 못 찾는 경우 흉내). 보관·복원은 ``agent_console_runtime.JsonlFolderSessionArchive``를
그대로 쓴다. 키는 작업 폴더 절대 경로의 해시다(실제 백엔드 규칙과 무관한 테스트용).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from agent_console_runtime import JsonlFolderSessionArchive, safe_name

FAKE_SESSION_MISSING_CODE = "fake.session_missing"
"""이어 쓸 세션 기록 파일이 없을 때 실패 코드."""

FAKE_SESSION_SUFFIX = ".jsonl"


def fake_session_key(cwd: str) -> str:
    """작업 폴더 → 키 폴더 이름(``k-`` + 절대 경로 해시 앞 24자).

    >>> fake_session_key("/work/a") == fake_session_key("/work/a"), fake_session_key("/w")[:2]
    (True, 'k-')
    """
    digest = hashlib.sha256(os.path.abspath(cwd).encode("utf-8")).hexdigest()
    return "k-" + digest[:24]


def fake_session_archive(root: Path) -> JsonlFolderSessionArchive:
    """``root`` 아래 가짜 세션 기록의 보관·복원."""
    return JsonlFolderSessionArchive(root, fake_session_key, suffix=FAKE_SESSION_SUFFIX)


def session_file(root: Path, cwd: str, session_id: str) -> Path | None:
    """그 세션 파일 경로(이름이 안전하지 않으면 None)."""
    if not safe_name(session_id):
        return None
    return root / fake_session_key(cwd) / f"{session_id}{FAKE_SESSION_SUFFIX}"


def append_turn(path: Path, record: dict[str, object]) -> None:
    """세션 파일에 한 줄 더한다(폴더가 없으면 만든다)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


__all__ = [
    "FAKE_SESSION_MISSING_CODE",
    "FAKE_SESSION_SUFFIX",
    "append_turn",
    "fake_session_archive",
    "fake_session_key",
    "session_file",
]
