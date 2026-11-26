"""계약 0.14.12(FU.19, 더하기만): `modules` 1.7.0.

- `PluginOptionsView` — 설정을 선언한 플러그인(비밀 값 공급자 등)의 옵션 읽기 전용 보기
  (스키마·가린 지금 값·설정 자리·YAML 조각).
- `ServerInfo.plugin_options` — 그 목록(생략 = 빈 목록, 옛 응답이 그대로 읽힌다).
"""

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    PluginOptionsView,
    ServerInfo,
)
from agent_console_contracts.modules import PluginOptionsView as SubpathPluginOptionsView
from agent_console_contracts.schema import build_schema


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_14_12() -> None:
    """0.14.12에서 정한 버전 이상이다(정확한 지금 값은 0.15.0 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 14, 12)
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v01412 = {
        "common": "1.16.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.7.0",
        "runs": "1.9.0",
        "usage": "1.1.0",
        "projects": "3.7.0",
        "chat": "1.4.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.2.0",
        "sdd": "1.3.0",
        "wiki": "1.2.0",
        "modules": "1.7.0",
    }
    assert set(v01412) <= set(CONTRACT_VERSIONS)  # 0.16.0: 하위 모듈 i18n이 늘었다
    for sub, version in v01412.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def test_plugin_options_view_shape() -> None:
    assert SubpathPluginOptionsView is PluginOptionsView
    view = PluginOptionsView.model_validate(
        {
            "extension": "secret_providers",
            "name": "example-file",
            "settings_key": "secrets.providers.example-file",
            "schema": {"type": "object"},
            "values": {"path": "[REDACTED]"},
            "configured": True,
        }
    )
    dumped = view.model_dump(mode="json", by_alias=True)
    assert dumped["schema"] == {"type": "object"}
    assert dumped["yaml_snippet"] == ""
    assert "PluginOptionsView" in build_schema()["$defs"]


def test_server_info_plugin_options_is_optional() -> None:
    old = ServerInfo.model_validate({"server_version": "1", "contracts_version": "0.14.11"})
    assert old.plugin_options == []
    schema = build_schema()["$defs"]["ServerInfo"]
    assert "plugin_options" in schema["properties"]
    assert "plugin_options" not in schema.get("required", [])
