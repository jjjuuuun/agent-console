# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-exports`, so the web app can show the Claude Code exporter and the `export.*`
  issues in English (data only, no API change). Internal log messages are now in English.
- `ExportCatalog.content(kind, id)`: a way to read single-file content (kinds whose content field points to one file).
  `files` now holds only multi-file content. Apps that build their own catalog must add this method (missing content
  is None). `MemoryCatalog.add(content=)` and `contents`. `claude-dir` reads resource content from `content` when it
  is not found in `files`.
- `claude-dir` follows the teams (children of nested teams) among the definitions it writes and exports their members
  too (the main node is only the selected team, and cycles are visited once).

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
