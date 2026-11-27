# Changelog

## Unreleased (0.2.0)

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs` `ac-mod-sdd`,
  so the web app can show the module description and settings in English (data only, no API change). Log lines are
  now in English.
- The kind contributions carry `open_role` (spec `sdd`, document template `sdd:templates`, `SPEC_OPEN_ROLE` and
  `TEMPLATE_OPEN_ROLE`), so the copy dialog kind list (`CopyKindInfo.open_role`, contracts 0.16.0) can offer "Open"
  for these rows.
- Added template version comparison: `GET /sdd/templates/{id}/versions/{a}/diff` (version to current) and
  `GET /sdd/templates/{id}/versions/{a}/diff/{b}`. Both return the existing contract `DefinitionDiff` and take
  `?project=<space>` like the other version routes. The calculation is the shared `agent_console_store.diff_versions`
  (same as `mod-versions`); locations that look like secrets (`secrets.document_secret_paths`, the rules used by
  restore) are masked as `***`. New public helper `secrets.document_secret_paths`. Consumer range:
  `agent-console-mod-sdd>=0.2,<0.3`; requires `agent-console-store>=0.2,<0.3`.
- `GET /sdd/info` returns `SddInfo.reserved_template_ids` (= `TEMPLATE_ROUTE_WORDS`, contract `sdd` 1.4.0), so the
  screen can warn in the new template id field in advance. `SddService.info(scope, *, reserved_template_ids=())`.
- Fixed: Save as template (`POST /sdd/specs/{id}/save-as-template`) with a reserved path word as id now writes nothing
  and rejects the request with the same 422 `validation_failed` (`details` = `{id, reserved}`) as creating a new
  template. Ids made from the name and new ids from `rename` avoid reserved words (previously templates such as `check`
  or `variables` were created, and their GET was shadowed by fixed routes). Public function
  `template_routes.reject_reserved_template_id`.
- The document template kind data carries the reserved path words (`TEMPLATE_ROUTE_WORDS`) as
  `DefinitionKind.reserved_ids` (the copy plan suggests a new id).

## 0.1.0

- First release (from the scripts/pkgkit template `module`): REST `/sdd/*` and WS `sdd.changed`, definition kind
  contributions (document templates and specs), the user settings section `sdd`, server administrator options
  (defaults in `data/defaults.json`), space selection (`sdd.spaces`, with a standalone root without it), task
  integrations and verification sources (plugin loaders), a parse cache, content secret checks, run label display
  rules (`data/label_display.json`), the port `sdd.service`, and standalone runs with `python -m`.
- Single document template REST (`template_routes`): `POST /sdd/templates`, `GET`, `PUT` and `DELETE`
  `/sdd/templates/{id}`, `…/variables`, skeleton files `…/files[/{path}]` (ETag and If-Match = the definition version,
  content secret checks), and versions `…/versions[/{hash}[/files[/{path}]]]` and
  `POST …/versions/{hash}/restore`. The store is the same as for the `/sdd/templates` list (the library, otherwise the
  standalone root; `?project=` = a space). The reserved path words `TEMPLATE_ROUTE_WORDS` (`variables`, `check`) are
  not used as template ids. Building suspected secret issues is collected in `secrets.document_issues` (shared with the
  pre-write check of the standalone store).
- `GET /sdd/import/files` returns subfolders (`dirs`) (`ac-sdd` `list_import_files`).
