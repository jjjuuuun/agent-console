"""FU.12 설치자 설정 → 위키 검색어 해셔(``query_hash``·``query_hash_salt_env``)."""

from __future__ import annotations

import hashlib
import hmac
import json
import typing
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_console_mod_wiki import WIKI_SERVICE, WikiModuleSettings, WikiService, module
from agent_console_mod_wiki.module import search_query_hasher
from agent_console_mod_wiki.ports import WikiServicePort
from agent_console_mod_wiki.testing import static_settings_module
from agent_console_modkit import BaseServices, ExtensionRegistries, ModulesConfig, Paths, assemble
from agent_console_wiki import QUERY_HASH_MODES

ENV = "TEST_WIKI_QUERY_SALT"
SALT = "wiki-salt-value-fu12"


def test_setting_choices_match_library_modes() -> None:
    field = WikiModuleSettings.model_fields["query_hash"]
    assert set(typing.get_args(field.annotation)) == set(QUERY_HASH_MODES)
    assert WikiModuleSettings().query_hash == "hmac"
    assert WikiModuleSettings().query_hash_salt_env is None
    with pytest.raises(ValidationError):
        WikiModuleSettings.model_validate({"query_hash": "md5"})
    with pytest.raises(ValidationError):
        WikiModuleSettings.model_validate({"query_hash_salt_env": ""})


def test_salt_from_environment() -> None:
    cfg = WikiModuleSettings(query_hash_salt_env=ENV)
    got = search_query_hasher(cfg, {ENV: SALT})("q")
    assert got == hmac.new(SALT.encode(), b"q", hashlib.sha256).hexdigest()
    assert search_query_hasher(cfg, {ENV: SALT})("q") == got


def test_missing_or_empty_salt_is_random_per_hasher() -> None:
    cfg = WikiModuleSettings(query_hash_salt_env=ENV)
    for environ in ({}, {ENV: ""}):
        a = search_query_hasher(cfg, environ)
        b = search_query_hasher(cfg, environ)
        assert a("q") == a("q") != b("q")


def test_plain_and_off() -> None:
    plain = WikiModuleSettings(query_hash="sha256", query_hash_salt_env=ENV)
    assert search_query_hasher(plain, {ENV: "ignored"})("q") == hashlib.sha256(b"q").hexdigest()
    assert search_query_hasher(WikiModuleSettings(query_hash="off"), {})("q") is None


def _service(tmp_path: Path, options: dict[str, object], environ: dict[str, str]) -> WikiService:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=ExtensionRegistries(),
        environ=environ,
    )
    assembly = assemble(
        [module, static_settings_module({})],
        ModulesConfig(options={"mod-wiki": options}),
        base=base,
    )
    found = assembly.port(WIKI_SERVICE)
    assert isinstance(found, WikiService)
    assert isinstance(found, WikiServicePort)
    return found


def test_module_builds_service_hasher_from_settings(tmp_path: Path) -> None:
    options: dict[str, object] = {"query_hash": "hmac", "query_hash_salt_env": ENV}
    service = _service(tmp_path / "a", options, {ENV: SALT})
    assert service.query_hash("q") == hmac.new(SALT.encode(), b"q", hashlib.sha256).hexdigest()
    off = _service(tmp_path / "b", {"query_hash": "off"}, {})
    assert off.query_hash("q") is None
    default = _service(tmp_path / "c", {}, {ENV: SALT})
    assert default.query_hash("q") not in (None, hashlib.sha256(b"q").hexdigest())


def test_salt_value_not_in_settings_dump_or_schema() -> None:
    cfg = WikiModuleSettings(query_hash_salt_env=ENV)
    dumped = json.dumps(cfg.model_dump(mode="json"))
    assert ENV in dumped
    assert SALT not in dumped
    schema = WikiModuleSettings.model_json_schema()
    props = schema["properties"]
    assert props["query_hash"]["title"]
    assert props["query_hash_salt_env"]["description"]
