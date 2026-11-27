# Changelog

## Unreleased (0.2.0)

- Model list assembly. The administrator option `model_discovery {enabled, ttl_s, failure_ttl_s, timeout_s,
  disabled_backends}` builds `BackendModelCatalogService` (the same masking and secret check as readiness,
  `build_model_catalog_service`). New route `GET /backends/{id}/model-catalog?refresh=` (`BackendModelCatalog`,
  `Cache-Control: no-store`; failures are 200 with `discovery.state = failed` and a warning issue; an unknown backend
  is 404). `GET /backends/{id}/models` keeps its shape and now returns the same merged list (configured first,
  `sources` filled). A finished sign-in session or a sign-out clears that backend's cache
  (`build_login_service(on_account_change=)`); without the sign-in service the routes still work. Shutdown stops
  lookups in progress. `build_router(model_catalog=)`. Requires `agent-console-runtime>=0.2,<0.3` and
  `agent-console-contracts>=0.16.1,<0.17`. Consumer range: `agent-console-mod-runs>=0.2,<0.3`.
- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-mod-runs`, so the web app can show the module description and settings and the
  `runs.storage_memory` and `team.rules_unavailable` issues in English (data only, no API change). Log lines are now
  in English.
- The `GET /runs/{id}` snapshot (including `?project=`) shows the finished status of a run in this app only after the
  events up to `run.<status>` are stored (`RunService.live_view`: the engine stores the final run first, so in between
  the snapshot shows the handle's previous status, end time, error and totals, and the stored copy for the rest).
  Previously the finished status could appear together with a `last_seq` and event list that lacked the final event.
  No contract or table change.
- A project whose registration was removed (`UnknownSpace` of `RecordsStores`) is treated as an unreadable place:
  reads in the `run_id` place are skipped (REST 404 `not_found`; `?project=` queries give 404 `project.not_found`),
  writes go to the pending file (reason `not_found`), and restart recovery waits for the next open. Previously
  exceptions escaped from `runs.reader`, `runs.events`, WS replay and writes during a run.
- `runs.reader.list_node_runs_many` and `runs.events.list_many` (batched store reads): reads once per place of the run
  (the host or a space this process knows). Runs in unreadable places (`RecordsUnavailable`) are left out. No table
  change.
- Blocks project runs that no provider covers. The optional method `accepts_project` of `runs.scopes`
  (`RunProjectScoper`): when the optional port `projects.lookup` is present but no provider covers the project,
  starting a run, a chat turn, resuming and project-based validation (`definitions_for`, `load_graph(project_id=)`,
  `check_project`) are refused with 409 `feature_unavailable` (`details = {module, port: "runs.scopes", project_id}`)
  and no run is created. While this blocks, `server.warnings` has a warning with the same code and `details.port`. New
  setting `unscoped_project_runs` (`policy` reject or allow, `message`), new public names `RunProjectScoper`,
  `UnscopedProjectRuns`, `unscoped_project_policy`, `unscoped_project_warning` and `UNSCOPED_PROJECT_PORT`, and
  `RunService(unscoped_project=)`, `accepts_project`, `has_project_scope` and `unscoped_project_error`. `graph_of_run`
  is not blocked. No contract or table change.
- `GET /runs/project-counts?source=app`: counts only root runs in the app (host) database (project record databases
  are not read). Omitted means the app database plus the record databases of registered projects that are not
  archived, as now. Other values give 422. No contract change.
- `GET /runs/{id}/locate` (`RunLocation`, contract 0.14.8): from a run id to the record space that holds the run (the
  spaces this process knows plus, read-only, the record databases of registered projects from the optional port
  `projects.lookup`, up to the limit `locate_max_projects` (default 200); app records = null; for a running run, the
  handle's `project_id`). 404 when not found, 409 `run.ambiguous` (`RunAmbiguousError`) when in several places. The
  found space is remembered as the `run_id` place (`SpaceRecorder.locate`, `agent_console_store.SpaceLocator`: the
  same policy as conversations). WS `run:<id>` also finds an unknown run through `RunService.locate` (in a worker
  thread). New module setting `locate_max_projects`, new public names `PROJECTS_LOOKUP` and `RunAmbiguousError`. No
  table change.
- `check_project(..., graph=)`: checks a draft graph instead of the stored copy, with the same sources and scope.
- `RunService.check_project(graph_id, project_id)`: validates with the same definition sources (`definitions_for`)
  and run scope (`scope`) as a run in that project (used by the validation summary of a space's team list).
- `GET /runs/page` gained `agent_id`, `conversation_id` and `root` (the same meaning as the old `GET /runs`), and
  `has_children` on every row (contract 0.13.2 `Run.has_children`). Cursor and source chaining rules are unchanged.
- Contract 0.13.1: `MOVE_BUSY` uses the contract constant `KnownIssueCodes.RUN_MOVE_BUSY` (same value).
- `RunService.host_id(project_id)` (the `host_id` this app writes on runs of that space; None when there is no space
  or no record space): auto-advance picks only runs of its own app from the run history.
- `GET /runs/page` (`RunPage`; `cursor`, `limit`, `project`, `root_only`, `status` (repeatable), `graph_id`,
  `label=<key>=<value>` (repeatable, AND) and `source`). When a record space exists, the cursor continues from the end
  of the folder records to the old app database records (`source=app`). `POST /runs` `labels` (root run,
  `RunService.start_graph` and `start_run(labels=)`), `GET /runs/{id}/events?node=`, the old `GET /runs` marked
  deprecated in OpenAPI, and 400 `bad_request` (`InvalidCursor`, `RunQueryError`). `runs.reader` gained `page` and
  `descendants` (following the space place).
- Lineage `runs` `runs_0004` (`run_labels(run_id, key, value)` plus the index `ix_run_labels_kv` (`key`, `value`,
  `run_id`); upgrading fills it from the root run's `doc.labels`, downgrading only drops the table). Moving old records
  also moves label rows (with a test). No route change at this point.
- `POST /runs/move-to-project` (old runs in the app database → the project record database, `RunMover`), and the port
  `runs.move_hook` (`ConversationRunMove`, the run hook attached to moving conversations). No table change.
- Optional port `records.spaces`: runs with a `project_id` (including children) are written to that project's record
  database (`SpaceRecorder`, recording `host_id`), checked before start (409 `project.records_unavailable`, 404
  `project.not_found`); when a space is first opened only runs with this app's `host_id` are recovered
  (`recover_space`); losing the record database during a run gives a pending line plus cancellation. `?project=`,
  `?source=app`, `POST /runs/{id}/mark-interrupted` and the setting `records_space_prefix`.
- The `runs` lineage descriptor has `scopes=("app","project")` (it is also applied to project record databases).
- Moved the event type prefixes of the observe tab from a web constant (`OBSERVE_PREFIXES`) to data. Package default
  data `data/observe_event_prefixes.json` (`hook.`, `mcp.`), the server administrator option
  `observe_event_prefixes` (null = default, a list = replace, `[]` = off), the route `GET /observe-event-prefixes`
  (`list[str]`, no contract change), the public API `DEFAULT_OBSERVE_EVENT_PREFIXES`, `load_observe_event_prefixes`
  and `observe_event_prefixes_of`, and `build_router(observe_event_prefixes=)`.
- Six backend account sign-in routes (`POST /backends/{id}/login`, `GET /backends/login/current`,
  `GET|DELETE /backends/login/{sid}`, `POST /backends/login/{sid}/input` and `POST /backends/{id}/logout`), the
  setting `backend_login` (`enabled` on by default, `timeout_s`, `timeout_max_s`, `heartbeat_s`, `retain_s` and
  `screen_max_lines`), `readiness.build_login_service`, an error map (sign-in 409, 404, 422 and 413), and cancellation
  of sessions in progress in the stop hook. The input body is checked directly so that default validation errors do
  not echo the value back.
- `plugins.bind_redactor(registries, redact)`: after the secret resolver is built, gives `secrets.redact` to node and
  edge types that build decision evidence (`RedactorConsumer`).
- Optional port `runs.scopes` (`RunScoper`, `RunScope`): on every start, the request `project_id` decides the node
  services and warnings of this run (before checks and preparation). The optional preparation attribute
  `run_context` (overridden per key) → the `run.started` payload, also passed to child run preparation.
- Optional preparer method `annotate_issues` (`RunIssueAnnotator`). The blocking response text = a heading + the
  first error issue, and `fix` = the first button. The 409 for resuming a child run has an [Open top-level run] action
  (role `runs`).
- `GET /condition-operators`, `GET /runs?root=`, `children` of `GET /runs/{id}` (direct children, in creation order)
  and `GET /interactions?root=`. The plugin loader gained the condition operator group (`condition_operators`) and
  `bind_condition_operators` (gives the bundled registry to node and edge types that use operators). The child run
  preparer `RunService.prepare_child` (the same `runs.preparers` checks and preparation) is plugged into the engine.
  `InteractionService.list(root_run_id=)`. Added the dependency `agent-console-conditions`.
- The optional preparation attribute `flow_settings` (`RunPreparation.flow_settings`, the last value that is not
  None) is passed to `GraphRuntime.start(flow_settings=)`. Older preparers without this attribute still work.
- Migration lineage `runs` (`runs_0001` an empty base, `runs_0002` the lineage's new columns and indexes, version
  table `alembic_version_runs`). `storage.py` became the `storage/` package (`BRANCH`). Module descriptor
  `migrations=(BRANCH,)`.
- Removed read compatibility for the old top-level `runtime`, `backends` and `working_directory`. The environment
  variables `WORKING_DIRECTORY` and `MAX_CONCURRENCY` are unchanged.

## 0.1.0

- First release (from the scripts/pkgkit template `module`).
- Moved the run assembly from `apps/server` (engine, runs, events, interactions, resume, descriptors and agent
  activity routes, WS `run:` and `interactions`, restart recovery, applying backend settings). Team rules, node
  services and chat resume come in through `runs.preparers`, `runs.services` and `runs.resume_handlers`. Settings
  `runtime`, `backends`, `working_directory` (old top-level keys), `run_files_dir`, `min_redact_chars`,
  `resume_origin` and `activity_limit`.
