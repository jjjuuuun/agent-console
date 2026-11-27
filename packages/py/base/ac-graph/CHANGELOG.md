# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-graph`, so the web app can show graph validation issues (by code) and port
  labels in English (data only, no API change).
- Cleanup: removed the unused direct dependency `agent-console-registry` (no imports). No public API changes.
- Validation messages refer to nodes by name (label, then the type title). Node and edge ids appear only in `node_id`,
  `edge_id` and `details`.
- With `validate_graph(cycle_edge=)`, a `cycle` issue carries a suggestion to change the returning edge to the cycle
  edge type (`remove_edge_ids` plus `add_edges`) and a message with the names (unchanged when no matching type
  exists).
- Loops: the public predicate `descriptor_cycle_edge` (descriptor `cycle`), the pure function
  `loop_regions(graph, edge_types) -> {edge_id: LoopRegion}`,
  `effective_max_iterations(edge, descriptor, settings_value)` and the constant `CYCLE_LIMIT_CONFIG_KEY`
  (`max_iterations`).

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
