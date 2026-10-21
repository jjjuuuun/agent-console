"""내보내기 상대 경로 검사(운영체제와 무관하게 같은 규칙: Windows에서도 안전한 이름만)."""

from __future__ import annotations

import re
from typing import Final

__all__ = ["path_problem"]

_FORBIDDEN_CHARS: Final = frozenset('<>:"|?*\\')
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$", re.IGNORECASE)


def path_problem(path: str, *, allow_empty: bool = False) -> str | None:
    """상대 경로(`/` 구분)의 문제 설명. 안전하면 None.

    거부: 빈 경로(`allow_empty`가 아니면), 절대 경로, `.`·`..`·빈 구성요소, 역슬래시·`:` 등
    Windows 금지 문자, 제어 문자, 예약 이름(`CON`, `NUL.txt` …), 끝이 점·공백인 구성요소.
    """
    if path == "":
        return None if allow_empty else "경로가 비어 있습니다"
    if path.startswith("/"):
        return "절대 경로는 쓸 수 없습니다"
    for part in path.split("/"):
        if part in ("", ".", ".."):
            return "빈 구성요소·`.`·`..`는 쓸 수 없습니다"
        if any(ch in _FORBIDDEN_CHARS or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in part):
            return "쓸 수 없는 문자가 있습니다"
        if _RESERVED.match(part):
            return "예약된 이름은 쓸 수 없습니다"
        if part[-1] in (".", " "):
            return "점·공백으로 끝나는 이름은 쓸 수 없습니다"
    return None
