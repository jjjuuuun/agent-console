"""그래프 저장 결과를 REST 계약 모델(`VersionedGraph`, `GraphSummary`)로 바꾸는 얇은 도우미."""

from agent_console_contracts import Graph, GraphSummary, VersionedGraph

from .interfaces import DefinitionStore, StoredDefinition
from .kinds import SCOPE_FIELD

GRAPH = "graph"


def to_versioned_graph(stored: StoredDefinition) -> VersionedGraph:
    """`StoredDefinition` -> `VersionedGraph`(GET/PUT/POST /graphs 응답)."""
    return VersionedGraph(
        graph=stored.model(Graph), version_hash=stored.version_hash, saved_at=stored.saved_at
    )


def list_graph_summaries(store: DefinitionStore) -> list[GraphSummary]:
    """`GET /graphs` 응답. 그래프 본문은 담지 않고 node_count·edge_count·saved_at·project를
    채운다."""
    return [
        GraphSummary(
            id=s.id,
            name=s.name,
            description=s.description,
            labels=s.labels,
            version_hash=s.version_hash,
            saved_at=s.saved_at,
            node_count=s.counts.get("nodes", 0),
            edge_count=s.counts.get("edges", 0),
            project=s.extra.get(SCOPE_FIELD),
        )
        for s in store.summaries(GRAPH)
    ]
