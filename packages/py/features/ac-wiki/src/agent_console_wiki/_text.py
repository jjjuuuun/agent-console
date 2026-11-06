"""글 위치 도구: 줄 시작 위치, 코드 포인트 → UTF-16 위치, JSON으로 옮길 수 있는 값.

위치 단위(design §7R.1.3): 라이브러리 안 계산과 도구는 **코드 포인트**(파이썬 `str` 위치)를 쓰고,
계약 보기(`WikiLink.start`·`end`, `WikiTextRange`)는 **UTF-16 코드 단위**로 바꿔 준다(웹이 받은
문자열을 그대로 `slice`할 수 있게).
"""

from __future__ import annotations

import bisect
import datetime as _dt
import re
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "Utf16Map",
    "jsonable",
    "line_of",
    "line_starts",
    "to_utf16",
]

_NEWLINE = re.compile(r"\r\n|\r|\n")
_ASTRAL = re.compile("[\U00010000-\U0010ffff]")


def line_starts(text: str) -> list[int]:
    """각 줄의 시작 위치(코드 포인트). 줄바꿈은 `\\r\\n`·`\\r`·`\\n`(CommonMark와 같다).

    마지막 줄바꿈 뒤에 글자가 없어도 그 위치를 빈 줄의 시작으로 넣는다.
    """
    starts = [0]
    starts.extend(m.end() for m in _NEWLINE.finditer(text))
    return starts


def line_of(starts: Sequence[int], offset: int) -> int:
    """위치가 있는 줄 번호(1부터). `starts`는 `line_starts` 결과."""
    return bisect.bisect_right(starts, offset)


class Utf16Map:
    """코드 포인트 위치 → UTF-16 코드 단위 위치 변환(한 글에 대해 한 번 만든다).

    BMP 밖 글자(이모지 등)는 UTF-16에서 두 단위라 그 뒤 위치가 하나씩 밀린다. 그런 글자가 없으면
    변환은 그대로다(대부분의 페이지).
    """

    __slots__ = ("_astral",)

    def __init__(self, text: str) -> None:
        self._astral: list[int] = [m.start() for m in _ASTRAL.finditer(text)]

    def __call__(self, offset: int) -> int:
        """코드 포인트 위치 `offset`의 UTF-16 위치."""
        if not self._astral:
            return offset
        return offset + bisect.bisect_left(self._astral, offset)

    @property
    def identity(self) -> bool:
        """변환이 그대로인지(BMP 밖 글자가 없음)."""
        return not self._astral


def to_utf16(text: str, offset: int) -> int:
    """한 번만 바꿀 때: `text`의 코드 포인트 위치 `offset`을 UTF-16 위치로."""
    return len(text[:offset].encode("utf-16-le")) // 2


def jsonable(value: Any) -> Any:
    """YAML에서 읽은 값을 JSON으로 옮길 수 있는 값으로 바꾼다(날짜 → ISO 문자열, 그 밖 → 문자열).

    매핑 키는 문자열로 바꾼다. 목록·튜플은 목록이 된다.
    """
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, _dt.datetime | _dt.date | _dt.time):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [jsonable(v) for v in value]
    return str(value)
