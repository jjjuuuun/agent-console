"""앱 id(``host_id``): workspace 상태 폴더에 한 번 만든 임의 문자열(design §PI.4.6.5)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from pathlib import Path

from agent_console_store import atomic_write_bytes

HOST_ID_FILE = "host_id"
"""상태 폴더 안 파일 이름."""
_VALID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def new_host_id() -> str:
    """새 임의 id(uuid4 hex)."""
    return uuid.uuid4().hex


def load_host_id(path: Path, *, new_id: Callable[[], str] = new_host_id) -> str:
    """``path``의 앱 id를 읽는다. 없거나 깨졌으면 새로 만들어 쓴다.

    두 프로세스가 동시에 만들어도 하나로 모인다.

    Args:
        path: id 파일 경로(보통 ``<상태 폴더>/host_id``). 상위 폴더는 만든다.
        new_id: 새 id 공장(테스트에서 주입).

    Returns:
        앱 id.

    Raises:
        OSError: 쓸 수 없다.

    >>> import tempfile
    >>> p = Path(tempfile.mkdtemp()) / ".state" / "host_id"
    >>> first = load_host_id(p)
    >>> load_host_id(p) == first
    True
    """
    current = _read(path)
    if current:
        return current
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = new_id()
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(candidate + "\n")
        return candidate
    except FileExistsError:
        pass
    for _ in range(20):  # 다른 프로세스가 막 만들었다 - 내용이 보일 때까지 짧게 기다린다
        current = _read(path)
        if current:
            return current
    atomic_write_bytes(path, (candidate + "\n").encode("utf-8"))  # 깨진 파일은 덮어쓴다
    return candidate


def _read(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return text if _VALID.match(text) else None


__all__ = ["HOST_ID_FILE", "load_host_id", "new_host_id"]
