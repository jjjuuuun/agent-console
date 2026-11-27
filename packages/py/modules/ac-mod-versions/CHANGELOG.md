# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-mod-versions`, so the web app can show the module description and settings in English (data only, no API
  change). Log lines are now in English.
- `VersionService.diff` now calls the shared `agent_console_store.diff_versions` (same result; the calculation moved
  to `ac-store` so the document template version routes in `ac-mod-sdd` can use it too). `SECRET_MASK` is re-exported
  from `ac-store`. Dropped the direct `agent-console-settings` dependency. Consumer range:
  `agent-console-store>=0.2,<0.3`.
- Pre-save checks for reverts and comparisons in a space (`?project=`) call the optional check method `space_issues`
  (`SpaceDefinitionCheck`), falling back to `issues`. Optional argument `VersionService(space=)`.
- Optional port `definitions.spaces`. Every version route takes `?project=<space>` and uses the version history of that
  space's store (list, single version, comparison, content files, revert). Without the port they give 409
  `feature_unavailable`, and an unknown space gives 404 `project.not_found`. When a `definitions.saved` item has a
  `space`, the retention count is applied to that space (`VersionService(spaces=)`). **Breaking change**: the
  `service` of `build_router(service, …)` takes a space name.
- Removed read compatibility for the old top-level `versions` (a `settings.removed_key` error points to the new
  location).

## 0.1.0

- First release (from the scripts/pkgkit template `module`).
- Moved the version routes of `apps/server` (list, comparison, revert). The collection table is settings data
  (`collections`). `max_per_definition` is wired up: the retention count is applied on every save notification
  `definitions.saved` and at startup. Settings `modules.options.mod-versions` (formerly `versions.*`).
