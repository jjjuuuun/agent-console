# Changelog

## Unreleased (0.3.0)

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-projects`, so the web app can show the `project.copy_reserved_id` issue in
  English (data only, no API change).
- BREAKING CHANGE: Removed the old definition-scope rules `visible`, `scope_issues`, `move_plan`, `delete_plan` and
  their constants. Use `legacy_items`, `legacy_counts` and `copy_plan`.
  Removed names: `visible`, `scope_issues`, `move_plan`, `delete_plan`, `UnknownDefinitionError`,
  `MOVE_TO_SHARED_SUGGESTION`, `CODE_SHARED_USES_PROJECT`, `CODE_CROSS_PROJECT`, `DEFAULT_MESSAGES` (the scope message
  table), `effective_scope` and `known_project_ids`. `CODE_UNKNOWN` and `CODE_REFERENCES_UNAVAILABLE` stay under the
  same names (moved to the module `_codes`). `ScopedDefinition`, `References`, `DefinitionId`, `legacy_*` and
  `without_scope_field` are unchanged.
- Consumer range: `agent-console-projects>=0.3,<0.4`.
- `reserved_target_issues(items, reserved_ids, *, target_index=, messages=, target_label=)`: for each item in an apply
  request whose target id (copy and overwrite use the source id, rename uses the new id) is a reserved word of its
  kind (`DefinitionKind.reserved_ids`, case-insensitive), an error `project.copy_reserved_id` is reported
  (`details{kind, id, action, target_id, reserved, suggested_id}`, plus `new_id` for rename; `path` is
  `/items/<n>/new_id` for rename and `/items/<n>/id` otherwise). The message keys `COPY_RESERVED_RENAME`
  (`project.copy_reserved_id.rename`) and `COPY_RESERVED_WRITE` (`project.copy_reserved_id.write`) are replaced
  through `messages=`. (`reserved_rename_issues`, released in the same unreleased period, was renamed to this and
  widened.)
- The `-n` collision rule of `registration_id` now uses `numbered_id` from `agent-console-numbered-id` (same public
  names and behavior). New dependency `agent-console-numbered-id`.
- Reverse references: `find_referrers(target, documents, references, *, messages=)` returns
  `ReferrerScan(keys, checked, warnings)`. It finds the definitions in the same space that use a definition through
  the injected reference extraction (the "Used by" list of the delete confirmation dialog). Without reference
  extraction, it does not read documents and reports info `project.references_unavailable` (message key
  `REFERRERS_UNAVAILABLE_MESSAGE`, default `DEFAULT_REFERRER_MESSAGES`).
- `copy_plan(reserved_ids=)`: items that would be written to the target under a reserved id of their kind get a
  warning `project.copy_reserved_id` (`CODE_COPY_RESERVED_ID`, `details.suggested_id`), and when the target does not
  have the id the default action is rename. Messages are replaced through `messages=`.
- Published the in-folder path guard `FolderGuard` (`is_reserved`, `contains_reserved`, `resolves_inside`,
  `violation`), `normalize_reserved`, `relative_inside` and `GuardViolation`. `link-projects-sdd` `ProjectSpecFiles`
  and the `link-projects-wiki` page folders use the same rules (no copies).
- Breaking change (only for the consumers `mod-logs` and `mod-projects`): removed `ProjectFolderSet.current` and
  `project_folders(working_directory=)` (compatibility for the old log scope `current`). Archived project folders are
  reported separately as `ProjectFolderSet.archived` (`archived_folders`); when the same folder is both registered
  and archived, registered wins. `project_for` still looks only at non-archived folders.

## 0.2.0

- A project is a local folder plus a copy of the configuration inside that folder. Added the dependency
  `agent-console-local-folders`.
- Added: registration rules `folder_conflicts`, `conflict_status`, `conflict_error_code`, `conflict_details`,
  `registry_conflicts`, `project_status`, `project_for_path` and `registered_folders`; path comparison `folder_key`,
  `folder_within`, `path_relation`, `resolve_folder` and `load_path_rules` (data `data/path_rules.json`); registration
  ids `folder_slug`, `registration_id` and `suggest_project_id`; merging `merge_project`, `split_project`,
  `initial_manifest`, `legacy_manifest_values`, `combined_version` and `ignored_key_issues`; copying `copy_plan`,
  `skip_warnings`, `apply_decisions`, `renames_of` and `apply_renames`; path guards `path_fields` and
  `outside_paths`; old data `legacy_items`, `legacy_counts` and `without_scope_field`.
- Changed: `project_folders` no longer falls back to the server's `working_directory` (projects without a folder and
  archived projects are excluded), and the result has `entries` (id plus folder) and `project_for`. `current` is a
  compatibility value filled only when `working_directory=` is given (removed later). `project_layer_value` reads
  `Project.folder`.
- Removed (breaking change): `suggest_log_projects`, `log_paths_from_sessions` and `normalize_path` (the log grouping
  `log_projects` is gone; use `folder_key` for path comparison).

## 0.1.0

- First release (from the scripts/pkgkit template `feature`).
- `visible`, `scope_issues`, `move_plan`, `delete_plan`, `suggest_log_projects`, `log_paths_from_sessions` and
  `project_layer_value`, the input `ScopedDefinition` (`from_document`, `from_summary`), and the injected reference
  extraction `References`.
