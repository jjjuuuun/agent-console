"""경로 글롭(`**` 지원): 패턴 → 정규식, 경로가 패턴에 맞는지.

규칙(모든 사용처가 같다):

- `*`·`?`: `/`를 넘지 않는다(`?`는 글자 하나).
- `**/`: 0개 이상의 폴더. 끝의 `/**`: 그 폴더 자신과 모든 하위. 그 밖의 `**`: 아무 글자(`/` 포함).
- 나머지 글자는 그대로 비교한다(정규식 특수 문자도 글자 그대로).
- 대소문자는 기본으로 구분하고 `case_insensitive=True`로 무시한다.

경로·패턴을 바꾸지 않는다. 역슬래시 경로(Windows)를 같은 규칙으로 비교하려면 `normalize_path`를 먼저
부른다. 형식 검사(빈 값·절대 경로 거부 등)는 쓰는 쪽 규칙이라 여기 없다.

공개 API: `glob_match`, `glob_regex`, `normalize_path`.
"""

from __future__ import annotations

import re
from functools import lru_cache

__all__ = ["glob_match", "glob_regex", "normalize_path"]

_CACHE_SIZE = 1024


def normalize_path(path: str) -> str:
    """비교용 경로: 역슬래시를 `/`로 바꾸고 끝 `/`를 뗀다(루트 `/`는 유지).

    >>> normalize_path("docs\\\\a\\\\"), normalize_path("/"), normalize_path("a//")
    ('docs/a', '/', 'a')
    """
    value = path.replace("\\", "/")
    while len(value) > 1 and value.endswith("/"):
        value = value[:-1]
    return value


@lru_cache(maxsize=_CACHE_SIZE)
def glob_regex(pattern: str, *, case_insensitive: bool = False) -> re.Pattern[str]:
    """글롭 → 컴파일한 정규식(경로 전체가 맞아야 한다, `match`로 쓴다). 같은 인자는 캐시한다.

    >>> glob_regex("a/**/b").pattern
    'a/(?:.*/)?b\\\\Z'
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("/**", i) and i + 3 == len(pattern):
            out.append("(?:/.*)?")  # `/proj/**`는 `/proj` 자신도 포함
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


def glob_match(pattern: str, path: str, *, case_insensitive: bool = False) -> bool:
    """경로가 글롭에 맞는지(패턴·경로를 바꾸지 않고 비교한다).

    Args:
        pattern: 글롭.
        path: 비교할 경로(`/` 구분).
        case_insensitive: 참이면 대소문자를 무시한다.

    Returns:
        경로 전체가 패턴에 맞으면 참.

    >>> glob_match("**/*.md", "a/b.md"), glob_match("*.md", "a/b.md")
    (True, False)
    >>> glob_match("/proj/**", "/proj"), glob_match("/proj/**", "/project")
    (True, False)
    """
    return glob_regex(pattern, case_insensitive=case_insensitive).match(path) is not None
