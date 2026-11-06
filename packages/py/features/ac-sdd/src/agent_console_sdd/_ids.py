"""정의 id 만들기(이름 → `Slug` 모양, 겹치면 `-2`…)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection

__all__ = ["slug_id", "unique_id"]

_MAX = 120
_BAD = re.compile(r"[^A-Za-z0-9_-]+")


def slug_id(name: str, *, fallback: str) -> str:
    """이름에서 정의 id(`[A-Za-z0-9][A-Za-z0-9_-]*`)를 만든다. 남는 글자가 없으면 `fallback`."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = _BAD.sub("-", ascii_name).strip("-_").lower()[:_MAX].strip("-_")
    return slug or fallback


def unique_id(name: str, taken: Collection[str], *, fallback: str) -> str:
    """`slug_id`가 `taken`에 있으면 `-2`, `-3`…을 붙인다(대소문자 무시)."""
    base = slug_id(name, fallback=fallback)
    folded = {t.casefold() for t in taken}
    if base.casefold() not in folded:
        return base
    n = 2
    while f"{base}-{n}".casefold() in folded:
        n += 1
    return f"{base}-{n}"
