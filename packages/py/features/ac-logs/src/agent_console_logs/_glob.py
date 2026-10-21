"""경로 글롭(`**` 지원). 출처 포함·제외 패턴과 프로젝트 묶기 규칙이 같은 규칙을 쓴다."""

from __future__ import annotations

import re
from functools import lru_cache

__all__ = ["glob_match", "normalize_path"]


def normalize_path(path: str) -> str:
    """비교용 경로: 역슬래시를 `/`로 바꾸고 끝 `/`를 뗀다(루트 `/`는 유지)."""
    value = path.replace("\\", "/")
    while len(value) > 1 and value.endswith("/"):
        value = value[:-1]
    return value


@lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern[str]:
    pat = normalize_path(pattern)
    out: list[str] = []
    i = 0
    while i < len(pat):
        ch = pat[i]
        if pat.startswith("/**", i) and i + 3 == len(pat):
            out.append("(?:/.*)?")  # `/proj/**` 는 `/proj` 자신도 포함
            i += 3
        elif pat.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif ch == "*":
            out.append("[^/]*")
            i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    return re.compile("".join(out) + r"\Z", re.DOTALL)


def glob_match(pattern: str, path: str) -> bool:
    """경로가 글롭에 맞는지(대소문자 구분).

    - `*`·`?`: `/`를 넘지 않는다.
    - `**/`: 0개 이상의 폴더. 끝의 `/**`: 그 폴더 자신과 모든 하위.
    - 역슬래시는 `/`로 바꿔 비교한다(Windows 경로).
    """
    return _compile(pattern).match(normalize_path(path)) is not None
