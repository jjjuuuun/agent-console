"""비밀처럼 보이는 값은 저장하지 않는다(`secret://` 참조만)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_console_project_space import ConfigReadonly, SecretRejected, open_space
from agent_console_project_space.testing import ReadOnlyFiles, sample_agent, snapshot_tree
from agent_console_secret_rules import SecretRules


def test_plain_secret_is_refused_and_nothing_is_written(folder: Path) -> None:
    space = open_space(folder)
    with pytest.raises(SecretRejected) as caught:
        space.definitions.create("agent", sample_agent(attributes={"API_KEY": "abcd1234efgh5678"}))
    assert [f.path for f in caught.value.findings] == ["/attributes/API_KEY"]
    assert "abcd1234efgh5678" not in str(caught.value)
    assert snapshot_tree(folder) == {}
    assert space.definitions.list_ids("agent") == []


def test_reference_is_accepted(folder: Path) -> None:
    space = open_space(folder)
    space.definitions.create("agent", sample_agent(attributes={"API_KEY": "secret://anthropic"}))
    assert "secret://anthropic" in (folder / ".agent-console/agents/a1.yaml").read_text()


def test_save_and_restore_paths_are_guarded_too(folder: Path) -> None:
    space = open_space(folder)
    created = space.definitions.create("agent", sample_agent())
    with pytest.raises(SecretRejected):
        space.definitions.save("agent", sample_agent(attributes={"password": "hunter2hunter2"}))
    assert space.definitions.get("agent", "a1").version_hash == created.version_hash


def test_user_rules_are_injected(folder: Path) -> None:
    rules = SecretRules().with_extra(value_patterns=[r"corp_[0-9]{6}"])
    space = open_space(folder, secret_rules=rules)
    with pytest.raises(SecretRejected):
        space.definitions.create("agent", sample_agent(attributes={"note": "corp_123456"}))


def test_body_files_scan_is_opt_in(folder: Path) -> None:
    doc = {"id": "r1", "type": "instruction", "name": "n", "content": {"file": "a.md"}}
    open_space(folder).definitions.create("resource", doc)
    plain = b"token: ghp_" + b"A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    open_space(folder).definitions.write_file(
        "resource",
        "r1",
        "a.md",
        plain,
        expected_version=open_space(folder).definitions.get("resource", "r1").version_hash,
    )
    strict = open_space(folder, scan_bodies=True)
    with pytest.raises(SecretRejected) as caught:
        strict.definitions.write_file(
            "resource",
            "r1",
            "b.md",
            plain,
            expected_version=strict.definitions.get("resource", "r1").version_hash,
        )
    assert caught.value.findings[0].path.startswith("/$content/b.md")


def test_read_only_space_refuses_writes(folder: Path) -> None:
    space = open_space(folder, files=ReadOnlyFiles())
    assert space.config_writable is False
    with pytest.raises(ConfigReadonly):
        space.definitions.create("agent", sample_agent())
    assert space.definitions.list_ids("agent") == []
    assert snapshot_tree(folder) == {}


def _team_graph(edge_config: dict[str, object]) -> dict[str, object]:
    """연결 config가 든 최소 team_graph 문서(5.7R.33y2 재현용)."""
    return {
        "id": "team",
        "name": "팀",
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "lead", "type": "agent", "label": "리더", "config": {}},
        ],
        "edges": [
            {
                "id": "m1",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "lead", "port": "in"},
                "kind": "message",
                "config": edge_config,
            }
        ],
    }


def test_edge_input_key_is_not_a_secret(folder: Path) -> None:
    space = open_space(folder)
    space.definitions.create("graph", _team_graph({"input_key": "message", "template": "{x}"}))
    assert "input_key: message" in (folder / ".agent-console/graphs/team.yaml").read_text()


def test_real_secret_in_graph_is_still_refused(folder: Path) -> None:
    space = open_space(folder)
    with pytest.raises(SecretRejected) as caught:
        space.definitions.create(
            "graph", _team_graph({"input_key": "message", "api_key": "sk-" + "ant-abcdef123456"})
        )
    assert [f.path for f in caught.value.findings] == ["/edges/0/config/api_key"]
    with pytest.raises(SecretRejected) as shaped:
        space.definitions.create(
            "graph", _team_graph({"input_key": "9f86d081884c7d659a2feaa0c55ad015"})
        )
    assert [f.path for f in shaped.value.findings] == ["/edges/0/config/input_key"]


def test_weak_name_rule_is_user_configurable(folder: Path) -> None:
    strict = open_space(folder, secret_rules=SecretRules().with_extra(key_names=["key"]))
    with pytest.raises(SecretRejected):
        strict.definitions.create("graph", _team_graph({"input_key": "message"}))
    off = open_space(folder, secret_rules=SecretRules(weak_key_names=()))
    with pytest.raises(SecretRejected):
        off.definitions.create("graph", _team_graph({"input_key": "message"}))
