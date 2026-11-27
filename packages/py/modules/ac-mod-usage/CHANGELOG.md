# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-mod-usage`, so the web app can show the module description and settings and the
  `usage.source_conflict` issue in English (data only, no API change). Log lines are now in English.
- When `resolve_command` cannot find the command on `PATH`, it looks in the folder of the Python that started the
  server (`extra_dirs`), and values given as paths are turned into absolute paths (so pasted snippets work as is).
- Fills `{agent_console_cmd}` in the setup snippets (option `agent_console_command`, `resolve_command`). Automatic
  enabling of sources not listed in the settings uses `agent_console_usage.auto_enabled`.
- Provides `definitions.checks` (`UsageSettingsCheck`: before common settings are saved, source settings are
  validated against the source `config_schema`, and errors give 422), and adds stored settings errors
  `usage.source_config_invalid` to `server.warnings`.
- Removed read compatibility for the old top-level `usage` (a `settings.removed_key` error points to the new
  location).

## 0.1.0

- Moved the observation store into the module (`storage/`, lineage `usage`). Removed the optional port
  `usage.observations` (the host database handle `BaseServices.database` is used). Standalone runs use SQLite in the
  state folder. Added the dependencies `agent-console-store` and `sqlalchemy`.
- First release (from the scripts/pkgkit template `module`).
- Moved `/usage` and `/usage/sources` of `apps/server`, the usage service assembly and observation cleanup.
  `GET /usage?parts=`: requesting only `windows` does not read the run history. Settings
  `modules.options.mod-usage` (formerly `usage.*`).
