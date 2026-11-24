"""검색어 해셔: 솔트 HMAC(기본)·솔트 없는 sha256·끄기."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from agent_console_query_hash import (
    QUERY_HASH_MODES,
    QueryHashModes,
    query_hasher,
    query_hasher_from_env,
)


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


def test_lone_surrogate_is_hashed() -> None:
    raw = "a\ud800".encode("utf-8", errors="surrogatepass")
    assert query_hasher("sha256")("a\ud800") == hashlib.sha256(raw).hexdigest()
    assert query_hasher("hmac", salt=b"s")("a\ud800") == (
        hmac.new(b"s", raw, hashlib.sha256).hexdigest()
    )


def test_salt_is_not_exposed() -> None:
    h = query_hasher("hmac", salt=b"top-secret-salt")
    assert "top-secret-salt" not in repr(h)
    with pytest.raises(ValueError, match="unknown query hash mode") as info:
        query_hasher("md5", salt=b"top-secret-salt")
    assert "top-secret-salt" not in str(info.value)


def test_from_env_reads_salt_variable() -> None:
    env = {"SALT": "abc"}
    h = query_hasher_from_env("hmac", salt_env="SALT", environ=env)
    assert h("q") == query_hasher("hmac", salt=b"abc")("q")


@pytest.mark.parametrize(
    ("salt_env", "environ"),
    [(None, {"SALT": "abc"}), ("", {"SALT": "abc"}), ("SALT", {}), ("SALT", {"SALT": ""})],
)
def test_from_env_without_value_uses_random_salt(
    salt_env: str | None, environ: dict[str, str]
) -> None:
    h = query_hasher_from_env(
        "hmac", salt_env=salt_env, environ=environ, random_bytes=lambda n: b"r" * n
    )
    assert h("q") == query_hasher("hmac", salt=b"r" * 32)("q")


def test_from_env_other_modes() -> None:
    env = {"SALT": "abc"}
    assert query_hasher_from_env("sha256", salt_env="SALT", environ=env)("q") == (
        hashlib.sha256(b"q").hexdigest()
    )
    assert query_hasher_from_env("off", salt_env="SALT", environ=env)("q") is None
    with pytest.raises(ValueError, match="unknown query hash mode") as info:
        query_hasher_from_env("md5", salt_env="SALT", environ=env)
    assert "abc" not in str(info.value)
