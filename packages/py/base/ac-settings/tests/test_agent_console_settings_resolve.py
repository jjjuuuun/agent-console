"""resolve_layers: 기본 규칙, 출처, 스키마 x-merge, 사용자 규칙, 전략 확장, 임의 층·필드."""

import copy
import random
from typing import Any

import pytest

from agent_console_settings import (
    DEFAULT_STRATEGIES,
    Layer,
    MergeContext,
    StrategyTable,
    TracedValue,
    default_strategies,
    resolve_layers,
    rule_for,
    set_at,
    unset_at,
)

# 설계 §R2.1의 네 층을 흉내 낸 예시 데이터(필드 이름은 테스트 데이터일 뿐, 패키지는 모른다).
COMMON = Layer(
    "common",
    "공통",
    {
        "model": "m-common",
        "tools": ["Read", "Grep"],
        "limits": {"directories": ["/w"], "network": "deny"},
        "backend_options": {"permission_mode": "default", "env": {"A": "1"}},
    },
)
TEAM = Layer("team", "팀 구성", {"model": "m-team", "backend_options": {"env": {"B": "2"}}})
AGENT = Layer("agent", "에이전트", {"tools": ["Read"], "limits": {"commands": ["ls"]}})
NODE = Layer("node", "이 팀의 노드", {"system_prompt": None})

# Pydantic이 만드는 모양(Optional[Model] = anyOf[$ref, null], $defs)을 손으로 쓴 스키마.
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tools": {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}]},
        "limits": {"anyOf": [{"$ref": "#/$defs/Limits"}, {"type": "null"}]},
        "resources": {"type": "array", "x-merge": "append"},
        "backend_options": {"type": "object", "additionalProperties": {"x-merge": "replace"}},
    },
    "$defs": {
        "Limits": {
            "type": "object",
            "x-merge": "replace",
            "properties": {"directories": {"type": "array"}, "commands": {"type": "array"}},
        }
    },
}


def test_default_rules_replace_scalars_and_lists_merge_objects() -> None:
    result = resolve_layers([COMMON, TEAM, AGENT, NODE])
    assert result.value == {
        "model": "m-team",
        "tools": ["Read"],
        "limits": {"directories": ["/w"], "network": "deny", "commands": ["ls"]},
        "backend_options": {"permission_mode": "default", "env": {"A": "1", "B": "2"}},
        "system_prompt": None,
    }
    assert not result.issues


def test_provenance_is_per_leaf() -> None:
    result = resolve_layers([COMMON, TEAM, AGENT, NODE])
    assert result.source_of("/model") == "team"
    assert result.source_of("/tools") == "agent"
    assert result.source_of("/tools/0") == "agent"
    assert result.source_of("/limits/directories") == "common"
    assert result.source_of("/limits/directories/0") == "common"
    assert result.source_of("/limits/commands") == "agent"
    assert result.source_of("/backend_options/env/A") == "common"
    assert result.source_of("/backend_options/env/B") == "team"
    assert result.source_of("/system_prompt") == "node"  # null도 "지정"
    assert result.source_of("/nothing") is None
    assert result.layers_under("/backend_options/env") == ["common", "team"]
    assert result.layers_under("/limits") == ["common", "agent"]
    assert [i.id for i in result.layers] == ["common", "team", "agent", "node"]


def test_omitted_inherits_but_null_and_empty_list_override() -> None:
    upper = Layer("u", value={"a": 1, "b": [1], "c": {"x": 1}})
    lower = Layer("l", value={"a": None, "b": [], "c": None})
    result = resolve_layers([upper, lower])
    assert result.value == {"a": None, "b": [], "c": None}
    assert resolve_layers([upper, Layer("l", value={})]).value == upper.value
    assert resolve_layers([upper, Layer("l", value=None)]).value == upper.value


def test_schema_x_merge_on_ref_target_and_property_and_additional_properties() -> None:
    attached = Layer("agent", value={"resources": [{"ref": "b"}], "limits": {"commands": ["ls"]}})
    common = Layer(
        "common",
        value={
            "resources": [{"ref": "a"}],
            "limits": {"directories": ["/w"]},
            "backend_options": {"env": {"A": "1"}},
        },
    )
    team = Layer("team", value={"backend_options": {"env": {"B": "2"}}})
    result = resolve_layers([common, team, attached], schema=SCHEMA)
    # $defs/Limits의 x-merge=replace → 아래 층이 limits 전체를 바꾼다(설계 §R2.3 limits 교체).
    assert result.value["limits"] == {"commands": ["ls"]}
    # 속성 자리의 x-merge=append → 첨부가 순서대로 쌓이고 원소마다 출처.
    assert result.value["resources"] == [{"ref": "a"}, {"ref": "b"}]
    assert result.source_of("/resources/0") == "common"
    assert result.source_of("/resources/1/ref") == "agent"
    # additionalProperties의 x-merge=replace → env 객체를 통째로 교체.
    assert result.value["backend_options"] == {"env": {"B": "2"}}


def test_user_rules_override_schema() -> None:
    common = Layer("common", value={"limits": {"directories": ["/w", "/tmp"], "network": "deny"}})
    node = Layer("node", value={"limits": {"directories": ["/tmp", "/etc"]}})
    rules = {"/limits": "merge", "/limits/directories": "intersect"}
    result = resolve_layers([common, node], schema=SCHEMA, rules=rules)
    assert result.value["limits"] == {"directories": ["/tmp"], "network": "deny"}
    assert result.source_of("/limits/directories/0") == "common"
    assert result.source_of("/limits/directories") == "node"
    assert rule_for("/limits", {}, schema=SCHEMA) == ("replace", "schema")
    assert rule_for("/limits", {}, schema=SCHEMA, rules=rules) == ("merge", "rules")
    assert rule_for("/model", "x") == ("replace", "default")
    assert rule_for("/obj", {}) == ("merge", "default")


def test_list_strategies() -> None:
    layers = [Layer("a", value={"t": ["x", "y"]}), Layer("b", value={"t": ["y", "z"]})]
    for name, expected in {
        "replace": ["y", "z"],
        "append": ["x", "y", "y", "z"],
        "union": ["x", "y", "z"],
        "intersect": ["y"],
    }.items():
        assert resolve_layers(layers, rules={"/t": name}).value["t"] == expected, name
    union = resolve_layers(layers, rules={"/t": "union"})
    assert [union.source_of(f"/t/{i}") for i in range(3)] == ["a", "a", "b"]
    # 위 층에 목록이 없으면 intersect는 처음 지정한 목록을 그대로 쓴다.
    only = resolve_layers([Layer("b", value={"t": ["q"]})], rules={"/t": "intersect"})
    assert only.value["t"] == ["q"]


def test_type_mismatch_and_unknown_strategy_are_reported_not_raised() -> None:
    layers = [Layer("a", value={"t": ["x"], "s": 1}), Layer("b", value={"t": "oops", "s": 2})]
    result = resolve_layers(layers, rules={"/t": "append", "/s": "nope"})
    assert result.value == {"t": "oops", "s": 2}
    codes = {(i.code, i.pointer, i.layer) for i in result.issues}
    assert ("type_mismatch", "/t", "b") in codes
    assert ("unknown_strategy", "/s", "a") in codes
    # null은 "지정함"이므로 형태 불일치로 보지 않는다.
    nulls = resolve_layers([layers[0], Layer("c", value={"t": None})], rules={"/t": "append"})
    assert nulls.value["t"] is None
    assert not nulls.issues


def test_duplicate_or_empty_layer_ids_rejected() -> None:
    with pytest.raises(ValueError, match="겹칩니다"):
        resolve_layers([Layer("a", value={}), Layer("a", value={})])
    with pytest.raises(ValueError, match="비었습니다"):
        resolve_layers([Layer("", value={})])


def test_inputs_are_not_mutated_and_result_is_a_copy() -> None:
    before = copy.deepcopy(COMMON.value)
    result = resolve_layers([COMMON, TEAM])
    result.value["limits"]["directories"].append("/x")
    assert COMMON.value == before


def test_to_dict_is_json_shaped() -> None:
    data = resolve_layers([COMMON, TEAM]).to_dict()
    assert set(data) == {"value", "provenance", "layers", "issues"}
    assert data["layers"][1] == {"id": "team", "label": "팀 구성", "source": None}


# ---------------------------------------------------------------- 전략 확장 예제
def keyed_attachments(base: TracedValue | None, incoming: Any, ctx: MergeContext, /) -> TracedValue:
    """예제 전략: `{ref, mode}` 첨부 목록. add=추가, replace=같은 ref 교체, remove=같은 ref 삭제.

    리소스 첨부(§R12.1)처럼 패키지 밖에서 정의해 전략 표에 등록하는 사용 예다.
    """
    items = list(base.items()) if base is not None and base.is_array else []
    for att in incoming:
        mode = att.get("mode", "add")
        same = [i for i, t in enumerate(items) if t.value.get("ref") == att.get("ref")]
        if mode == "remove":
            items = [t for i, t in enumerate(items) if i not in same]
        elif mode == "replace" and same:
            items[same[0]] = TracedValue.stamp(att, ctx.layer)
        else:
            items.append(TracedValue.stamp(att, ctx.layer))
    return TracedValue.array(items, ctx.layer)


def test_custom_strategy_registered_in_new_table() -> None:
    table = default_strategies()
    table.register("keyed", keyed_attachments)
    layers = [
        Layer("common", value={"resources": [{"ref": "claude-md"}, {"ref": "old"}]}),
        Layer("team", value={"resources": [{"ref": "old", "mode": "remove"}]}),
        Layer("node", value={"resources": [{"ref": "claude-md", "mode": "replace", "v": 2}]}),
    ]
    schema = {"properties": {"resources": {"x-merge": "keyed"}}}
    result = resolve_layers(layers, schema=schema, strategies=table)
    assert result.value["resources"] == [{"ref": "claude-md", "mode": "replace", "v": 2}]
    assert result.source_of("/resources/0") == "node"
    # 기본 표에는 없으므로 기본 규칙(교체)으로 대체되고 문제로 남는다.
    fallback = resolve_layers(layers, schema=schema)
    assert any(i.code == "unknown_strategy" for i in fallback.issues)


def test_strategy_table_is_explicit_and_default_is_frozen() -> None:
    assert set(DEFAULT_STRATEGIES) == {"replace", "merge", "append", "union", "intersect"}
    assert isinstance(DEFAULT_STRATEGIES, StrategyTable)
    with pytest.raises(RuntimeError):
        DEFAULT_STRATEGIES.register("x", keyed_attachments)
    table = DEFAULT_STRATEGIES.copy()
    table.register("x", keyed_attachments)
    assert "x" in table
    assert "x" not in DEFAULT_STRATEGIES
    with pytest.raises(ValueError, match="이미"):
        table.register("x", keyed_attachments)
    table.register("x", keyed_attachments, replace=True)


# ---------------------------------------------------------------- 층 편집 도우미와 함께
def test_override_and_revert_with_set_at_unset_at() -> None:
    node_value = set_at(NODE.value, "/limits/network", "allow")  # 이 층에서 덮어쓰기
    result = resolve_layers([COMMON, TEAM, AGENT, Layer("node", value=node_value)])
    assert result.source_of("/limits/network") == "node"
    reverted = unset_at(node_value, "/limits/network")  # 상속으로 되돌리기
    assert "limits" not in reverted
    again = resolve_layers([COMMON, TEAM, AGENT, Layer("node", value=reverted)])
    assert again.source_of("/limits/network") == "common"


# ---------------------------------------------------------------- 임의 층 개수·임의 필드
def _random_value(rng: random.Random, depth: int) -> Any:
    kind = rng.choice(["int", "str", "null", "list", "obj"] if depth < 3 else ["int", "str"])
    if kind == "int":
        return rng.randint(0, 9)
    if kind == "str":
        return rng.choice("abc")
    if kind == "null":
        return None
    if kind == "list":
        return [rng.randint(0, 3) for _ in range(rng.randint(0, 3))]
    return {rng.choice("pqrs"): _random_value(rng, depth + 1) for _ in range(rng.randint(0, 3))}


def _reference(layers: list[dict[str, Any]]) -> tuple[Any, dict[str, str]]:
    """기본 규칙(객체 = 재귀 병합, 나머지 = 교체)의 독립 참조 구현."""

    def stamp(value: Any, src: str, at: str, prov: dict[str, str]) -> None:
        prov[at] = src
        if isinstance(value, dict):
            for k, v in value.items():
                stamp(v, src, f"{at}/{k}", prov)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                stamp(v, src, f"{at}/{i}", prov)

    def drop(prov: dict[str, str], at: str) -> None:
        for key in [k for k in prov if k == at or k.startswith(at + "/")]:
            del prov[key]

    def apply(base: Any, inc: Any, src: str, at: str, prov: dict[str, str]) -> Any:
        if not isinstance(inc, dict):
            drop(prov, at)
            stamp(inc, src, at, prov)
            return copy.deepcopy(inc)
        if not isinstance(base, dict):
            drop(prov, at)
            base = {}
        out = dict(base)
        prov[at] = src
        for k, v in inc.items():
            out[k] = apply(out.get(k), v, src, f"{at}/{k}", prov)
        return out

    value: Any = None
    prov: dict[str, str] = {}
    for i, layer in enumerate(layers):
        value = apply(value, layer, f"L{i}", "", prov)
    prov.pop("", None)
    return value or {}, prov


@pytest.mark.parametrize("seed", range(40))
def test_arbitrary_layer_count_and_fields_match_reference(seed: int) -> None:
    rng = random.Random(seed)
    raw = [
        {rng.choice("abcdef"): _random_value(rng, 1) for _ in range(rng.randint(0, 4))}
        for _ in range(rng.randint(1, 7))
    ]
    result = resolve_layers([Layer(f"L{i}", f"층 {i}", v) for i, v in enumerate(raw)])
    expected_value, expected_prov = _reference(raw)
    assert result.value == expected_value
    assert dict(result.provenance) == expected_prov
