# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `agent-console-example-module`, so the web app can show the `example_notes.*`
  issues in English (data only, no API change).
- The `--example-notes-max` help is in English (it appears in `agent-console serve --help`).
- Raised the development dependency range to `agent-console-server>=1.0,<2` (server display version 1.0.0). No code
  changes.

## 0.1.0

- First release: an example server module `mod-example-notes`. It has the REST path `/example-notes`, server
  administrator options (`x-ui` and descriptions) with the command-line option `--example-notes-max`, the user settings
  section `example_notes`, a definition kind contribution (note templates), the migration lineage `example_notes` (app
  and project record databases), the port `example_notes.reader`, and standalone use with
  `python -m agent_console_example_module`.
