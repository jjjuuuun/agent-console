"""경계 사례: 빈 층, 순환 $ref, 모르는 전략, 상속 복원, 섞인 객체 출처 (QA 추가)."""

from agent_console_settings import Layer, resolve_layers, schema_annotation, unset_at


def test_empty_and_valueless_layers() -> None:
    assert resolve_layers([]).value == {}
    got = resolve_layers([Layer("a"), Layer("b", value={})])
    assert got.value == {}
    assert dict(got.provenance) == {}
    assert got.issues == ()


def test_circular_schema_ref_terminates() -> None:
    cyc = {"$ref": "#/$defs/A", "$defs": {"A": {"$ref": "#/$defs/B"}, "B": {"$ref": "#/$defs/A"}}}
    assert schema_annotation(cyc, "/a/b", "x-merge") is None
    node = {
        "$defs": {"N": {"properties": {"c": {"$ref": "#/$defs/N"}, "l": {"x-merge": "append"}}}},
        "$ref": "#/$defs/N",
    }
    got = resolve_layers(
        [Layer("a", value={"c": {"c": {"l": [1]}}}), Layer("b", value={"c": {"c": {"l": [2]}}})],
        schema=node,
    )
    assert got.value == {"c": {"c": {"l": [1, 2]}}}


def test_unknown_strategy_falls_back_and_reports() -> None:
    got = resolve_layers(
        [Layer("a", value={"x": [1]}), Layer("b", value={"x": [2]})], rules={"/x": "nope"}
    )
    assert got.value == {"x": [2]}
    assert {i.code for i in got.issues} == {"unknown_strategy"}


def test_unset_restores_inheritance_and_layers_under() -> None:
    upper = {"y": {"z": 1}, "w": 1}
    lower = unset_at({"y": {"z": 9}, "w": 2}, "/y/z")
    got = resolve_layers([Layer("a", value=upper), Layer("b", value=lower)])
    assert got.value == {"y": {"z": 1}, "w": 2}
    assert got.source_of("/y/z") == "a"
    assert got.source_of("/w") == "b"
    assert got.layers_under("") == ["a", "b"]
    assert got.layers_under("/y") == ["a"]
