# Changelog

## Unreleased (0.2.0)

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-teams`, so the web app can show the effective settings layer names and the
  `team.*`, `interaction.*`, `review.*` and `settings.*` issues in English (data only, no API change).
- BREAKING CHANGE: The common layer no longer reads the legacy top-level `WorkspaceSettings.default_backend`. Put the
  value in `agent_defaults.backend`.
  The common layer (`agent_layers`, `layers_for`, `node_settings`, `resolve_backends` and others) reads only
  `agent_defaults`. When only the old key is present, the common layer backend is empty and the pre-run check reports
  `backend.unresolved`. The function argument `default_backend` (the last fallback) is unchanged.
- Consumer range: `agent-console-teams>=0.2,<0.3`.
- `graph_dependencies` and `agent_dependencies` take the optional argument `scope_layers` (scope layers right below
  Common, the same value as `layers_for`). The `resources[]` attachments of the layer values are added as `shared`
  after the common layer attachments. The default `()` behaves as before.
- Numbering of new node and edge ids in suggestions now uses `numbered_id` from `agent-console-numbered-id` (same
  behavior). New dependency `agent-console-numbered-id`.
- Session summary (contract 0.13.2): `session_summary(plan, strategies) -> GraphSessionSummary | None` (the same rule
  as the web `sessionView.sessionSummary`) and `edge_sessions(plan, strategies)`. Session values are open strings from
  the descriptors and are counted per value (value names and strategy ids are not compared). None when no edge has a
  session value.
- Cleanup: **public API removal**: removed `TeamIssueCodes.DELEGATION_TOO_DEEP` (an old alias). Use
  `TeamIssueCodes.DELEGATION_DEPTH_EXCEEDED` (the value `delegation.depth_exceeded` is the same).
- The delegation strategy descriptor `shares_session` is honored. `session_grant` does not add the interaction kinds
  and wait limits of delegates of a non-sharing strategy (for example `host`) to the delegator's session. New public
  functions `shares_session(link, strategies)` and `runs_in_own_session(plan, node_id, strategies)`,
  `session_owner(plan, node_id, strategies=None)` (stops at delegates with their own session) and
  `prepare_run(..., strategies=None)` (when given, the engine wait grant equals the session grant). The backend
  `validate_settings` hook also checks delegates with their own session against their own grant. The test kit
  `s_far` has `shares_session=False`.
- `team_settings(graph, workspace, *, scope_layers=())` (effective values at the team level),
  `resolve_backends(scope_layers=)`, and a re-export of `Layer`.
- `TeamPlan.label_of` uses label, then the bound definition id, then the node type title. `node_display_name` and
  validation messages use label, then the agent definition name, then that order (the node id is the last fallback).
- `layers_for`, `agent_layers`, `node_settings` and `effective_settings` take the optional argument `scope_layers`
  (generic layers inserted as is right below Common, for example a project layer). The default `()` behaves as before.
  The package does not know about projects.
- `graph_dependencies` includes the child team of nested team nodes
  (`DefinitionDependency(kind = team_kind, node_id, version)`, new field `version`), for export ordering.
- Nested team rules `_rules_teams.check_nested_teams` (`team.recursive`, `team.nesting_exceeded`,
  `team.team_not_found`, `team.child_no_entry`), `validate_team(teams=)`, `TeamLookup`, `find_team`,
  `with_team_settings`, `merge_overrides`, `TeamPlan.team_refs` and `team_versions`, `TeamConventions.team_kind` and
  `node_version_key`, and `TeamIssueCodes.TEAM_*`. The test tool `Kit` gained nested team nodes (`nest`) and
  `graph(graph_id=)`.
- `RunPreparation.delegation_settings` (the effective setting `delegation`: defaults, then Common, then the team, for
  `GraphRuntime.start(delegation_settings=)`, the delegation depth limit during a run) and `delegation_settings()`.
- Updated validation rules. Graph checks use `cycle_edge=descriptor_cycle_edge` (flow cycles closed by a cycle edge
  and review rejection returns are allowed), `flow.max_iterations_invalid` and `flow.loop_invoked_only`, the
  `composable` decision for mixed delegation with a `team.mixed_strategies` suggestion (change the edge type), the
  delegation depth code value is `delegation.depth_exceeded` (`details.path`), and nodes reached only by cycle edges
  report `team.unreachable`. Injected `validate_team(edge_checks=)`, `flow_settings()`,
  `SuggestionBuilder.replace_kind` and `make_issue(path=)`. `testing.Kit` gained a cycle edge type and a remote
  delegation strategy that can be combined (`inner` is composable too).
- `RunPreparation.flow_settings` (the effective setting `flow`: defaults, then Common, then the team, for
  `GraphRuntime.start(flow_settings=)`).

## 0.1.0

- `TeamCatalog` and `catalog_from_registries` (from a bundle of plugin registries to node, edge, delegation strategy
  and backend descriptors, with `plan` and `try_plan`). Link modules share the same reads.
- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
