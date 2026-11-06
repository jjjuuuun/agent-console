"""페이지 경로 글롭(`orphan_ignore`·쓰기 규칙 `applies_to`).

규칙은 `ac-logs`의 경로 글롭과 같다(`*`·`?`는 `/`를 넘지 않음, `**/`는 0개 이상 폴더, 끝 `/**`는 그
폴더 자신과 하위). 대소문자 무시는 문법 `case_insensitive`를 따른다. 페이지 경로는 확장자가 없다.
"""

from __future__ import annotations

import re
from functools import lru_cache

__all__ = ["check_glob", "glob_match"]


@lru_cache(maxsize=1024)
def _compile(pattern: str, case_insensitive: bool) -> re.Pattern[str]:
    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("/**", i) and i + 3 == len(pattern):
            out.append("(?:/.*)?")
            i += 3
        elif pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
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
    flags = re.DOTALL | (re.IGNORECASE if case_insensitive else 0)
    return re.compile("".join(out) + r"\Z", flags)


def check_glob(pattern: object) -> str | None:
    """글롭 형식 검사. 맞으면 None, 아니면 사람이 읽는 이유(`wiki.invalid_glob` 이슈 문장).

    거부: 문자열이 아님, 빈 값, 역슬래시, 절대 경로(`/`로 시작), 제어 문자.
    """
    if not isinstance(pattern, str) or not pattern:
        return "빈 경로 모양입니다."
    if "\\" in pattern:
        return "역슬래시 대신 /를 쓰세요."
    if pattern.startswith("/"):
        return "위키 폴더 기준 상대 경로로 적으세요(/로 시작하지 않음)."
    if any(ord(c) < 32 for c in pattern):
        return "제어 문자가 들어 있습니다."
    return None


def glob_match(pattern: str, path: str, *, case_insensitive: bool = False) -> bool:
    """페이지 경로가 글롭에 맞는지. 형식이 틀린 글롭(`check_glob`)은 늘 거짓이다."""
    if check_glob(pattern) is not None:
        return False
    return _compile(pattern, case_insensitive).match(path) is not None
