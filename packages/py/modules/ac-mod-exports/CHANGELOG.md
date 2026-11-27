# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-mod-exports`, so the web app can show the module description and export folder
  settings in English (data only, no API change).
- `ScopedExportDependencies.for_lookup(lookup, *, scope=None)`: when the source is a project space, the project id is
  passed as `scope` (the provider also adds the common attachments of that project's settings layer to the
  dependencies). This is part of the same unreleased change as the item below, so providers that only have
  `for_lookup(lookup)` add the `scope` keyword.
- Definitions that are used together are included when exporting from a project space too. When the
  `exports.dependencies` value has `for_lookup(lookup)` (new optional protocol `ScopedExportDependencies`), the
  calculation built on that space's store is used (no fallback to the shared library). Without it, only the selected
  items, as before.
- `LookupExportCatalog.content`: the content of single-file content kinds (kinds where `list_files` raises
  `ValueError`) is read with `read_content`. Multi-file content kinds give None (their content is in `files`). The
  consumer protocol `DefinitionLookup` gained `read_content` (`DefinitionStore` satisfies it).
- Optional ports `projects.folders` and `definitions.spaces`. With the ports, the folder write roots are the registered
  project folders (root id = registration id; the server administrator `roots` are not used), and the source is the
  space of the query `?project=` (default) or `source=library` (shared library); without `project`, the shared
  library. An unregistered id gives 404 `project.not_found`, and `source=project` without `project` gives 422
  `project.required`. `exports.dependencies` (based on the library) is not used for project space sources. Without the
  ports, the current settings apply as is. `ProjectExports`, `ExportProjectError` and `ExportSource`.
- Removed read compatibility for the old top-level `exports`. The `home` default is no longer taken from the old
  `imports.home` (it is its own option; when omitted, HOME or USERPROFILE).

## 0.1.0

- First release (from the scripts/pkgkit template `module`).
- Moved `/exporters` and `/exports/*` of `apps/server` and the export service assembly (catalog =
  `definitions.lookup` plus `exports.dependencies`). Settings `modules.options.mod-exports` (formerly `exports.*`,
  with `home` and `expose_paths` added).
