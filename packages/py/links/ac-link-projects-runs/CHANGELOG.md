# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-projects-runs`, so the web app can show the link module description and settings in English (data only, no
  API change). Log lines are now in English.
- The template table of the path guard now uses `ac-nodes-core.path_placeholders`: it is the same table and the same
  base (the project folder) as the run (agent node `resolve_paths`), so the checked paths equal the
  `limits.directories` the backend receives.
- `scope_run` sets the node service `WORKING_DIRECTORY` to the project folder for project runs (a relative
  `working_directory` uses the same base as the path guard and resolves against the folder; child and grandchild runs
  inherit it). Integration tests for nested team runs that the run folder and credential paths are not passed on.
- `ProjectScope.accepts_project(project_id)` (`mod-runs` `RunProjectScoper`): true when project reads are available.
  In an assembly where this link module is off (and the projects feature is on), `mod-runs` blocks runs and
  conversation turns with a `project_id` with 409 `feature_unavailable` (`details.port = "runs.scopes"`). No contract
  changes.

## 0.3.0

- **Breaking change**: the default of the setting `require_project` is now true. In an assembly with the projects
  module on, calling `POST /runs` (including conversation turns) without a `project_id` returns 422
  `project.required`. The web app always sends `project_id`. For the previous behavior, set
  `modules.options.link-projects-runs.require_project: false`. The default of the library constructor
  `ProjectScope(require_project=)` stays false.

## 0.2.0

- Pre-run checks. `ProjectScope.run_definitions` (an optional run scope method): the definition lookup source of a run
  is that project's space (`definitions.spaces`); a project that does not exist gives 404 `project.not_found`; state
  problems give 409 `project.folder_missing` or `project.manifest_invalid`; a run target that is not in the space
  gives 422 `project.not_imported` (`in_library`, through `definitions.lookup`). It does not fall back to the library.
- Rejection `errors` in the `scope_run` result: starting without a project gives 422 `project.required` (setting
  `require_project`, off by default for now and to be turned on once the web app sends `project_id`); a record database
  that cannot be written gives 409 `project.records_unavailable` (`ProjectView.records_writable` and
  `config_writable`, with the reason from `records_issue.details` as is); an `x-path` value of the effective settings
  outside the folder gives 422 `project.outside_folder` (layer name and node id; the app workspace and state folder
  are allowed, and `{workspace}` = the folder).
- New module `preflight` (building error bodies, `outside_paths_of_graph`, message data `PreflightTexts`). Ports
  `definitions.spaces` and `definitions.lookup` (optional), protocol `ProjectViews`.
- Breaking change: runs for an unregistered project are rejected with 404 (previously they ran without a layer and
  warned `project.unknown`). With `require_project` on, runs without a `project_id` are rejected too.

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- `ProjectScope`: project id to the project layer (`project_layer_value`); a project that does not exist gives a
  `project.unknown` warning. Provides the ports `runs.scopes` (run scope to the node service `SCOPE_LAYERS`) and
  `settings.scope_layers` (effective settings `?project=`), and requires `projects.lookup`.
- Settings `layer_id`, `layer_label` and `unknown_message`. `testing.memory_projects_module` for standalone runs.
