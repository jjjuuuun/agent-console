"""비밀 공급자 설정 훅(X10 설정): 설치자 설정 ``secrets.providers.<key>``로 공급자 다시 만들기."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

import pytest

from agent_console_modkit import (
    SECRET_PROVIDERS_REGISTRY,
    SECRET_PROVIDERS_SETTINGS_KEY,
    ConfigurableSecretProvider,
    ExtensionRegistries,
    SecretProviderOptionsError,
    SettingsNoticeCodes,
    configure_secret_providers,
    env_secret_lookup,
    schema_defaults,
    secret_lookup,
    secret_providers_of,
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prefix": {"type": "string", "default": "v-"},
        "file": {"type": ["string", "null"], "format": "path", "default": None},
        "nested": {"type": "object", "properties": {"n": {"type": "integer", "default": 1}}},
    },
    "additionalProperties": False,
}


class Tunable:
    """설정 훅이 있는 공급자(테스트용). 값 = 접두 + 이름."""

    seen: ClassVar[list[tuple[dict[str, Any], Path | None]]] = []

    def __init__(self, prefix: str = "default-") -> None:
        self.prefix = prefix

    def get_secret(self, name: str) -> str | None:
        return self.prefix + name if name.startswith("t_") else None

    @classmethod
    def options_schema(cls) -> Mapping[str, Any]:
        return SCHEMA

    @classmethod
    def from_options(
        cls, options: Mapping[str, Any], *, environ: Mapping[str, str], base_dir: Path | None
    ) -> Tunable:
        unknown = set(options) - set(SCHEMA["properties"])
        if unknown:
            raise ValueError(f"모르는 옵션: {', '.join(sorted(unknown))}")
        cls.seen.append((dict(options), base_dir))
        return cls(str(options.get("prefix", "v-")) + environ.get("SUFFIX", ""))


class Plain:
    """설정 훅이 없는 공급자."""

    def get_secret(self, name: str) -> str | None:
        return "plain" if name == "p" else None


def _bundle(**items: Any) -> ExtensionRegistries:
    bundle = ExtensionRegistries()
    registry = bundle.extension(SECRET_PROVIDERS_REGISTRY)
    for key, item in items.items():
        registry.register(key, item, source=f"test {key}")
    return bundle


def test_protocol_shape() -> None:
    assert isinstance(Tunable(), ConfigurableSecretProvider)
    assert not isinstance(Plain(), ConfigurableSecretProvider)


def test_no_settings_keeps_the_registered_instance(tmp_path: Path) -> None:
    original = Tunable("kept-")
    bundle = _bundle(tune=original)
    setup = configure_secret_providers(bundle, {}, environ={}, base_dir=tmp_path)
    assert setup.configured == []
    assert secret_providers_of(bundle) == [original]
    # 스키마가 있으면 설정이 없어도 보기 재료(기본값)는 나온다
    (view,) = setup.options
    assert (view.name, view.configured) == ("tune", False)
    assert view.settings_key == "secrets.providers.tune"
    assert view.values == {"prefix": "v-", "file": None}
    assert setup.warnings == []


def test_settings_rebuild_the_provider_and_the_lookup_sees_it(tmp_path: Path) -> None:
    Tunable.seen.clear()
    bundle = _bundle(tune=Tunable(), plain=Plain())
    setup = configure_secret_providers(
        bundle,
        {"tune": {"prefix": "x-", "nested": {}}},
        environ={"SUFFIX": "!"},
        base_dir=tmp_path,
    )
    assert setup.configured == ["tune"]
    # 원문 그대로, base_dir 주입
    assert Tunable.seen == [({"prefix": "x-", "nested": {}}, tmp_path)]
    entry = bundle.extension(SECRET_PROVIDERS_REGISTRY).list()[1]
    assert (entry.key, entry.source) == ("tune", "test tune")  # 출처는 그대로
    lookup = secret_lookup(env_secret_lookup({}), secret_providers_of(bundle))
    assert lookup("t_a") == "x-!t_a"
    assert lookup("p") == "plain"
    (view,) = setup.options  # 스키마도 설정도 없는 Plain은 보기에 없다
    assert view.configured is True
    assert view.values == {"prefix": "x-", "file": None, "nested": {"n": 1}}


def test_rejected_options_raise_with_location_only() -> None:
    bundle = _bundle(tune=Tunable())
    with pytest.raises(SecretProviderOptionsError) as caught:
        configure_secret_providers(bundle, {"tune": {"token": "sekret-zz1"}}, environ={})
    text = str(caught.value)
    assert text.startswith(f"{SECRET_PROVIDERS_SETTINGS_KEY}.tune:")
    assert "token" in text  # 키 이름은 보인다
    assert "sekret-zz1" not in text  # 값은 없다


def test_hook_must_return_a_provider() -> None:
    class Broken(Tunable):
        @classmethod
        def from_options(
            cls, options: Mapping[str, Any], *, environ: Mapping[str, str], base_dir: Path | None
        ) -> Any:
            return object()

    with pytest.raises(SecretProviderOptionsError, match="get_secret"):
        configure_secret_providers(_bundle(b=Broken()), {"b": {}}, environ={})


def test_settings_for_unknown_or_hookless_providers_only_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    plain = Plain()
    bundle = _bundle(plain=plain)
    with caplog.at_level(logging.WARNING):
        setup = configure_secret_providers(
            bundle, {"plain": {"a": 1}, "ghost": {"b": 2}}, environ={}
        )
    assert setup.configured == []
    assert secret_providers_of(bundle) == [plain]
    assert len(setup.warnings) == 2
    assert any("plain" in w and "from_options" in w for w in setup.warnings)
    assert any("'ghost'" in w for w in setup.warnings)
    assert all("1" not in w and "2" not in w for w in setup.warnings)  # 값은 없다


def test_bundle_without_registry_is_empty() -> None:
    class Bare:
        pass

    setup = configure_secret_providers(Bare(), {"x": {}}, environ={})
    assert setup.configured == []
    assert setup.options == []
    assert setup.warnings
    assert "'x'" in setup.warnings[0]


def test_schema_defaults_fills_nested_objects_without_validation() -> None:
    filled = schema_defaults(SCHEMA, {"nested": {}, "extra": True})
    assert filled == {"nested": {"n": 1}, "extra": True, "prefix": "v-", "file": None}
    assert schema_defaults(None, {"a": 1}) == {"a": 1}


def test_settings_warnings_log_english_and_keep_web_text(caplog: pytest.LogCaptureFixture) -> None:
    """I.6: 같은 경고가 터미널(로그)에는 영어, `warnings`(웹 server-info)에는 한국어 원문이다."""
    bundle = _bundle(plain=Plain())
    with caplog.at_level(logging.WARNING):
        setup = configure_secret_providers(
            bundle, {"plain": {"a": 1}, "ghost": {"b": 2}}, environ={}
        )
    logged = [r.getMessage() for r in caplog.records]
    assert any("secret provider plain has no settings hook" in line for line in logged)
    assert any("'ghost' is not a registered secret provider" in line for line in logged)
    assert not any(re.search("[가-힣]", line) for line in logged)
    assert all(re.search("[가-힣]", w) for w in setup.warnings)


def test_settings_notices_carry_code_and_details() -> None:
    """I.7c: 웹이 문구 묶음 ``codes``로 문구를 고르도록 코드·``details``가 붙는다(값은 없다)."""
    setup = configure_secret_providers(
        _bundle(plain=Plain()), {"plain": {"a": 1}, "ghost": {"b": 2}}, environ={}
    )
    assert [(n.code, dict(n.details)) for n in setup.notices] == [
        (
            SettingsNoticeCodes.SECRET_PROVIDER_NO_SETTINGS_HOOK,
            {"setting": "secrets.providers.plain", "provider": "plain", "hook": "from_options"},
        ),
        (
            SettingsNoticeCodes.SECRET_PROVIDER_UNKNOWN,
            {"setting": "secrets.providers", "provider": "ghost"},
        ),
    ]
    assert setup.warnings == [n.message for n in setup.notices]
