# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-mod-imports`, so the web app can show the module description and import source
  settings in English (data only, no API change).
- `HOME_REMOVED_REASON` is in English; the host prints it to the terminal when it refuses to start.
- Optional ports `projects.folders` and `definitions.spaces`. With the ports, the source is the `.claude` of the folder
  of the query `?project=<registration id>` (the setting `project_dir` and the settings file folder are not used), and
  the save location is the query `target` (`project` by default = that project's space, `library` = the shared
  library). Without `project`, only sources that need no folder are available; `target=project` gives 422
  `project.required`, an unregistered id gives 404 `project.not_found`, and a missing space port gives 409
  `feature_unavailable`. Without the ports, the current settings apply as is (`?project=` gives 409). No assembly has
  a source for the user-global `~/.claude`. `ProjectImports`, `ImportProjectError` and `ImportTarget`.
- The import request `project` is stamped into the imported definitions (`ac-imports` `ImportService.apply`, no route
  changes).
- Removed read compatibility for the old top-level `imports`. When omitted, `project_dir` is the host
  `paths.base_dir`, and `mod-runs.working_directory` is not read as its default.

## 0.1.0

- First release (from the scripts/pkgkit template `module`).
- Moved `/resources/import/*` of `apps/server` and the import source assembly. Settings
  `modules.options.mod-imports` (formerly `imports.*`). Standalone runs attach `testing.local_definitions_module` when
  `--with` is absent.
