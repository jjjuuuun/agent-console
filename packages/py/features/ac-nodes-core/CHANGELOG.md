# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-nodes-core`, so the web app can show the node, edge, interaction and delegation
  descriptors and the node error codes in English (data only, no API change). The `input_key` description of the user
  message edge is a fixed string. Internal log messages are now in English.
- `merge_access_layers(items, *, entries_key, entry_key, default_ops)` and the key constants `ACCESS_CONFIG_FIELD`,
  `ACCESS_TOOLS_FIELD` and `ACCESS_OPS_FIELD`: tool providers (the memory and wiki link modules) merge the access
  settings attached to a field with the same rules (the copies in both link modules moved here).
- `resolve_paths(values, base)`, `path_placeholders(base)` and `WORKSPACE_PLACEHOLDER`: the agent node resolves
  templates (`{workspace}`) and relative paths in `limits.directories` to real paths based on `WORKING_DIRECTORY` and
  passes them to `AgentRequest.limits` (and `agent.limits`). Previously the templates went as is to the backend
  `add_dirs` and tool checks. Without a base, values are unchanged.
- `resolve_working_directory(value, base)`: joins a relative `working_directory` onto the node service
  `WORKING_DIRECTORY` (absolute paths, `~` and drives are unchanged). The agent node's `AgentRequest.cwd` uses this
  rule (previously a relative path was passed as is, and the backend resolved it against the server process's current
  directory).
- Cleanup: moved the history of removed nodes from the `__init__` docstring and README into this changelog. No code
  changes.
- `WhenEdge(redact=)` and `use_redactor(redact)` (`ac-conditions.RedactorConsumer`): the evaluation evidence is masked
  before it is truncated. The `sdk-subagents` descriptor states `shares_session=True` explicitly.
- Service key `SCOPE_LAYERS` (`nodes_core.scope_layers`): inserts scope layers (for example, a project layer) right
  below Common in the agent node's effective settings.
- Service key `ERROR_FIXES` (`ErrorFixer`): adds fix buttons to agent node failures. Optional agent node hook
  `display_name` (the name of the bound definition). Removed design numbers from descriptor descriptions.
- `WhenEdge.use_operators(provider)` (`ac-conditions.OperatorConsumer`): the runs module passes the host's condition
  operator registry.
- Node type `team` (`team.TeamNode`, nested team: `binds{graph, team_ref}`, role `team`, `ui_hints.shape stacked`,
  config `TeamNodeConfig{team_ref, version, input_key, reply, reply_separator, settings}`). Child runs through
  `ctx.run_child`, reply selection `pick_replies`, conversation session path keys `session_path_key` and
  `child_sessions`, the service key `TEAM_LOOKUP`, the error codes `team.lookup_unavailable`, `team.team_not_found`,
  `team.invalid_settings` and `team.child_failed`, and the wait reason `TEAM_CHILD_WAITING`. Added the role `team` to
  `connects` of the `handoff`, `loop`, `when`, `on_error`, `message` and `reply` edges.
- Edge type `delegate` (`edges.DelegateEdge`, none plus invocation `host`, config
  `DelegateEdgeConfig{strategy, result}`, `HOST_STRATEGY`). `sdk-subagents` is now `composable=true` and gained
  `contribute` (subagents plus a wrapped reply sink). Agent node config `delegation` (strategy id to strategy config)
  and mixed delegation (grouped by strategy; when all are composable, `contribute` is merged into one backend call,
  otherwise `agent.mixed_strategies`). Test-only dev dependency `agent-console-delegation-host`.
- Edge types `when` (`conditional.WhenEdge`, config `conditions`, evaluation evidence and warnings, pre-save check
  `validate_edge` through `ac-conditions.condition_issues`) and `on_error` (`conditional.OnErrorEdge`,
  `handles_failure`). `condition_subject`, `CONDITION_FALSE`. The agent node passes the backend's
  `AgentResult.structured` on as `NodeResult.structured`. New dependency `agent-console-conditions`.
- Edge type `loop` (`loops.LoopEdge`, flow plus the descriptor `cycle{max_iterations: 3}`, config
  `LoopEdgeConfig.max_iterations`), `DEFAULT_LOOP_MAX_ITERATIONS`. The agent node continues the session of the same
  node's previous iteration (`ctx.previous_session_id`), and when continuing it leaves the carried input
  (`Incoming.carried`) out of the prompt.

## 0.1.0

- Earlier history: removed the `input`, `output` and `router` nodes that had been put on hold.
- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
