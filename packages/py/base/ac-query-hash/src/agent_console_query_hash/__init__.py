"""검색 이벤트에 남길 검색어 해시 만들기(솔트 HMAC·솔트 없는 sha256·끔).

검색어는 짧은 경우가 많아 솔트 없는 sha256이면 사전 대입으로 원문을 되찾을 수 있다. 이벤트가 DB와
로그 내보내기에 남는 쪽(예: 메모리·위키 에이전트 도구)은 기본으로 솔트 HMAC-SHA256을 쓴다. 방식은
쓰는 쪽이 데이터(설치자 설정)로 고르고, 솔트 값은 쓰는 쪽이 환경변수 등에서 읽어 넘긴다 — 이
패키지는 솔트를 저장·출력하지 않는다. 표준 라이브러리만 쓴다.

- `hmac`(기본): HMAC-SHA256(솔트, 검색어). 솔트를 주지 않으면 만들 때 무작위 32바이트 — 같은 해셔
  (보통 서버 프로세스 하나) 안에서만 같은 검색어가 같은 값이다.
- `sha256`: 솔트 없는 sha256(프로세스·설치를 넘어 같은 값이 필요할 때).
- `off`: 해시를 싣지 않는다(None).

검색어는 UTF-8(`surrogatepass`)로 바꿔 해시한다 — 짝 없는 서로게이트가 든 입력도 예외 없이 해시된다.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable, Mapping
from typing import Final

__all__ = [
    "QUERY_HASH_MODES",
    "QueryHashModes",
    "QueryHasher",
    "query_hasher",
    "query_hasher_from_env",
]

type QueryHasher = Callable[[str], str | None]
"""검색어 → 16진수 해시(None = 싣지 않음)."""

_SALT_BYTES: Final = 32


class QueryHashModes:
    """`query_hasher`의 방식 이름."""

    HMAC: Final = "hmac"
    SHA256: Final = "sha256"
    OFF: Final = "off"


QUERY_HASH_MODES: Final = (QueryHashModes.HMAC, QueryHashModes.SHA256, QueryHashModes.OFF)
"""알려진 방식(설정 검증·화면 선택지)."""


def _encode(query: str) -> bytes:
    return query.encode("utf-8", errors="surrogatepass")


def query_hasher(
    mode: str = QueryHashModes.HMAC,
    *,
    salt: bytes | None = None,
    random_bytes: Callable[[int], bytes] = secrets.token_bytes,
) -> QueryHasher:
    """검색어 해셔를 만든다.

    Args:
        mode: `QUERY_HASH_MODES` 중 하나.
        salt: `hmac` 솔트. None이거나 비면 `random_bytes(32)`(만들 때 한 번). 해셔의 repr·예외
            문구에 솔트가 드러나지 않는다.
        random_bytes: 무작위 바이트 공급(테스트에서 바꾼다).

    Returns:
        검색어 → 해시(16진수 64자) 또는 None(`off`).

    Raises:
        ValueError: 모르는 방식.

    >>> query_hasher("off")("secret plan") is None
    True
    >>> query_hasher("sha256")("a") == hashlib.sha256(b"a").hexdigest()
    True
    >>> h = query_hasher("hmac", salt=b"s")
    >>> h("a") == h("a") != query_hasher("hmac", salt=b"t")("a")
    True
    """
    if mode == QueryHashModes.OFF:
        return lambda _query: None
    if mode == QueryHashModes.SHA256:
        return lambda query: hashlib.sha256(_encode(query)).hexdigest()
    if mode == QueryHashModes.HMAC:
        key = salt if salt else random_bytes(_SALT_BYTES)

        def keyed(query: str) -> str:
            return hmac.new(key, _encode(query), hashlib.sha256).hexdigest()

        return keyed
    raise ValueError(f"unknown query hash mode: {mode!r} (known: {', '.join(QUERY_HASH_MODES)})")


def query_hasher_from_env(
    mode: str = QueryHashModes.HMAC,
    *,
    salt_env: str | None,
    environ: Mapping[str, str],
    random_bytes: Callable[[int], bytes] = secrets.token_bytes,
) -> QueryHasher:
    """설정 값(방식 + 솔트 환경변수 이름) → 검색어 해셔. 솔트 값은 설정에 두지 않는다.

    Args:
        mode: `QUERY_HASH_MODES` 중 하나.
        salt_env: `hmac` 솔트를 읽을 환경변수 이름(None·빈 문자열 = 무작위 솔트).
        environ: 환경변수(주입 — 보통 ``os.environ``).
        random_bytes: 변수가 없거나 빌 때 쓰는 무작위 바이트 공급.

    Returns:
        `query_hasher(mode, salt=<변수 값 UTF-8>)`. 변수가 없거나 비면 무작위 솔트(만들 때 한 번).

    Raises:
        ValueError: 모르는 방식(문구에 솔트 값은 없다).

    >>> env = {"MY_SALT": "s"}
    >>> query_hasher_from_env("hmac", salt_env="MY_SALT", environ=env)("a") == (
    ...     query_hasher("hmac", salt=b"s")("a")
    ... )
    True
    >>> query_hasher_from_env("off", salt_env=None, environ={})("a") is None
    True
    """
    value = environ.get(salt_env, "") if salt_env else ""
    salt = value.encode("utf-8", errors="surrogatepass") if value else None
    return query_hasher(mode, salt=salt, random_bytes=random_bytes)
