"""`agent_console_exports.testing`: 메모리 카탈로그(`ExportCatalog`)와 기본 형식."""

from agent_console_contracts import ExportSelection
from agent_console_exports import ExportCatalog
from agent_console_exports.claude_dir import claude_dir_exporter
from agent_console_exports.testing import MemoryCatalog, MemoryDependency


def test_memory_catalog_reads_back_what_was_added() -> None:
    dep = MemoryDependency(kind="resource", id="tip", node_id="pl")
    catalog: ExportCatalog = MemoryCatalog().add(
        "agent", {"id": "pl"}, files={"a.md": b"x"}, uses=[dep]
    )
    assert catalog.document("agent", "pl") == {"kind": "agent", "id": "pl"}
    assert catalog.document("agent", "nope") is None
    assert catalog.files("agent", "pl") == {"a.md": b"x"}
    assert catalog.files("agent", "nope") == {}
    assert list(catalog.dependencies("agent", "pl")) == [dep]
    assert list(catalog.dependencies("agent", "nope")) == []


def test_memory_catalog_drives_default_exporter() -> None:
    catalog = MemoryCatalog().add("agent", {"id": "pl", "name": "pl", "system_prompt": "p"})
    out = claude_dir_exporter({}).plan([ExportSelection(kind="agent", id="pl")], catalog, {})
    assert [f.path for f in out.files] == [".claude/agents/pl.md"]
