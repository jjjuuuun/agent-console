"""겹치면 ``-2``·``-3``… 붙이기: 비어 있는 id·이름 하나를 찾는다.

등록 id(프로젝트), 이름에서 만든 정의 id, 가져오기 rename, 그래프 제안의 새 노드 id, 백업 파일
이름처럼 "이미 있으면 뒤에 번호를 붙인다"는 같은 규칙을 한곳에 둔다. 무엇이 "이미 있음"인지
(대소문자 무시·저장소 조회·파일 존재)는 쓰는 쪽이 ``is_taken``으로 정한다. 표준 라이브러리만 쓴다.
"""

from __future__ import annotations

from collections.abc import Callable

__all__ = ["NoFreeId", "numbered_id"]


class NoFreeId(LookupError):  # noqa: N818 - 조회 실패 계열(LookupError)로 둔다
    """``limit``까지 번호를 붙여도 빈 이름이 없다."""


def numbered_id(
    base: str,
    is_taken: Callable[[str], bool],
    *,
    max_length: int | None = None,
    limit: int | None = None,
) -> str:
    """``base``가 비어 있으면 그대로, 아니면 ``base-2``, ``base-3``…에서 처음 빈 것.

    Args:
        base: 바라는 이름.
        is_taken: 이름 → 이미 있나(비교 방식은 쓰는 쪽이 정한다 - 예: 대소문자 무시 집합).
        max_length: 결과의 최대 글자 수. 번호를 붙일 때 ``base`` 뒤를 잘라 맞춘다(None = 자르지
            않음). ``base`` 자체는 자르지 않는다.
        limit: 시도할 번호의 상한(이 번호는 시도하지 않는다, None = 끝없이).

    Returns:
        비어 있는 이름.

    Raises:
        NoFreeId: ``limit``까지 빈 이름이 없다.

    >>> taken = {"app", "app-2"}
    >>> numbered_id("web", taken.__contains__), numbered_id("app", taken.__contains__)
    ('web', 'app-3')
    >>> folded = {"App"}
    >>> numbered_id("app", lambda c: c.casefold() in {t.casefold() for t in folded})
    'app-2'
    >>> numbered_id("abcdef", {"abcdef"}.__contains__, max_length=5)
    'abc-2'
    """
    if not is_taken(base):
        return base
    n = 2
    while limit is None or n < limit:
        suffix = f"-{n}"
        head = base if max_length is None else base[: max(0, max_length - len(suffix))]
        candidate = head + suffix
        if not is_taken(candidate):
            return candidate
        n += 1
    raise NoFreeId(f"no free name for {base!r} below -{limit}")
