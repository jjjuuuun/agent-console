# agent-console-graph

Pure logic for graph definitions: structure validation, port resolution, topological sort and cycle checks, version hashes.
It does not know any specific node or edge type. The type list (descriptors) and the dynamic port resolver are **passed in as arguments**.

## Installation

Inside the workspace:

```bash
uv sync --all-packages
```

Standalone install (from another project):

```bash
uv pip install ./packages/py/base/ac-graph
```

Dependencies: `agent-console-contracts`, `jsonschema`, `referencing`

| Dependency | What | Why | Alternatives |
| --- | --- | --- | --- |
| `jsonschema` (>=4.23) | Validates node and edge `config` against the type's `config_schema` | The de facto standard implementation that supports every draft including JSON Schema 2020-12. It reports error locations (`absolute_path`) that convert directly to `Issue.path` (JSON Pointer). Kept in one place, `_schema.py`, so it is easy to replace | `fastjsonschema` (fast, but only the first error and weak location info), generating Pydantic models dynamically (only part of the schema features) |

| `referencing` (>=0.28, a jsonschema dependency) | Sets the `$ref` resolution registry explicitly | So that external `$ref` (URLs, files) are **not fetched** and are treated as unresolvable (`invalid_config_schema`). Only local `#/...` and `$defs` are allowed | Leaving it to jsonschema's default behavior (which may change between versions) |

> mypy types come from `types-jsonschema` in the root dev group.
> Validators per descriptor are cached within one `validate_graph` call (5,000 nodes ≈ 0.2 seconds).

## Public API

```python
validate_graph(graph, node_types, edge_types, *, resolve_ports=None, cycle_edge=None,
               validate_node=None) -> list[Issue]
graph_hash(graph) -> str                 # sha256 hex
canonical_graph(graph) -> dict           # canonical document that is hashed
topology(graph, *, ignore_edge=None) -> Topology
node_ports(descriptor, config, resolve_ports=None) -> PortSpec
schedule_view(graph, node_types, edge_types) -> ScheduleView
non_flow_edges(edge_types) -> EdgeFilter   # for topology(ignore_edge=): true when scheduling != flow
descriptor_cycle_edge(edge, descriptor) -> bool          # for validate_graph(cycle_edge=): true when the descriptor has a cycle
loop_regions(graph, edge_types) -> dict[str, LoopRegion] # cycle edge id → loop region
effective_max_iterations(edge, descriptor, settings_value=None) -> int | None
```

- `node_types` / `edge_types`: iterables of `NodeTypeDescriptor` / `EdgeTypeDescriptor` (several versions allowed).
  Without `NodeSpec.type_version` the latest version with the same id is used; edges always use the latest version.
- `resolve_ports(descriptor, config) -> PortSpec`: the dynamic port resolver (`PortResolver`). It usually wraps the node type implementation's
  `resolve_ports(config)`. Without one, dynamic-port nodes get a `ports_unresolved` warning and port checks are skipped.
- `cycle_edge(edge, edge_descriptor) -> bool`: when true, that flow edge is left out of the cycle check. By default only DAGs are allowed.
  Edges whose descriptor `scheduling` is not `flow` (`none`, `entry`, `exit`) are always left out of the cycle calculation
  (for example, `user → A →(reply) user` is not a cycle).
- `validate_node(node, descriptor) -> Iterable[Issue]`: semantic validation beyond the schema (called only for nodes that pass the schema).

### Issue code (`GraphIssueCodes`)

| code | Target | severity | `path` / `details` |
| --- | --- | --- | --- |
| `duplicate_node_id` | node_id | error | |
| `duplicate_edge_id` | edge_id | error | |
| `unknown_node_type` | node_id | error | `{type, type_version}` |
| `unknown_edge_type` | edge_id | error | `{kind}` |
| `invalid_config` | node_id or edge_id | error | `path` = JSON Pointer relative to config, `{validator, schema_path}` |
| `invalid_config_schema` | node_id or edge_id | error | The type's `config_schema` itself is wrong (metaschema violation, unresolvable `$ref`), `path=""` |
| `port_resolution_failed` | node_id | error | `{error}` (exception class name) |
| `ports_unresolved` | node_id | warning | Dynamic ports but no resolver |
| `unknown_node` | edge_id | error | `{end: source\|target, node}` |
| `unknown_port` | edge_id | error | `{end, node, port, available}` |
| `cycle` | graph | error | `{nodes: [...]}` (strongly connected component, including self loops). Edges for which the `cycle_edge` predicate is true are left out. When a predicate is given, fix suggestions are attached (below) |

### Loop regions

- **Cycle edge** = a flow edge whose edge type descriptor has `cycle` (`CyclePolicy`). Names are not looked at.
  With `validate_graph(..., cycle_edge=descriptor_cycle_edge)`, every flow cycle must contain at least one cycle edge (otherwise `cycle`).
- **"Change to a loop edge" suggestion** (when `cycle_edge` is given): for each back edge in a cycle group (an edge that returns to the search path when you follow
  depth-first from the nodes entered from outside the group), the suggestion replaces it with the first flow type for which the predicate becomes true and whose `connects` (node type
  `role`) and config schema fit (hidden types excluded): `Issue.suggestions[{id: "cycle:<edge>:<type>", label,
  patch: {remove_edge_ids: [edge], add_edges: [same id and ports, new type, only the config keys the new schema declares]}}]`. If no type fits,
  there is no suggestion and the message stays the same.
- `loop_regions`: for each cycle edge `e(s → t)`, `LoopRegion{edge_id, nodes, entry=t, exit=s}`. `nodes` = nodes on the flow paths from `t` to `s`
  (in `graph.nodes` order, calculated with every cycle edge left out, so the inner region of a nested loop is a subset of the outer region). If `s = t`, `(s,)`.
  Forward edges that do not close a cycle and edges that point to missing nodes are not in the result.
- `effective_max_iterations`: edge config `max_iterations` (`CYCLE_LIMIT_CONFIG_KEY`) → setting value → descriptor `cycle.max_iterations`
  (omitted = inherit). None if the edge is not a cycle edge or the config value is not an integer; values below 1 are returned as is (the caller decides).

```python
>>> from agent_console_contracts import CyclePolicy, EdgeTypeDescriptor, Graph
>>> from agent_console_graph import loop_regions
>>> again = EdgeTypeDescriptor(id="my-again", title="다시", cycle=CyclePolicy(max_iterations=2))
>>> loop_graph = Graph.model_validate(
...     {
...         "id": "g",
...         "name": "g",
...         "nodes": [{"id": "a", "type": "x"}, {"id": "b", "type": "x"}],
...         "edges": [
...             {"id": "ab", "source": {"node": "a", "port": "o"},
...              "target": {"node": "b", "port": "i"}, "kind": "my-wire"},
...             {"id": "back", "source": {"node": "b", "port": "o"},
...              "target": {"node": "a", "port": "i"}, "kind": "my-again"},
...         ],
...     }
... )
>>> loop_regions(loop_graph, [again])["back"].nodes
('a', 'b')

```

### `graph_hash` normalization rules

1. Serialize with the contract models (`mode="json"`, aliases); an omitted field equals a field set to its default. Preserved unknown fields are included.
2. Remove display-only fields: graph `ui`, node `position` and `layout`, edge `layout` (screen layout).
3. Sort `nodes` and `edges` by `id` (list order does not matter). Other list orders are kept.
4. Canonical JSON (sorted keys, separators without spaces, UTF-8) → sha256 hex.

### `schedule_view`

Calculated only from the edge descriptor `scheduling` (`flow`, `none`, `entry`, `exit`) and the node descriptor `executable` (no names are known).

| Field | Meaning |
| --- | --- |
| `entry_nodes` | Executable nodes that an `entry` edge enters (entry points). **Only explicit edges**; nothing is inferred from the graph shape |
| `scheduled` | Executable nodes with at least one incoming `entry` or `flow` edge (scheduled nodes) |
| `incoming` / `outgoing` / `exits` | Edge ids of the `entry` and `flow` inputs of scheduled nodes, the `flow` outputs per node, and the `exit` outputs |
| `exit_nodes` | Nodes that an `exit` edge leaves (nodes that produce the reply) |
| `scheduling`, `*_edges` | Classification per edge and per kind (edges of unknown types are left out) |
| `topology` | Topology calculated from `flow` edges only |

## Minimal usage

```python
>>> from agent_console_contracts import (
...     EdgeTypeDescriptor,
...     Graph,
...     NodeTypeDescriptor,
...     PortDef,
...     PortSpec,
... )
>>> from agent_console_graph import graph_hash, topology, validate_graph

>>> src = NodeTypeDescriptor(
...     id="my-src", title="Src", static_ports=PortSpec(outputs=[PortDef(name="o")])
... )
>>> dst = NodeTypeDescriptor(
...     id="my-dst", title="Dst", static_ports=PortSpec(inputs=[PortDef(name="i")])
... )
>>> wire = EdgeTypeDescriptor(id="my-wire", title="Wire")
>>> graph = Graph.model_validate(
...     {
...         "id": "g",
...         "name": "g",
...         "nodes": [{"id": "a", "type": "my-src"}, {"id": "b", "type": "my-dst"}],
...         "edges": [
...             {
...                 "id": "e",
...                 "source": {"node": "a", "port": "o"},
...                 "target": {"node": "b", "port": "i"},
...                 "kind": "my-wire",
...             }
...         ],
...     }
... )
>>> validate_graph(graph, [src, dst], [wire])  # no problems
[]
>>> topology(graph).order
('a', 'b')
>>> len(graph_hash(graph))  # sha256 of the normalized graph (identifies the version)
64
>>> [i.code for i in validate_graph(graph, [src], [wire])]  # an unknown node type becomes an issue
['unknown_node_type']

```

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-graph`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/base/ac-graph/tests
```
