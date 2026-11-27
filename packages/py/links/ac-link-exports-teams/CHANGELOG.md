# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-exports-teams`, so the web app can show the link module description and settings in English (data only,
  no API change). Log lines are now in English.
- Optional port `settings.scope_layers` (multiple providers). `for_lookup(lookup, *, scope=None)`: when `scope` (for
  example a project id) is given, the common attachments (`resources[]`) of that scope layer are added to the
  dependencies too. Constructor arguments `scopes` (scope id to layer) and `scope_layers`. Public `SCOPE_LAYERS` and
  `ScopeLayersSource`.
- `TeamExportDependencies.for_lookup(lookup)`: the same calculation with the same descriptors and common settings,
  reading from another definition store (a project space). `mod-exports` uses it when exporting from a project space.

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- Moved the `exports.dependencies` provider (`TeamExportDependencies`) out of `apps/server`.
