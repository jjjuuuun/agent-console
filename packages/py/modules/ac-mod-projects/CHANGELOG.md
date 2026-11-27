# Changelog

## Unreleased (0.3.0)

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-mod-projects`, so the web app can show the module description and settings in English (data only, no API
  change). Log lines are now in English.
- `GET /projects/copy/kinds` fills `CopyKindInfo.open_role` (contracts 0.16.0, `projects` 4.1.0): the kind
  contribution `open_role` first, then the kind data `DefinitionKind.open_role`, otherwise null. New public helper
  `definitions.contribution_open_roles` and `CopyService(kind_open_roles=)`.
- `GET /projects/copy/kinds` fills `CopyKindInfo.reserved_ids` (the kind data `DefinitionKind.reserved_ids`, including
  contributed kinds, contract `projects` 4.1.0), so the copy dialog can warn in the new name field before applying.
- BREAKING CHANGE: Removed `POST /projects/move-plan`, `/move`, `/scope-issues` and `ScopeService`,
  `DefinitionSnapshot`. The `snapshot_ttl_seconds` option is accepted but no longer read.
  Removed public names: `ScopeService`, `DefinitionsUnavailableError`, `CODE_DEFINITIONS_UNAVAILABLE` and
  `DefinitionSnapshot` (and `MODULE_MESSAGES` and `issues_payload` of `service.py`). The removed routes overlap with
  `/projects/{id}`, answer 405 and are not in OpenAPI. The `definitions.saved` subscription (dropping the snapshot
  cache) is gone too; the topic is still published as the space save notification. The setting
  `snapshot_ttl_seconds` is `deprecated` in the schema, and the server still starts when it is present.
- Dependency `agent-console-projects>=0.3,<0.4`. Consumer range `agent-console-mod-projects>=0.3,<0.4`.
- Applying a copy (`POST /projects/copy/apply`) writes nothing and rejects the request with 422 `validation_failed`
  (`details.issues` = error `project.copy_reserved_id`, with the suggestion `suggested_id`) when the target id (copy
  and overwrite use the source id, rename uses the new id) is a reserved word of its kind. Reserved words come from the
  kind data (`DefinitionKind.reserved_ids`, including contributed kinds), and the messages are
  `project.copy_reserved_id.rename` and `project.copy_reserved_id.write` in the setting `messages`.
- The copy kind list `CopyKindInfo.title` uses the kind data `DefinitionKind.title` when the kind contribution has no
  `title` (default kinds get names too; null when both are missing).
- Reverse references for every kind: `GET /projects/copy/items/{kind}/{id}/references?project=` returns
  `CopyItemReferences` (contract 0.14.10). It reads the definitions in the same space and finds the ones that use this
  item through `definitions.references` and the kind contribution `references` (the pure rule `find_referrers` in
  `ac-projects`). Used for the "Used by" list of the delete confirmation dialog. Without reference extraction,
  `checked` is false. `CopyService.item_references`.
- The copy plan passes the `reserved_ids` of contributed kinds to `copy_plan(reserved_ids=)` (items with reserved ids
  get a suggested new id).
- Setting `sessions_dir` (the session archive folder name, inherits `link-projects-records.session_archive.dir`): it
  is passed in the space layout together with `records_file`, so the `.gitignore` template and the
  `project.gitignore_outdated` check follow the configured names.
- Optional port `definitions.kind_contributions` (`KIND_CONTRIBUTIONS`). Space kinds = the movable kinds among the
  library kinds plus contributed kinds (including `library=False`), through `library_kinds(store, contributions=())`.
  The contributions' `references` are merged with `definitions.references` and used for copy plans and scope checks
  (`contribution_references`). Without contributions, kinds and copy results are the same as before.
- `projects.folders` has archived folders (`archived`). Removed `ProjectManager(working_directory=)` for the old log
  scope `current` and the inheritance of `working_directory` (SeedSetting). The setting `working_directory` remains but
  is not read (`deprecated` in the schema).
- Copy dialog metadata: `GET /projects/copy/kinds?project=` (`CopyKindInfo[]`: the copy kinds of that space with
  `library` and `portable`, excluding singletons and unknown kinds) and `GET /projects/copy/items?project=&kind=`
  (`CopyItem[]`, 404 for unknown kinds). `CopyService(kind_info=)`, `kinds` and `items`; kind information comes from
  `library_kinds` (defaults plus contributions).

## 0.2.0

- Breaking change: the registry is `ProjectRegistration` (folder, archived, label), and name, description and the
  project layer live in the folder manifest. Responses are `ProjectView` (status, `config_writable`, `manifest_id`,
  `kinds`, `issues`, `config_dir`, `records_*`, with a time limit). Registration uses `init_space` (writes only when
  missing and adopts otherwise; a broken manifest is not written), overlaps give 409, DELETE archives, and
  `PUT archived:false` registers again.
- New routes: `manifest/reset`, `gitignore/append`, `{id}/legacy/plan`, `copy/plan` and `copy/apply`, `folders`,
  `folders/check`, `folders/capabilities` and `folders/pick` (tested with a fake runner, loopback only, one at a time,
  and the dialog closes when the connection drops).
- Provided ports `projects.spaces` and `definitions.spaces` (space cache), optional `records.spaces`, `secrets.rules`
  and `definitions.reference_rewriters`. Entry point `agent_console.folder_dialogs`.
- Removed: the scope warnings provided through `definitions.checks`, `delete-plan` and DELETE `mode`. The old scope
  routes (`move-plan`, `move`, `scope-issues`) stayed as deprecated (removed later).

## 0.1.0

- First release (from the scripts/pkgkit template `module`).
- Project CRUD (`projects/<id>.yaml`, its own `FileDefinitionStore`), `delete-plan` and two delete paths
  (`move_to_shared` and `delete_definitions`), `move-plan` and `move` (apply), `scope-issues`, the provided ports
  `projects.lookup` and `definitions.checks`, optional `definitions.lookup`, `definitions.store` and
  `definitions.references`, and the web role `projects`.
