"""키·태그 글자 규칙(design §5.7R.1.1). 내보내기 파일 경로로 그대로 쓸 수 있는 키만 받는다."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from ._errors import InvalidKeyError

KEY_SEPARATOR = "/"
"""키 마디 구분자(경로 모양)."""

_FORBIDDEN_SEGMENTS = frozenset({"", ".", ".."})


def _has_control(text: str) -> bool:
    return any(unicodedata.category(ch) in {"Cc", "Cf", "Zl", "Zp"} for ch in text)


def check_key(key: str, *, max_chars: int) -> str:
    """키 글자 규칙을 검사하고 그대로 돌려준다.

    규칙: 비어 있지 않음, `max_chars` 이하, 앞뒤 `/` 없음, 빈 마디·`.`·`..` 마디 없음, 제어 문자
    없음, 역슬래시 없음(경로 공격 방지), 마디 앞뒤 공백 없음.

    Args:
        key: 검사할 키.
        max_chars: 최대 글자 수.

    Returns:
        같은 키.

    Raises:
        InvalidKeyError: 규칙에 맞지 않을 때(메시지에 키 원문을 싣지 않는다).

    >>> check_key("결정/api-버전", max_chars=256)
    '결정/api-버전'
    """
    if not isinstance(key, str) or not key:
        raise InvalidKeyError("키가 비어 있다")
    if len(key) > max_chars:
        raise InvalidKeyError(f"키가 {max_chars}자를 넘는다")
    if _has_control(key) or "\\" in key:
        raise InvalidKeyError("키에 제어 문자나 역슬래시가 있다")
    for segment in key.split(KEY_SEPARATOR):
        if segment in _FORBIDDEN_SEGMENTS:
            raise InvalidKeyError("키에 빈 마디나 '.'·'..' 마디가 있다(앞뒤 '/' 포함)")
        if segment != segment.strip():
            raise InvalidKeyError("키 마디 앞뒤에 공백이 있다")
    return key


def check_tags(tags: Iterable[str], *, max_tags: int, max_chars: int) -> list[str]:
    """태그 목록을 검사하고 순서를 지켜 중복을 뺀 목록을 돌려준다.

    Raises:
        InvalidKeyError: 빈 태그·제어 문자·글자 수·개수 초과.

    >>> check_tags(["a", "b", "a"], max_tags=8, max_chars=64)
    ['a', 'b']
    """
    out: list[str] = []
    for tag in tags:
        if not isinstance(tag, str) or not tag.strip():
            raise InvalidKeyError("빈 태그가 있다")
        if len(tag) > max_chars or _has_control(tag):
            raise InvalidKeyError(f"태그는 제어 문자 없이 {max_chars}자 이하여야 한다")
        if tag not in out:
            out.append(tag)
    if len(out) > max_tags:
        raise InvalidKeyError(f"태그는 {max_tags}개까지다")
    return out
