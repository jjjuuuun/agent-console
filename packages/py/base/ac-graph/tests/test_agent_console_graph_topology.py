"""topology: 위상 정렬, 진입/종료 노드, 사이클."""

from agent_console_contracts import EdgeSpec, Graph, NodeSpec
from agent_console_graph import topology


def graph(node_ids: list[str], links: list[tuple[str, str]]) -> Graph:
    return Graph(
        id="g",
        name="g",
        nodes=[NodeSpec(id=i, type="t") for i in node_ids],
        edges=[
            EdgeSpec.model_validate(
                {
                    "id": f"{s}-{t}",
                    "source": {"node": s, "port": "o"},
                    "target": {"node": t, "port": "i"},
                    "kind": "k",
                }
            )
            for s, t in links
        ],
    )


def test_order_entry_exit() -> None:
    topo = topology(graph(["d", "b", "a", "c"], [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")]))
    assert topo.is_dag
    # 동률은 graph.nodes 순서(b가 c보다 먼저)
    assert topo.order == ("a", "b", "c", "d")
    assert topo.entry_nodes == ("a",)
    assert topo.exit_nodes == ("d",)
    assert topo.incoming["d"] == ("b-d", "c-d")
    assert topo.outgoing["a"] == ("a-b", "a-c")


def test_isolated_node_is_entry_and_exit() -> None:
    topo = topology(graph(["x", "y"], []))
    assert topo.order == ("x", "y")
    assert topo.entry_nodes == topo.exit_nodes == ("x", "y")


def test_cycles_reported_and_order_partial() -> None:
    topo = topology(
        graph(
            ["a", "b", "c", "d", "e"],
            [("a", "b"), ("b", "c"), ("c", "b"), ("c", "d"), ("e", "e")],
        )
    )
    assert not topo.is_dag
    assert topo.cycles == (("b", "c"), ("e",))
    assert topo.order == ("a",)


def test_ignore_edge_breaks_cycle() -> None:
    g = graph(["a", "b"], [("a", "b"), ("b", "a")])
    assert not topology(g).is_dag
    topo = topology(g, ignore_edge=lambda edge: edge.id == "b-a")
    assert topo.is_dag
    assert topo.order == ("a", "b")
    assert topo.incoming["a"] == ()


def test_dangling_edges_and_duplicate_nodes_are_ignored() -> None:
    g = graph(["a", "a", "b"], [("a", "b"), ("ghost", "b")])
    topo = topology(g)
    assert topo.order == ("a", "b")
    assert topo.incoming["b"] == ("a-b",)


def test_large_chain_no_recursion_limit() -> None:
    ids = [f"n{i}" for i in range(5000)]
    links = [(ids[i], ids[i + 1]) for i in range(len(ids) - 1)] + [(ids[-1], ids[0])]
    topo = topology(graph(ids, links))
    assert len(topo.cycles) == 1
    assert len(topo.cycles[0]) == 5000
