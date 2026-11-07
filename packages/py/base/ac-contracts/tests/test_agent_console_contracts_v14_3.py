"""계약 0.14.3(plugins.disabled 후속, 더하기만): `modules` 1.6.0.

- `PluginInfo.reason` — skipped·disabled 플러그인의 끈 이유(선택, 0.14.2 응답이 그대로 읽힌다).
"""

from agent_console_contracts import CONTRACT_VERSIONS, CONTRACTS_VERSION, PluginInfo, ServerInfo
from agent_console_contracts.schema import build_schema


def test_contracts_version_is_0_14_3() -> None:
    assert CONTRACTS_VERSION == "0.14.3"
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == "0.14.3"
    assert CONTRACT_VERSIONS == {
        "common": "1.12.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.7.0",
        "runs": "1.8.0",
        "usage": "1.1.0",
        "projects": "3.3.0",
        "chat": "1.3.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.1.0",
        "sdd": "1.2.0",
        "wiki": "1.2.0",
        "modules": "1.6.0",
    }


def test_old_plugin_info_still_reads() -> None:
    info = PluginInfo.model_validate({"name": "p", "status": "skipped"})
    assert info.reason is None


def test_plugin_reason_round_trip() -> None:
    info = PluginInfo(name="p", group="g", loaded=False, status="disabled", reason="설정 목록")
    server = ServerInfo.model_validate(
        {"server_version": "1", "contracts_version": "0.14.3", "plugins": [info.model_dump()]}
    )
    assert server.plugins[0].reason == "설정 목록"


def test_plugin_schema_documents_reason_and_disabled_list() -> None:
    props = build_schema()["$defs"]["PluginInfo"]["properties"]
    assert "reason" in props
    assert "plugins.disabled" in props["status"]["description"]
