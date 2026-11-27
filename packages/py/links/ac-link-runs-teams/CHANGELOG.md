# Changelog

## Unreleased (0.2.0)

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-runs-teams`, so the web app can show the link module description and settings in English (data only, no
  API change). Log lines are now in English.
- BREAKING CHANGE: `TeamRules` no longer reads the legacy `WorkspaceSettings.default_backend`. It does not fill the
  node service `DEFAULT_BACKEND` from settings and does not pass it as the fallback to validation or preflight. Put the
  value in `agent_defaults.backend`.
  The node service key `DEFAULT_BACKEND` (`ac-nodes-core`) and the `default_backend` argument of `resolve_backends`
  and `validate_team` remain (an extension point the host injects). The minimal README example reads
  `agent_defaults.backend`.
- Consumer range: `agent-console-link-runs-teams>=0.2,<0.3` (depends on `agent-console-teams>=0.2,<0.3`).
- Pre-save checks for `?project=` validation call the optional check method `space_issues` (`SpaceDefinitionCheck`,
  based on that space, for example looking up attached resources only in that space). Without it, `issues`. Optional
  arguments `definition_check_issues(space=)` and `with_definition_checks(space=)`.
- `TeamRules.run_working_directory` joins relative paths onto `WORKING_DIRECTORY` (`resolve_working_directory`, the
  same rule as nodes).
- `POST /graphs/{id}/validate` takes an optional `?project=` (based on runs in that project,
  `ProjectRunChecker.check_project(graph_id, project_id, graph=)` and `load_graph(project_id=)`). Without it, 409
  `feature_unavailable` (`build_router(project_unavailable=)`).
- Validation summaries for the team list of a space (`?project=`): `ValidationSummaries.space_summaries` (a
  fingerprint cache per space). Computed only when `runs.starter` has the optional method
  `ProjectRunChecker.check_project`.
- Server administrator option schema `RunsTeamsLinkSettings` (`issue_fixes_file` replaces the fix button table; an
  empty table file turns it off) and `issue_fixes_of`. The module passes it to `TeamRules(issue_fixes=)`.
- Preparation (`prepare`) passes the delegation strategy descriptors to `prepare_run(strategies=)`, so the engine wait
  grant is per session (honoring `shares_session`).
- The node service `SCOPE_LAYERS` is applied to pre-run checks and preparation. The preparation result
  `TeamRunPreparation.run_context` has the effective run folder of the run (`RUN_CONTEXT_CWD` = `cwd`,
  `TeamRules(cwd_key=)`), and `run_working_directory`.
- Fix button table `IssueFixes` (data `data/issue_fixes.json`, `DEFAULT_ISSUE_FIXES`, `load_issue_fixes`).
  `TeamRules.annotate_issues` (adds `fix` to validation issues), `TeamRules.error_fix` (node service `ERROR_FIXES`),
  and the argument `issue_fixes`.
- Node service `TEAM_LOOKUP` (reading a team = `runs.starter.load_graph(id, version_hash)`) and nested checks in the
  team rules (`TeamRules(graphs=)`, `find_team`). The companion module for standalone runs, `LocalChecker.load_graph`,
  follows the version hash.

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- Moved team rule checks, run preparation (`runs.preparers`), node services (`runs.services`), list validation
  summaries (`graphs.validation`, a workspace fingerprint cache) and `POST /graphs/{id}/validate` out of
  `apps/server`.
