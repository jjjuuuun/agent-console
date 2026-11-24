"""FU.6 검색 이벤트 검색어 해시: 솔트 HMAC(기본)·솔트 없는 sha256·끄기."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from agent_console_memory import QUERY_HASH_MODES, QueryHashModes, query_hasher


def test_modes_are_known() -> None:
    assert set(QUERY_HASH_MODES) == {"hmac", "sha256", "off"}


def test_default_is_random_salt_hmac() -> None:
    calls: list[int] = []

    def fake_random(n: int) -> bytes:
        calls.append(n)
        return b"k" * n

    h = query_hasher(random_bytes=fake_random)
    assert calls == [32]
    expected = hmac.new(b"k" * 32, b"plan", hashlib.sha256).hexdigest()
    assert h("plan") == expected
    assert h("plan") != hashlib.sha256(b"plan").hexdigest()
    assert calls == [32]  # 솔트는 만들 때 한 번


def test_two_default_hashers_differ() -> None:
    assert query_hasher()("same") != query_hasher()("same")


def test_given_salt_is_stable_and_empty_salt_is_random() -> None:
    assert query_hasher("hmac", salt=b"s")("q") == query_hasher("hmac", salt=b"s")("q")
    assert query_hasher("hmac", salt=b"", random_bytes=lambda n: b"r" * n)("q") == (
        query_hasher("hmac", salt=b"r" * 32)("q")
    )


def test_sha256_and_off() -> None:
    digest = hashlib.sha256("한글".encode()).hexdigest()
    assert query_hasher(QueryHashModes.SHA256)("한글") == digest
    assert query_hasher(QueryHashModes.OFF)("q") is None


def test_unknown_mode() -> None:
    with pytest.raises(ValueError, match="unknown query hash mode"):
        query_hasher("md5")
