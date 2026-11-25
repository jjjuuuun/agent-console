"""이름 → 정의 id(저장소 id 모양 `[A-Za-z0-9][A-Za-z0-9_-]*`, 겹치면 `-2`·`-3`…).

사용자가 id 없이 이름만 주고 정의를 만들 때(위키·문서 틀·스펙 등) 쓰는 같은 규칙이다.
악센트는 떼고(NFKD → ASCII), 영문자·숫자·`_`·`-` 밖의 글자 묶음은 `-` 하나로 바꾸고,
소문자로, 앞뒤 `-`·`_`를 떼고, 120자에서 자른다(뒤에 `-<번호>`를 붙여도 저장소 id 길이
128자 안). 남는 글자가 없으면 `fallback`. 번호 붙이기는 `agent_console_numbered_id.numbered_id`
하나로 하고 여기서 다시 내보낸다(이 패키지를 쓰는 기능이 같은 규칙을 import 하나로 쓰게).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection
from typing import Final

from agent_console_numbered_id import NoFreeId, numbered_id

__all__ = ["SLUG_MAX_CHARS", "NoFreeId", "numbered_id", "slug_id", "unique_id"]

SLUG_MAX_CHARS: Final = 120
"""`slug_id`가 만드는 id의 최대 글자 수(번호 꼬리 `-n` 자리를 남긴다)."""

_BAD = re.compile(r"[^A-Za-z0-9_-]+")


def slug_id(name: str, *, fallback: str) -> str:
    """이름에서 정의 id를 만든다. 남는 글자가 없으면 `fallback`(그대로 돌려준다).

    >>> slug_id("Project Notes", fallback="wiki"), slug_id("프로젝트 노트", fallback="wiki")
    ('project-notes', 'wiki')
    >>> slug_id("Café  Menü_", fallback="x")
    'cafe-menu'
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = _BAD.sub("-", ascii_name).strip("-_").lower()[:SLUG_MAX_CHARS].strip("-_")
    return slug or fallback


def unique_id(name: str, taken: Collection[str], *, fallback: str) -> str:
    """`slug_id`가 `taken`에 있으면 `-2`, `-3`…을 붙인다(대소문자 무시).

    >>> unique_id("Project Notes", ["project-notes"], fallback="wiki")
    'project-notes-2'
    >>> unique_id("x", ["X", "x-2"], fallback="wiki")
    'x-3'
    """
    folded = {t.casefold() for t in taken}
    return numbered_id(slug_id(name, fallback=fallback), lambda c: c.casefold() in folded)
