"""계약 0.15.0(wiki 1.3.0) 서버 쪽: ``WikiInfo.wiki_kind``·``reserved_page_names``, 그래프
``?depth=all``(``WIKI_GRAPH_DEPTH_ALL``)과 응답 ``WikiGraph.depth``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts import WIKI_GRAPH_DEPTH_ALL
from agent_console_mod_wiki import PAGE_ROUTE_WORDS

API = "/api/v1"


def _chain(client: Any, kit: Any, n: int) -> None:
    """``p0 → p1 → … → p(n-1)`` 한 줄로 이어진 위키 ``w``."""
    assert client.post(f"{API}/wiki/wikis", json={"name": "w"}).status_code == 201
    for i in range(n):
        nxt = f"[[p{i + 1}]]\n" if i + 1 < n else ""
        kit.write_page(client, "w", f"p{i}", f"# p{i}\n{nxt}")


def test_info_reports_wiki_kind_and_reserved_page_names(standalone: tuple[Any, Any]) -> None:
    client, _ = standalone
    info = client.get(f"{API}/wiki/info").json()
    assert info["wiki_kind"] == "wiki"
    assert info["rules_kind"] == "wiki-rules"
    assert info["reserved_page_names"] == list(PAGE_ROUTE_WORDS) == ["history"]


def test_info_wiki_kind_follows_installer_option(tmp_path: Path, database: Any, kit: Any) -> None:
    assembly = kit.make_assembly(
        tmp_path, options={"wiki_kind": "zz-notes", "rules_kind": "zz-rules"}, database=database
    )
    with kit.client_for(assembly) as client:
        info = client.get(f"{API}/wiki/info").json()
    assert (info["wiki_kind"], info["rules_kind"]) == ("zz-notes", "zz-rules")


@pytest.mark.parametrize(
    ("query", "depth", "paths"),
    [
        ({}, 1, {"p0", "p1"}),  # 생략 = 1(옛 클라이언트 동작 그대로)
        ({"depth": "0"}, 0, {"p0"}),
        ({"depth": "3"}, 3, {"p0", "p1", "p2", "p3"}),
        ({"depth": WIKI_GRAPH_DEPTH_ALL}, None, {f"p{i}" for i in range(6)}),
    ],
    ids=["omitted", "zero", "three", "all"],
)
def test_graph_depth_values(
    standalone: tuple[Any, Any],
    kit: Any,
    query: dict[str, str],
    depth: int | None,
    paths: set[str],
) -> None:
    client, _ = standalone
    _chain(client, kit, 6)
    res = client.get(f"{API}/wiki/wikis/w/graph", params={"center": "p0", **query})
    assert res.status_code == 200, res.text
    graph = res.json()
    assert {n["path"] for n in graph["nodes"]} == paths
    assert graph["depth"] == depth
    assert graph["truncated"] is False


def test_graph_without_center_has_null_depth(standalone: tuple[Any, Any], kit: Any) -> None:
    client, _ = standalone
    _chain(client, kit, 3)
    graph = client.get(f"{API}/wiki/wikis/w/graph", params={"depth": "all"}).json()
    assert graph["depth"] is None
    assert len(graph["nodes"]) == 3


@pytest.mark.parametrize("bad", ["x", "-1", "ALL", "1.5"])
def test_graph_bad_depth_is_422(standalone: tuple[Any, Any], kit: Any, bad: str) -> None:
    client, _ = standalone
    _chain(client, kit, 2)
    res = client.get(f"{API}/wiki/wikis/w/graph", params={"center": "p0", "depth": bad})
    assert res.status_code == 422, res.text


def test_graph_all_keeps_node_cap(tmp_path: Path, database: Any, kit: Any) -> None:
    """깊이 제한이 없어도 칸 수 상한(``graph_max_nodes``)은 그대로다."""
    assembly = kit.make_assembly(tmp_path, options={"graph_max_nodes": 3}, database=database)
    with kit.client_for(assembly) as client:
        _chain(client, kit, 6)
        graph = client.get(
            f"{API}/wiki/wikis/w/graph", params={"center": "p0", "depth": "all"}
        ).json()
    assert [n["path"] for n in graph["nodes"]] == ["p0", "p1", "p2"]
    assert graph["truncated"] is True
    assert graph["total"] == 6
    assert graph["depth"] is None


def test_openapi_documents_depth_all(standalone: tuple[Any, Any]) -> None:
    client, _ = standalone
    paths = client.get(f"{API}/openapi.json").json()["paths"]
    params = paths[f"{API}/wiki/wikis/{{wiki_id}}/graph"]["get"]["parameters"]
    [depth] = [p for p in params if p["name"] == "depth"]
    assert "all" in str(depth["schema"])
