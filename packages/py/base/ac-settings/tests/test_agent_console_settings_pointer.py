from typing import Any

import pytest

from agent_console_settings import (
    MISSING,
    PointerError,
    escape_token,
    get_at,
    join_pointer,
    set_at,
    split_pointer,
    unescape_token,
    unset_at,
)


def test_pointer_round_trip_escapes() -> None:
    assert escape_token("a/b~c") == "a~1b~0c"
    assert unescape_token("a~1b~0c") == "a/b~c"
    assert join_pointer("", "a/b", 0, "~") == "/a~1b/0/~0"
    assert split_pointer("/a~1b/0/~0") == ["a/b", "0", "~"]
    assert split_pointer("") == []
    with pytest.raises(PointerError):
        split_pointer("a")


def test_get_at_distinguishes_missing_from_null() -> None:
    doc: dict[str, Any] = {"a": {"b": None}, "l": [1, 2]}
    assert get_at(doc, "/a/b") is None
    assert get_at(doc, "/a/c") is MISSING
    assert get_at(doc, "/l/1") == 2
    assert get_at(doc, "/l/5") is MISSING
    assert get_at(doc, "/l/x", default=0) == 0
    assert get_at(doc, "") == doc


def test_set_at_copies_and_creates_parents() -> None:
    doc: dict[str, Any] = {"limits": {"commands": ["ls"]}}
    out = set_at(doc, "/limits/network", "deny")
    assert out == {"limits": {"commands": ["ls"], "network": "deny"}}
    assert doc == {"limits": {"commands": ["ls"]}}  # 원본 불변
    assert set_at(None, "/a/b/c", 1) == {"a": {"b": {"c": 1}}}
    assert set_at(doc, "/limits/commands/0", "pwd")["limits"]["commands"] == ["pwd"]
    assert set_at(doc, "/limits/commands/-", "pwd")["limits"]["commands"] == ["ls", "pwd"]
    assert set_at(doc, "", {"x": 1}) == {"x": 1}


def test_set_at_rejects_non_container_path() -> None:
    with pytest.raises(PointerError):
        set_at({"a": 1}, "/a/b", 2)
    with pytest.raises(PointerError):
        set_at({"l": [1]}, "/l/3", 2)


def test_unset_at_prunes_emptied_parents_only() -> None:
    doc: dict[str, Any] = {"limits": {"commands": ["ls"]}, "keep": {}}
    assert unset_at(doc, "/limits/commands") == {"keep": {}}
    assert unset_at(doc, "/limits/commands", prune=False) == {"limits": {}, "keep": {}}
    assert unset_at(doc, "/nothing/here") == doc  # 없으면 그대로
    assert doc["limits"] == {"commands": ["ls"]}  # 원본 불변
    assert unset_at({"l": [1, 2]}, "/l/0") == {"l": [2]}
    with pytest.raises(PointerError):
        unset_at(doc, "")
