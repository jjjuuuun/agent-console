"""경로 글롭(`**` 지원). 출처 포함·제외 패턴과 프로젝트 묶기 규칙이 같은 규칙을 쓴다.

규칙은 `agent-console-path-glob`이다. 여기서는 패턴과 경로를 `normalize_path`로 맞춘 뒤
(역슬래시 → `/`, 끝 `/` 떼기) 대소문자를 구분해 비교한다.
"""

from __future__ import annotations

from agent_console_path_glob import glob_match as _glob_match
from agent_console_path_glob import normalize_path

__all__ = ["glob_match", "normalize_path"]


def glob_match(pattern: str, path: str) -> bool:
    """경로가 글롭에 맞는지(대소문자 구분).

    - `*`·`?`: `/`를 넘지 않는다.
    - `**/`: 0개 이상의 폴더. 끝의 `/**`: 그 폴더 자신과 모든 하위.
    - 역슬래시는 `/`로 바꿔 비교한다(Windows 경로).
    """
    return _glob_match(normalize_path(pattern), normalize_path(path))
