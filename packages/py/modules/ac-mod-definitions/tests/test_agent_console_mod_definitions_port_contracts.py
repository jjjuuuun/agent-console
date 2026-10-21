"""포트 계약(3R.12): mod-definitions가 주는 구현 ↔ 기존 소비 모듈(3R.10)의 소비 프로토콜.

정적 검사(mypy, 프로토콜 형식에 대입)와 실행 검사(``runtime_checkable``은 ``isinstance``, 나머지는
그 프로토콜로 실제 동작)를 함께 한다. 같은 이름 포트로 조립했을 때 소비 모듈이 켜지는지도 본다.
"""

from __future__ import annotations

from pathlib import Path

from agent_console_contracts import WorkspaceSettings
from agent_console_imports import DefinitionWriter
from agent_console_mod_definitions import (
    DEFINITION_CHECKS,
    DEFINITIONS_STORE,
    SECRET_RULES,
    WORKSPACE_SETTINGS,
    module,
)
from agent_console_mod_exports import DefinitionLookup as ExportsLookup
from agent_console_mod_exports import module as exports
from agent_console_mod_imports import module as imports
from agent_console_mod_presets import DefinitionCheck as PresetsCheck
from agent_console_mod_presets import module as presets
from agent_console_mod_usage import WorkspaceSettingsReader
from agent_console_mod_usage import module as usage
from agent_console_mod_versions import DefinitionCheck as VersionsCheck
from agent_console_mod_versions import SecretRulesReader, VersionStore
from agent_console_mod_versions import module as versions
from agent_console_modkit import BaseServices, Paths, assemble
from agent_console_store import DefinitionStore


def test_provided_ports_match_consumer_protocols(tmp_path: Path) -> None:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    assembly = assemble([module], base=base)
    store = assembly.port(DEFINITIONS_STORE)
    assert store is not None
    as_versions: VersionStore = store
    as_presets: DefinitionStore = store
    as_imports: DefinitionWriter = store
    as_exports: ExportsLookup = store
    assert isinstance(store, ExportsLookup)
    saved = as_imports.create("agent", {"id": "a", "name": "a"})
    assert as_presets.get("agent", "a").version_hash == saved.version_hash
    assert as_versions.versions.list("agent", "a")
    assert as_exports.get("agent", "a").document["id"] == "a"

    reader = assembly.port(WORKSPACE_SETTINGS)
    assert reader is not None
    as_usage: WorkspaceSettingsReader = reader
    assert isinstance(as_usage(), WorkspaceSettings)
    rules = assembly.port(SECRET_RULES)
    assert rules is not None
    as_rules: SecretRulesReader = rules
    assert as_rules().find_suspected({"token": "ghp_abcdefghijk"})

    for check in assembly.ports(DEFINITION_CHECKS):
        assert isinstance(check, VersionsCheck)
        assert isinstance(check, PresetsCheck)


def test_consumers_assemble_on_provided_ports(tmp_path: Path) -> None:
    base = BaseServices(
        environ={"HOME": str(tmp_path / "home")},
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
    )
    assembly = assemble([module, versions, presets, imports, exports, usage], base=base)
    states = {r.id: r.state.value for r in assembly.report}
    assert set(states.values()) == {"active"}, states
