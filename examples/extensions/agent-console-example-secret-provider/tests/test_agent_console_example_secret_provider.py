"""단위 시험: entry point 선언·로더, 줄 규칙(데이터), 파일 없음 = 경고만,
값이 로그·예외·repr에 없음."""

from __future__ import annotations

import importlib.metadata
import logging
import os
import tomllib
from pathlib import Path

import pytest

from agent_console_example_secret_provider import (
    PROVIDER_ID,
    EnvFileSecretProvider,
    FileSecretProvider,
    default_settings_data,
    load_settings,
    parse_secret_lines,
    register,
)
from agent_console_registry import load_entry_points
from agent_console_runtime import (
    SECRET_PROVIDERS_GROUP,
    Registries,
    SecretNotFoundError,
    SecretProvider,
    SecretResolver,
    as_secret_provider,
)

ROOT = Path(__file__).resolve().parents[1]
VALUE = "file-value-zz51"
ENV = default_settings_data()["path_env"]


def _file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "secrets.env"
    path.write_text(text, encoding="utf-8")
    return path


def _all_logs(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(r.getMessage() for r in caplog.records)


def test_entry_point_declaration() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    table = data["project"]["entry-points"][SECRET_PROVIDERS_GROUP]
    assert table == {PROVIDER_ID: "agent_console_example_secret_provider:EnvFileSecretProvider"}


def test_loaded_through_the_registry_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV, str(_file(tmp_path, f"EXAMPLE_TOKEN={VALUE}\n")))
    registries = Registries()
    ep = importlib.metadata.EntryPoint(
        name=PROVIDER_ID,
        value="agent_console_example_secret_provider:EnvFileSecretProvider",
        group=SECRET_PROVIDERS_GROUP,
    )
    reports = load_entry_points(
        SECRET_PROVIDERS_GROUP,
        registries.secret_providers,
        validate=as_secret_provider,
        entry_points=[ep],
    )
    assert [r.status for r in reports] == ["loaded"]
    provider = registries.secret_providers.get(PROVIDER_ID)
    assert isinstance(provider, SecretProvider)
    assert SecretResolver([provider]).resolve("secret://example_token") == VALUE


def test_register_for_plugin_modules(tmp_path: Path) -> None:
    registries = Registries()
    register(registries)
    assert [e.key for e in registries.secret_providers.list()] == [PROVIDER_ID]


def test_line_rules() -> None:
    text = (
        "﻿# 주석\n"
        "\n"
        "A=1\n"
        "  B = two words  \n"
        'C="quoted=still"\n'
        "D='x'\n"
        "no equals sign\n"
        "bad name!=x\n"
        "A=again\n"
    )
    values, skipped = parse_secret_lines(text, load_settings())
    assert values == {"A": "again", "B": "two words", "C": "quoted=still", "D": "x"}
    assert skipped == [7, 8]
    raw, _ = parse_secret_lines('C="q"\n', load_settings({"strip_quotes": False}))
    assert raw == {"C": '"q"'}
    alt, _ = parse_secret_lines("; note\nA=1\n", load_settings({"comment_prefixes": [";"]}))
    assert alt == {"A": "1"}


def test_bad_options_name_the_key_only() -> None:
    with pytest.raises(ValueError, match="name_pattern"):
        load_settings({"name_pattern": "("})
    with pytest.raises(ValueError, match="unknown"):
        load_settings({"unknown": True})


def test_lookup_exact_then_upper(tmp_path: Path) -> None:
    provider = FileSecretProvider(_file(tmp_path, f"EXAMPLE_TOKEN={VALUE}\nmixed=m\n"))
    assert provider.get_secret("EXAMPLE_TOKEN") == VALUE
    assert provider.get_secret("example_token") == VALUE
    assert provider.get_secret("mixed") == "m"
    assert provider.get_secret("nothing") is None
    strict = FileSecretProvider(provider.path, settings=load_settings({"upper_fallback": False}))
    assert strict.get_secret("example_token") is None


def test_missing_file_is_a_single_warning_then_picks_up_the_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "later.env"
    provider = FileSecretProvider(path)
    with caplog.at_level(logging.WARNING):
        assert provider.get_secret("EXAMPLE_TOKEN") is None
        assert provider.get_secret("EXAMPLE_TOKEN") is None
    assert len(caplog.records) == 1
    assert "비밀 파일이 없습니다" in caplog.records[0].getMessage()
    path.write_text(f"EXAMPLE_TOKEN={VALUE}\n", encoding="utf-8")
    assert provider.get_secret("EXAMPLE_TOKEN") == VALUE  # 재시작 없이


def test_changed_file_is_reread(tmp_path: Path) -> None:
    path = _file(tmp_path, "EXAMPLE_TOKEN=old-value-1\n")
    provider = FileSecretProvider(path)
    assert provider.get_secret("EXAMPLE_TOKEN") == "old-value-1"
    path.write_text(f"EXAMPLE_TOKEN={VALUE}\n# 크기도 바뀐다\n", encoding="utf-8")
    os.utime(path, ns=(1, 1))  # 시각 해상도가 낮은 파일 시스템에서도 바뀜이 보이게
    assert provider.get_secret("EXAMPLE_TOKEN") == VALUE


def test_values_never_appear_in_logs_repr_or_errors(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _file(tmp_path, f"EXAMPLE_TOKEN={VALUE}\nbroken line with {VALUE}\n")
    provider = FileSecretProvider(path)
    with caplog.at_level(logging.DEBUG):
        assert provider.get_secret("EXAMPLE_TOKEN") == VALUE
        resolver = SecretResolver([provider])
        with pytest.raises(SecretNotFoundError) as caught:
            resolver.resolve("secret://not_there")
    logs = _all_logs(caplog)
    assert "2번째 줄을 건너뜁니다" in logs
    for text in (logs, repr(provider), str(caught.value)):
        assert VALUE not in text
        assert "EXAMPLE_TOKEN" not in text  # 이름도 로그에 넣지 않는다


def test_too_large_file_is_not_read(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = _file(tmp_path, f"EXAMPLE_TOKEN={VALUE}\n")
    provider = FileSecretProvider(path, settings=load_settings({"max_file_bytes": 5}))
    with caplog.at_level(logging.WARNING):
        assert provider.get_secret("EXAMPLE_TOKEN") is None
    assert "너무 커서" in _all_logs(caplog)
    assert VALUE not in _all_logs(caplog)


def test_env_provider_without_path_gives_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        provider = EnvFileSecretProvider({})
    assert provider.path is None
    assert provider.get_secret("EXAMPLE_TOKEN") is None
    assert ENV in _all_logs(caplog)


def test_env_provider_reads_injected_environment(tmp_path: Path) -> None:
    path = _file(tmp_path, f"EXAMPLE_TOKEN={VALUE}\n")
    provider = EnvFileSecretProvider({ENV: str(path)})
    assert provider.path == path
    assert provider.get_secret("EXAMPLE_TOKEN") == VALUE
