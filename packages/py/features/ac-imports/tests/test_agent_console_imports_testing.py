"""`agent_console_imports.testing.MemoryDefinitionWriter`: 프로토콜 만족·버전·충돌 규칙."""

import pytest

from agent_console_imports import DefinitionWriter
from agent_console_imports.testing import MemoryDefinitionWriter, MemoryFile


def test_satisfies_definition_writer_protocol() -> None:
    writer: DefinitionWriter = MemoryDefinitionWriter()
    assert writer.list_ids("agent") == []


def test_versions_and_conflicts() -> None:
    w = MemoryDefinitionWriter()
    v1 = w.create("agent", {"id": "a", "name": "A"}, message="m")
    assert v1.version_hash == "v1"
    assert w.get("agent", "a") == v1
    with pytest.raises(ValueError, match="이미"):
        w.create("agent", {"id": "a"})
    with pytest.raises(ValueError, match="버전"):
        w.save("agent", {"id": "a"}, expected_version="v9")
    v2 = w.save("agent", {"id": "a", "name": "B"}, expected_version="v1")
    assert v2.version_hash == "v2"
    assert w.documents[("agent", "a")] == {"id": "a", "name": "B"}
    with pytest.raises(KeyError):
        w.get("agent", "missing")
    with pytest.raises(KeyError):
        w.write_content("agent", "missing", b"x")
    assert w.list_ids("agent") == ["a"]
    assert w.list_ids("skill") == []
    assert w.messages[0] == ("agent", "a", "m")


def test_content_and_files() -> None:
    w = MemoryDefinitionWriter()
    v = w.create("resource", {"id": "r"})
    v = w.write_content("resource", "r", b"body", expected_version=v.version_hash)
    assert w.contents[("resource", "r")] == b"body"
    v = w.write_files(
        "resource", "r", {"a.md": b"a", "b.md": b"b"}, expected_version=v.version_hash
    )
    w.write_files("resource", "r", {"a.md": None}, expected_version=v.version_hash)
    assert w.list_files("resource", "r") == [MemoryFile("b.md")]
