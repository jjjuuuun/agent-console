"""find_widenings: 아래 층이 권한·범위를 넓히면 경고(설계 §R2.3, 결정 §R13-9)."""

from typing import Any

import pytest

from agent_console_settings import DEFAULT_WIDEN_CHECKS, Layer, find_widenings

LIMITS_SCHEMA: dict[str, Any] = {
    "properties": {"limits": {"anyOf": [{"$ref": "#/$defs/Limits"}, {"type": "null"}]}},
    "$defs": {
        "Limits": {
            "x-merge": "replace",
            "properties": {
                "directories": {"x-widen": "path_subset"},
                "commands": {"x-widen": "subset"},
                "network": {"x-widen": {"kind": "order", "order": ["deny", "allow"]}},
            },
        }
    },
}

COMMON = Layer(
    "common",
    "공통",
    {"limits": {"directories": ["/w"], "commands": ["ls"], "network": "deny"}},
)


def test_widening_detected_with_schema_annotations() -> None:
    node = Layer(
        "node",
        "노드",
        {
            "limits": {
                "directories": ["/w/sub", "/etc"],
                "commands": ["ls", "rm"],
                "network": "allow",
            }
        },
    )
    found = {(w.pointer, w.check): w for w in find_widenings([COMMON, node], schema=LIMITS_SCHEMA)}
    assert found[("/limits/directories", "path_subset")].added == ("/etc",)
    assert found[("/limits/commands", "subset")].added == ("rm",)
    net = found[("/limits/network", "order")]
    assert net.added == ("allow",)
    assert net.layer == "node"
    assert net.upper_layer == "common"


def test_narrowing_or_untouched_is_not_widening() -> None:
    narrower = Layer("node", value={"limits": {"directories": ["/w/a/../b"], "commands": []}})
    assert find_widenings([COMMON, narrower], schema=LIMITS_SCHEMA) == []
    unrelated = Layer("team", value={"model": "x"})
    assert find_widenings([COMMON, unrelated], schema=LIMITS_SCHEMA) == []


def test_path_escape_is_widening() -> None:
    sneaky = Layer("node", value={"limits": {"directories": ["/w/../etc", "C:\\w\\x"]}})
    common = Layer("common", value={"limits": {"directories": ["/w", "C:/w"]}})
    found = find_widenings([common, sneaky], schema=LIMITS_SCHEMA)
    assert [w.added for w in found] == [("/w/../etc",)]


def test_intersect_rule_cannot_widen() -> None:
    node = Layer("node", value={"limits": {"commands": ["ls", "rm"]}})
    rules = {"/limits": "merge", "/limits/commands": "intersect"}
    assert find_widenings([COMMON, node], schema=LIMITS_SCHEMA, rules=rules) == []


def test_checks_argument_and_custom_comparator() -> None:
    upper = Layer("a", value={"budget": 10})
    lower = Layer("b", value={"budget": 20})
    comparators = {
        **DEFAULT_WIDEN_CHECKS,
        "max": lambda up, low, params: (low,) if low > up else (),
    }
    found = find_widenings([upper, lower], checks={"/budget": "max"}, comparators=comparators)
    assert [(w.pointer, w.added) for w in found] == [("/budget", (20,))]
    with pytest.raises(ValueError, match="모르는"):
        find_widenings([upper, lower], checks={"/budget": "max"})
    with pytest.raises(ValueError, match="형식"):
        find_widenings([upper, lower], checks={"/budget": {"no_kind": 1}})


def test_missing_or_null_upper_is_not_compared() -> None:
    lower = Layer("node", value={"limits": {"commands": ["rm"]}})
    assert find_widenings([Layer("common", value={}), lower], schema=LIMITS_SCHEMA) == []
    nulls = Layer("common", value={"limits": {"commands": None}})
    assert find_widenings([nulls, lower], schema=LIMITS_SCHEMA) == []


def test_any_number_of_layers_each_compared_to_effective_upper() -> None:
    layers = [
        COMMON,
        Layer("team", value={"limits": {"commands": ["ls", "git"]}}),
        Layer("agent", value={"model": "m"}),
        Layer("node", value={"limits": {"commands": ["ls", "git", "rm"]}}),
    ]
    found = find_widenings(layers, schema=LIMITS_SCHEMA)
    assert [(w.layer, w.upper_layer, w.added) for w in found if w.check == "subset"] == [
        ("team", "common", ("git",)),
        ("node", "team", ("rm",)),
    ]
