# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-runs-trace`, so the web app can show the link module description and settings in English (data only, no
  API change).
- `/runs/handoffs` and `/runs/{id}/trace` take an optional `?project=` (`TraceViews.in_project`: the optional method
  `for_project` of `runs.reader` and `runs.events`; without it, runs are filtered by their `project_id` through
  `ProjectRuns`). An unknown project gives 404 `project.not_found`, and records of that project that cannot be read
  give 409 `project.records_unavailable` (`ERROR_MAP`). Without the query, behavior is as before (handoff totals = host
  records, flow = where the run history found the run). Optional port `definitions.spaces`: the team of a run with a
  `project_id` at that time is read only from that space's store (`TraceViews(space_history=)`; when it cannot be
  opened, without edge types).
- `/runs/{id}/trace` attaches the flows of child runs (nested teams) recursively (`TraceViews.trace(children=True)`),
  and fills the edges of call spans (`call_edges`) and the delegated tasks (NodeRun input). `/runs/handoffs` counts
  only each run's own flow (no double counting of children). Uses `list(parent_run_id=)` and `list_node_runs` of the
  port `runs.reader`.

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- Moved `/runs/{id}/trace` and `/runs/handoffs` out of `apps/server`. The team at the time of the run comes from the
  optional port `definitions.lookup`.
