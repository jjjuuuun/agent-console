# Changelog

## Unreleased (0.2.0)

- Backend model discovery (a new extension point). Optional capability `ModelDiscoveryCapableBackend`
  (`discover_models(ctx, timeout_s) -> ModelDiscoveryResult`, declared with `capabilities.model_discovery`, contracts
  0.16.1), `supports_model_discovery`, the reason names `ModelDiscoveryReasons`, the pure function `merge_models` (the
  configured list first and in its order, discovered-only models after it in backend order; the same id = one entry
  where a non-empty configured `title`, `description` and `context_window` and the configured `attributes` keys win;
  `sources` filled), and the shared service `BackendModelCatalogService` (`catalog(backend_id, refresh=)`, `models`,
  `invalidate`, `aclose`; a per-backend memory cache `ttl_s`, a failure cache `failure_ttl_s`, one lookup for
  concurrent requests, stale-while-refresh with the last good list, failures as 200 data with the warning issue
  `backend.model_discovery_failed`, `disabled`/`unsupported` states, length limits `ModelListLimits`, injected
  `redact`, `has_secret`, `clock` and `monotonic`; logs carry only the backend id, state, reason, method, count and
  elapsed time), the text data `ModelCatalogTexts`, and the constants `DEFAULT_MODEL_TTL_S`,
  `DEFAULT_MODEL_FAILURE_TTL_S`, `DEFAULT_MODEL_DISCOVERY_TIMEOUT_S`, `SOURCE_CONFIG` and `SOURCE_DISCOVERED`.
  `BackendLoginService(on_account_change=)` is called with the backend id after a sign-in session ends or a sign-out
  returns (listener errors are logged and ignored). Requires `agent-console-contracts>=0.16.1,<0.17`. Consumer range:
  `agent-console-runtime>=0.2,<0.3`.
- Service sentences with values are also sent as source template + values (contracts 0.16.1 `text_templates`).
  `ReadinessTexts.probe_timeout`, `LoginTexts.expired` and `LoginTexts.logout_timeout` now use `{seconds}` and
  `{minutes}` instead of `{seconds:g}` and `{minutes:g}` (same output: the value goes through `compact_number`); the
  connection test timeout, sign-in expiry and sign-out timeout responses carry `text_templates["/message"]`. New field
  `LoginProgress.text_templates` (driver → service): the service keeps only entries whose filled text equals the
  field, keeps warning templates when it stops a session, and masks templates with the response.
  `BackendReadinessService` and the sign-out path also drop backend templates that do not match their field. New
  helpers `matching_text_templates` and `compact_number`. Text a server administrator changes through `texts` is not
  translated by the web app (it is no longer the catalog key); add it to a catalog folder to translate it.
- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-runtime`, so the web app can show the engine error and issue codes in English
  (data only, no API change). Internal log messages are now in English.
- `GraphRuntime.start(labels=)`: only recorded as `Run.labels` of the root run (child runs do not inherit them; the
  caller checks limits).
- Backend account sign-in extension point: the optional capabilities `LoginCapableBackend` and
  `LogoutCapableBackend`, `LoginDriver`, `LoginProgress` and `BackendLoginContext`, the session service
  `BackendLoginService` (one session at a time, time limit, heartbeat, cancellation, cleanup on shutdown, masking and
  logging rules), `mask_values`, and the errors `LoginUnsupportedError`, `LogoutUnsupportedError`, `LoginBusyError`,
  `LoginRefusedError`, `LoginSessionNotFoundError` and `LoginInputError`. Test helper module `testing_login`.
- `GraphRuntime.start(run_context=, start_warnings=)`: run context added to the `run.started` payload (it does not
  overwrite status fields) and warnings emitted as `log.warning` after `run.started`. A child run inherits the parent
  context unless `ChildRunPreparation.run_context` is given.
- Optional hook `NODE_NAME_HOOK` (`display_name(config, services)`) and `node_display_name`. Run failure summaries
  name the node by its name (`'<이름>' 실패: …`, `details{node_id, node_name, error}`) followed by the cause's `fix`.
  Delegation refusal, seed and resume issue messages no longer contain the node id (it is in `details.node_id`).
  Refusing to resume a child run comes before the status check, and `details` gained `status`. The test node `t.step`
  has `name` and `fix`.
- Child runs (`root_run_id`) are not resumed on their own: `resume_options` is an empty list, and
  `ResumeService.resume` raises `RunNotResumableError` (`details{run_id, root_run_id, parent_run_id}`).
- Mixed delegation: the optional protocol `ComposableDelegation` (`contribute(plan, ctx) -> DelegationContribution`),
  `DelegationContribution{subagents, host_tools, options, wrap_sink}`, the pure functions `merge_contributions`
  (name clashes and option conflicts = `DelegationIssueCodes`) and `apply_contribution`, and the type `SinkWrapper`
  (`_delegation.py`).
- Reasons and warnings of edge decisions: `Activation.condition` and `warnings`, and the new result
  `Blocked(reason, condition, warnings)` (dead-path + `edge.skipped`). The engine carries `edge.traversed.condition`
  and emits warnings as `log.warning`. `validate_graph_with` calls the optional capability
  `EdgeValidator.validate_edge` (`EdgeValidationContext`). `NodeResult.structured` and `NodeRunView.structured`
  (structured results that are not stored).
- Loop (cycle edge) runs: a descriptor `cycle` edge reopens the loop region as a new iteration
  (`NodeRun.iteration`), with the events `loop.iteration` and `loop.exhausted`, limit inheritance (edge config →
  `flow_settings` → descriptor), the safety limit `flow.max_node_runs`
  (`RuntimeErrorCodes.MAX_NODE_RUNS_EXCEEDED`), `GraphRuntime(flow_settings=)` and `start(flow_settings=)`,
  `NodeRunView.iteration`, `Incoming.carried`, `NodeContext.previous_session_id`, the validation
  `cycle_edge=descriptor_cycle_edge`, iteration handling in recovery and resume, the test edge `t.loop`, the `t.step`
  config `per_iteration` and `session`, and `Probe.seen` (`NodeSeen`).
- Platform tool runtime types `HostTool`, `HostToolResult` and `HostToolHandler` and `AgentRequest.host_tools`
  (runtime only, not serialized), and the shared backend helpers `call_host_tool`, `duplicate_host_tool_names` and
  `object_input_schema` (new module `_host_tools.py`).

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior change.
