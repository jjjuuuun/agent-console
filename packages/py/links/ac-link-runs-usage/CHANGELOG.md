# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-runs-usage`, so the web app can show the link module description and settings in English (data only, no
  API change). Log lines are now in English.
- One token rollup (`IncrementalTokenRollups(batch=)`) and one event query (`MergedEventQuery(batch=)`) each run inside
  a `RecordsStores.batch` block (new public name `Batch`). With 12 projects and a limit of 8, one rollup opens 12
  spaces and the next rollup reopens 4 (previously 12). Projects deleted between listing and opening the space
  (`UnknownSpace`) are skipped on their own (previously the following projects were dropped too). Development
  dependency `agent-console-link-projects-records` (tests with the real pool).
- The "This project" token totals (`rollups(project_id=)`) read the latest `limit` runs of that `project_id` from the
  app records directly with a store condition (index `ix_runs_project_created`). Previously the latest `limit` runs of
  the app records were read first and then filtered, so older project runs were missed when there were many other
  runs. When `runs.reader` has the optional method `for_project(None)` (app records only, `mod-runs`), it is used
  (in assemblies with record spaces, `list(project_id=)` reads the project record database). Accepted shape
  `AppRunSource` (plus `project_id`), optional capability `AppScopedRuns`.
- Runs to reread are read in batches per source (with the optional methods `list_many` and `list_node_runs_many`,
  events and NodeRuns each use a batched query; otherwise per run). The first rollup runs one list, event and NodeRun
  query per source (previously three per run). Optional capabilities `BatchEvents` and `BatchNodeRuns`.
- Token totals count only root runs (`ac-usage.counts_toward_usage`, avoiding double counting of child runs).

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- Moved `usage.event_query` and `usage.token_rollups` out of `apps/server` and changed token totals to an incremental
  cache (an event seq watermark per run, subscribed to `runs.event`).
