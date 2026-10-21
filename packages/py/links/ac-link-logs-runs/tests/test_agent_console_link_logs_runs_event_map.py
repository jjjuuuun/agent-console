"""대응표(데이터): 기본값 읽기·우선순위·덮어쓰기·값 틀·대체 범주, 기본 파일 없이도 동작."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_console_link_logs_runs import (
    DEFAULT_FALLBACK_CATEGORY,
    EventMap,
    load_default_event_map,
    load_event_map,
)
from agent_console_link_logs_runs.event_map import render, resolve
from agent_console_logs import ConfigError

EVENT = {
    "type": "mcp.call_completed",
    "run_id": "r1",
    "node_path": ["a", "b"],
    "actor": "pl",
    "payload": {"server": "docs", "is_error": True, "exit_code": 0, "n": None},
}
NAMES = {"type": "mcp.call_completed", "node": "b", "parent_node": "a"}


def test_default_map_is_package_data_and_valid() -> None:
    default = load_default_event_map()
    assert default.rule_for("hook.finished").get("category") == "hook"
    assert default.rule_for("mcp.call_started").get("stage") == "start"
    assert default.rule_for("agent.text_delta").skip


def test_exact_key_beats_globs_and_longer_glob_wins() -> None:
    table = EventMap({"*": {"category": "x"}, "a.*": {"category": "y"}, "a.b": {"category": "z"}})
    assert table.rule_for("a.b").get("category") == "z"
    assert table.rule_for("a.c").get("category") == "y"
    assert table.rule_for("q").get("category") == "x"


def test_no_rule_uses_fallback_category() -> None:
    table = EventMap({"a.*": {"category": "y"}})
    assert table.rule_for("other.thing").get("category") == DEFAULT_FALLBACK_CATEGORY
    assert EventMap(fallback_category="misc").rule_for("x").get("category") == "misc"


def test_overrides_replace_whole_rule_per_key() -> None:
    base = EventMap({"a.b": {"category": "z", "stage": "start"}, "a.*": {"category": "y"}})
    merged = base.with_overrides({"a.b": {"category": "w"}, "new.*": {"skip": True}})
    assert merged.rule_for("a.b").spec == {"category": "w"}  # stage는 남지 않는다
    assert merged.rule_for("new.x").skip
    assert base.rule_for("a.b").get("stage") == "start"  # 원본은 그대로


def test_template_fills_pointers_and_names() -> None:
    assert render("{/payload/server}/{node}<{parent_node}>", EVENT, NAMES) == "docs/b<a>"
    assert render("{/payload/missing}{unknown}x", EVENT, NAMES) == "x"
    assert render("{/payload/is_error}", EVENT, NAMES) == "true"


def test_value_spec_maps_json_forms() -> None:
    spec = {"pointer": "/payload/is_error", "map": {"true": "error"}, "default": "ok"}
    assert resolve(spec, EVENT, NAMES) == "error"
    assert resolve({"pointer": "/payload/exit_code", "map": {"0": "ok"}}, EVENT, NAMES) == "ok"
    assert resolve({"pointer": "/payload/n", "default": "none"}, EVENT, NAMES) == "none"
    assert resolve({"pointer": "/payload/n"}, EVENT, NAMES) == ""
    assert resolve({"pointer": "/payload/server"}, EVENT, NAMES) == "docs"
    assert resolve(None, EVENT, NAMES) == ""


def test_bad_rule_shape_is_config_error() -> None:
    with pytest.raises(ConfigError):
        load_event_map("types: {a.b: {category: 3}}")
    with pytest.raises(ConfigError):
        load_event_map("types: {a.b: {nope: x}}")


def test_missing_or_empty_default_file_still_works(tmp_path: Path) -> None:
    gone = load_default_event_map(tmp_path / "none.yaml")
    assert gone.rule_for("hook.finished").get("category") == DEFAULT_FALLBACK_CATEGORY
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    assert load_default_event_map(empty).rules == {}
