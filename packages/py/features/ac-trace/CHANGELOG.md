# Changelog

## Unreleased

- Internal log messages are now in English.
- A call NodeRun (`call`) becomes a separate session `node` span under the delegator span
  (`call:<path>#<call>`, one per call round), with a delegator-to-call link (edge id and type from
  `build_trace(call_edges=)`) and a preview of the delegated task (`node_runs=` input). Each loop iteration gets its own
  span (`node:<node>#<attempt>@<iteration>`, `iteration`), and passing a cycle edge is a link to the next iteration.
  Child run groups (`children=`) sit under the node span that `run.child_started` points to (`run_id`,
  `child_span_id`). A handoff starts from the most recent span of that node. New public functions `call_span_id` and
  `child_span_id`, and `node_span_id(…, iteration)`.

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
