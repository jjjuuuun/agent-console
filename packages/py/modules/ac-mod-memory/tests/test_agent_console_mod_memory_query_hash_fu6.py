"""FU.6 설치자 설정 → 검색어 해셔(``query_hash``·``query_hash_salt_env``)."""

from __future__ import annotations

import hashlib
import hmac
import typing

import pytest
from pydantic import ValidationError

from agent_console_memory import QUERY_HASH_MODES
from agent_console_mod_memory import MemoryModuleSettings
from agent_console_mod_memory.module import search_query_hasher

ENV = "TEST_MEMORY_QUERY_SALT"


def test_setting_choices_match_library_modes() -> None:
    field = MemoryModuleSettings.model_fields["query_hash"]
    assert set(typing.get_args(field.annotation)) == set(QUERY_HASH_MODES)
    assert MemoryModuleSettings().query_hash == "hmac"
    with pytest.raises(ValidationError):
        MemoryModuleSettings.model_validate({"query_hash": "md5"})


def test_salt_from_environment() -> None:
    cfg = MemoryModuleSettings(query_hash_salt_env=ENV)
    got = search_query_hasher(cfg, {ENV: "s3"})("q")
    assert got == hmac.new(b"s3", b"q", hashlib.sha256).hexdigest()
    assert search_query_hasher(cfg, {ENV: "s3"})("q") == got


def test_missing_or_empty_salt_is_random_per_hasher() -> None:
    cfg = MemoryModuleSettings(query_hash_salt_env=ENV)
    for environ in ({}, {ENV: ""}):
        a = search_query_hasher(cfg, environ)
        b = search_query_hasher(cfg, environ)
        assert a("q") == a("q") != b("q")
    default = MemoryModuleSettings()
    assert search_query_hasher(default, {ENV: "s3"})("q") != (
        search_query_hasher(cfg, {ENV: "s3"})("q")
    )


def test_plain_and_off() -> None:
    plain = MemoryModuleSettings(query_hash="sha256", query_hash_salt_env=ENV)
    assert search_query_hasher(plain, {ENV: "ignored"})("q") == hashlib.sha256(b"q").hexdigest()
    assert search_query_hasher(MemoryModuleSettings(query_hash="off"), {})("q") is None
