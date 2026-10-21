"""graph_hash: 키 순서·좌표·ui·목록 순서 무관, 의미 있는 변경에만 바뀐다."""

from collections.abc import Callable
from typing import Any

from agent_console_contracts import Graph
from agent_console_graph import canonical_graph, graph_hash

BASE: dict[str, Any] = {
    "kind": "graph",
    "id": "g",
    "name": "그래프",
    "inputs": [{"name": "in", "schema": {"type": "string"}}],
    "nodes": [
        {"id": "a", "type": "zz-x", "config": {"k": 1, "m": [1, 2]}, "position": {"x": 0, "y": 0}},
        {"id": "b", "type": "zz-y", "position": {"x": 10, "y": 5}},
    ],
    "edges": [
        {
            "id": "e1",
            "source": {"node": "a", "port": "o"},
            "target": {"node": "b", "port": "i"},
            "kind": "zz-w",
        }
    ],
    "ui": {"viewport": {"x": 0, "y": 0, "zoom": 1}},
}


def h(doc: dict[str, Any]) -> str:
    return graph_hash(Graph.model_validate(doc))


def clone() -> dict[str, Any]:
    return Graph.model_validate(BASE).model_dump(mode="json", by_alias=True)


def test_hash_is_hex_sha256_and_stable() -> None:
    value = h(BASE)
    assert len(value) == 64
    assert value == h(BASE)


def test_key_order_does_not_matter() -> None:
    reordered = dict(reversed(list(BASE.items())))
    reordered["nodes"] = [dict(reversed(list(node.items()))) for node in BASE["nodes"]]
    assert h(reordered) == h(BASE)


def test_layout_and_ui_do_not_matter() -> None:
    doc = clone()
    doc["nodes"][0]["position"] = {"x": 999, "y": -3}
    del doc["nodes"][1]["position"]
    doc["ui"] = {"viewport": {"zoom": 2}, "selected": ["a"]}
    assert h(doc) == h(BASE)


def test_node_and_edge_list_order_does_not_matter() -> None:
    doc = clone()
    doc["nodes"].reverse()
    assert h(doc) == h(BASE)


def test_explicit_defaults_equal_omitted() -> None:
    doc = clone()
    doc["nodes"][1]["config"] = {}
    doc["nodes"][1]["join"] = None
    assert h(doc) == h(BASE)


def test_meaningful_changes_change_hash() -> None:
    base = h(BASE)
    changes: list[Callable[[dict[str, Any]], object]] = [
        lambda d: d["nodes"][0]["config"].update(k=2),
        lambda d: d["nodes"][0]["config"]["m"].reverse(),
        lambda d: d["nodes"][1].update(join="all"),
        lambda d: d["nodes"][1].update(type="zz-z"),
        lambda d: d["edges"][0]["target"].update(port="j"),
        lambda d: d["edges"][0].update(kind="zz-v"),
        lambda d: d.update(name="다른 이름"),
        lambda d: d["inputs"].append({"name": "in2"}),
        lambda d: d["nodes"][0].update(custom_field=1),  # 보존되는 모르는 필드
    ]
    for change in changes:
        doc = clone()
        change(doc)
        assert h(doc) != base, change


def test_canonical_graph_strips_ui_and_position() -> None:
    doc = canonical_graph(Graph.model_validate(BASE))
    assert "ui" not in doc
    assert all("position" not in node for node in doc["nodes"])


# ---------------------------------------------------------------- 화면 배치(layout, E-3)


def test_layout_only_change_keeps_hash() -> None:
    """노드·엣지 layout은 position처럼 해시에서 빠진다(graph-edges §5.3 S2)."""
    base = h(clone())
    doc = clone()
    doc["nodes"][0]["layout"] = {"direction": "tb", "ports": {"out:o": "right"}}
    doc["edges"][0]["layout"] = {
        "shape": "smoothstep",
        "waypoints": [{"x": 560, "y": 280}, {"x": 560, "y": 72}],
        "label_t": 0.3,
        "zz-unknown": {"kept": True},
    }
    doc["ui"] = {"layout": {"direction": "tb", "edge_shape": "auto"}}
    assert h(doc) == base
    # position과 layout을 같이 바꿔도 같다
    doc["nodes"][1]["position"] = {"x": -40, "y": 900}
    doc["nodes"][1]["layout"] = {"direction": "bt"}
    assert h(doc) == base


def test_canonical_graph_strips_layout_but_keeps_meaning() -> None:
    doc = clone()
    doc["nodes"][0]["layout"] = {"direction": "tb"}
    doc["edges"][0]["layout"] = {"shape": "step"}
    canon = canonical_graph(Graph.model_validate(doc))
    assert all("layout" not in node for node in canon["nodes"])
    assert all("layout" not in edge for edge in canon["edges"])
    # 의미 필드는 그대로 남아 해시가 바뀐다
    doc["edges"][0]["kind"] = "zz-other"
    assert h(doc) != h(clone())


# ---------------------------------------------------------------- 정의 범위(project, 계약 0.8.0)


def test_project_only_change_keeps_hash() -> None:
    """팀 구성을 다른 프로젝트·공용으로 옮겨도 해시가 같다(design §UX-P.4)."""
    base = h(clone())
    for value in ("app", "other", None):
        doc = clone()
        doc["project"] = value
        assert h(doc) == base, value
        assert "project" not in canonical_graph(Graph.model_validate(doc))
    # 범위와 함께 의미 필드를 바꾸면 해시가 바뀐다
    doc = clone()
    doc["project"] = "app"
    doc["name"] = "다른 이름"
    assert h(doc) != base
