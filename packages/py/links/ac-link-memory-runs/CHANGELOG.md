# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-link-memory-runs`, so the web app can show the link module description and
  settings and the `memory.access_invalid` issue in English (data only, no API change). Log lines are now in English.
- `merge_access` merges with `agent_console_nodes_core.merge_access_layers` and then only validates (the same rules as
  the wiki link module, same behavior).

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- Resource type `memory` (package data `data/memory_resource_type.yaml`, settings schema = contract
  `MemoryAccessConfig`), entry point `agent_console.resource_types`.
- Tool provider `MemoryToolProvider` (layer merging `merge_access`, a RunEvent `memory.*` per tool call), the run
  scope `MemoryRunScope` (`runs.scopes`, a provider and write limit per run), and the pre-save check
  `MemoryResourceCheck` (`definitions.checks`, warns about unknown scope kinds). `memory.service` is required.
- Setting `max_writes_per_run`. `testing.memory_service_module` for standalone runs.
- Project runs (with a `project_id`) use only the memory service's `space(project_id)` store (the space service
  applies the context switch). When `space` is missing or fails, the tools keep the same shape, every call returns
  `memory.scope_unavailable`, and the memory field node shows a warning (`UnavailableMemoryService`,
  `space_service`). `testing.StaticMemoryService(spaces=...)` and `space`.
