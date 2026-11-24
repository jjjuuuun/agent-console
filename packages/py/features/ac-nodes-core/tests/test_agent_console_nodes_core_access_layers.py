"""접근 설정 층 합치기(`merge_access_layers`) — 메모리·위키 도구 공급자가 함께 쓰는 규칙."""

from typing import Any

import pytest

from agent_console_nodes_core import merge_access_layers


def _merge(items: Any) -> dict[str, Any] | None:
    return merge_access_layers(items, entries_key="wikis", entry_key="wiki", default_ops=["read"])


@pytest.mark.parametrize("items", [None, "x", b"x", [], [{"config": "x"}, 3, {"no": 1}]])
def test_no_layers(items: Any) -> None:
    assert _merge(items) is None


def test_near_layer_wins_per_entry_and_key() -> None:
    far = {
        "config": {
            "wikis": [{"wiki": "a", "access": ["read"]}, {"wiki": "b", "access": ["read"]}],
            "tools": {"read": {"name": "far_read"}, "write": {"name": "far_write"}},
            "header": "far",
            "default": "a",
        }
    }
    near = {
        "config": {
            "wikis": [{"wiki": "b", "access": ["read", "write"]}],
            "tools": {"read": {"name": "near_read"}},
            "header": "near",
        }
    }
    merged = _merge([far, near])
    assert merged == {
        "header": "near",
        "default": "a",
        "wikis": [
            {"wiki": "b", "access": ["read", "write"]},
            {"wiki": "a", "access": ["read"]},
        ],
        "tools": {"read": {"name": "near_read"}, "write": {"name": "far_write"}},
    }


def test_same_entry_in_one_layer_unions_and_default() -> None:
    layer = {
        "config": {
            "wikis": [
                {"wiki": "a", "access": ["read"]},
                {"wiki": "a", "access": ["write", "read"]},
                {"wiki": "c"},
                {"wiki": 3},
                "bad",
                {"wiki": "d", "access": "write"},
            ]
        }
    }
    merged = _merge([layer])
    assert merged is not None
    assert merged["wikis"] == [
        {"wiki": "a", "access": ["read", "write"]},
        {"wiki": "c", "access": ["read"]},
        {"wiki": "d", "access": []},
    ]
    assert "tools" not in merged


def test_entries_key_always_present() -> None:
    assert _merge([{"config": {"header": "h"}}]) == {"header": "h", "wikis": []}


def test_default_ops_not_shared() -> None:
    default = ["read"]
    merged = merge_access_layers(
        [{"config": {"wikis": [{"wiki": "a"}]}}],
        entries_key="wikis",
        entry_key="wiki",
        default_ops=default,
    )
    assert merged is not None
    merged["wikis"][0]["access"].append("write")
    assert default == ["read"]
