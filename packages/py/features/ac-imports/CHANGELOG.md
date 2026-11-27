# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-imports`, so the web app can show the `import.*` warnings in English (data
  only, no API change). Internal log messages are now in English.
- Finding a free id for rename now uses `numbered_id` from `agent-console-numbered-id` (same 128-character truncation
  and attempt limit). New dependency `agent-console-numbered-id`.
- Cleanup: removed the unused direct dependency `ruamel-yaml` (YAML is read by `agent-console-claude-format`).
- The request field `ImportRequest.project` (contract 0.8.0) is stamped into the scope field (`SCOPE_FIELD`) of the
  written definitions. `ImportService.apply(request, *, stamp=None)`, `request_stamp`. Omitted means the shared
  library (same as before).

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
