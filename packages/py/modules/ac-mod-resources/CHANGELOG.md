# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-mod-resources`, so the web app can show the module description and settings and
  the `resource.not_multi_file` and `resource.reserved_file_name` issues in English (data only, no API change). Log
  lines are now in English.
- Optional port `definitions.spaces`. `/resources` and `/resources/{id}/…` (list, read, create, save, delete, content,
  multiple files) take `?project=<space>`. Without the port they give 409 `feature_unavailable`, and an unknown space
  gives 404 `project.not_found`. `usage_count` in space lists is null. **Breaking change**: the `service` of
  `build_router(service)` takes a space name.
- The list fills `ResourceSummary.project` (summary `extra.project`; the shared library = null).

## 0.1.0

- First release (from the scripts/pkgkit template `module`).
- Moved resource CRUD, content, multiple files, `/resource-types` and `/merge-strategies` out of `apps/server`.
  Provided ports `resources.lookup` and `resources.types`, optional port `definitions.usages` (list `usage_count`,
  null without it).
- Reserved name warning issues fill the location `path` (JSON Pointer `/files/<file path>`) and include the file path
  in the message (the save warning banner used to show no path).
