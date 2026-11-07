# ruff: noqa: N818
"""실행 목록 커서 페이지의 공통 부분(design §6R.2, B-11).

정렬은 ``created_at`` 내림차순, 같은 시각이면 ``id`` 내림차순이다. 커서는 마지막 행의
(``created_at``, ``id``)를 base64로 감싼 불투명 문자열이고, 다음 페이지는 그보다 *뒤*의 행이다.
그래서 페이지 사이에 새 Run이 들어오거나(맨 앞에 쌓임) 읽은 Run이 지워져도 행이 겹치거나
빠지지 않는다.
"""

from __future__ import annotations

import base64
import binascii
import json

from .errors import StoreError

MAX_PAGE_LIMIT = 1000
"""한 페이지 상한(호출자가 더 큰 값을 주면 이 값으로 줄인다)."""


class InvalidCursor(StoreError):
    """커서 문자열이 이 저장소가 만든 모양이 아니다 -> ``bad_request``."""

    code = "bad_request"


def encode_cursor(created_at: float, run_id: str) -> str:
    """마지막 행의 위치를 불투명 커서로.

    >>> decode_cursor(encode_cursor(12.5, "run-1"))
    (12.5, 'run-1')
    """
    raw = json.dumps([created_at, run_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[float, str]:
    """``encode_cursor``의 역. 모양이 틀리면 ``InvalidCursor``."""
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        created_at, run_id = data
        if not isinstance(run_id, str) or isinstance(created_at, bool):
            raise ValueError("type")
        return float(created_at), run_id
    except (binascii.Error, ValueError, TypeError, UnicodeDecodeError) as exc:
        raise InvalidCursor("invalid cursor") from exc


def clamp_limit(limit: int) -> int:
    """1 이상 ``MAX_PAGE_LIMIT`` 이하로."""
    return max(1, min(limit, MAX_PAGE_LIMIT))


_ASCII_FOLD = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def fold_query(text: str | None) -> str | None:
    """검색어 ``q``를 비교용으로: 앞뒤 공백을 떼고 ASCII 대문자만 소문자로. 비면 None(거르지 않음).

    SQLite ``lower``·``LIKE``가 ASCII만 접기 때문에 인메모리 구현도 같은 규칙을 쓴다(두 구현의
    결과가 같게).

    >>> fold_query("  Run-ABC ")
    'run-abc'
    >>> fold_query("Énorme") == "Énorme"
    True
    >>> fold_query("   ") is None
    True
    """
    if text is None:
        return None
    folded = text.strip().translate(_ASCII_FOLD)
    return folded or None


def fold_text(text: str) -> str:
    """대상 문자열을 ``fold_query``와 같은 규칙(ASCII만)으로 접는다."""
    return text.translate(_ASCII_FOLD)


LIKE_ESCAPE = "\\"
"""``like_contains`` 패턴의 이스케이프 문자."""


def like_contains(folded: str) -> str:
    """부분 일치 ``LIKE`` 패턴. ``%``·``_``·이스케이프 문자를 글자 그대로 찾게 이스케이프한다.

    >>> like_contains("50%_a\\\\b")
    '%50\\\\%\\\\_a\\\\\\\\b%'
    """
    escaped = (
        folded.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )
    return f"%{escaped}%"
