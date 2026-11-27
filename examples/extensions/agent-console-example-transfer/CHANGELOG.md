# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `agent-console-example-transfer`, so the web app can show the `example_transfer.*`
  warnings in English (data only, no API change).
- Raised the development dependency range to `agent-console-server>=1.0,<2` (server display version 1.0.0). No code
  changes.
- Integrated server test: exporting a single team also includes the common attachments (resources) from the project
  settings layer, and importing it into a project that uses the same attachments runs without a missing resource
  warning.
- The integrated server test selects a single agent: when exporting from a project space, the resources it uses are
  included from that space.
- The content of a single file (catalog `content`) is stored in the item field `content` and passed as
  `ImportItem.content` on import (the field name is the option data `fields.content`). Added `register(registries)` for
  use without installation and an integrated server round-trip test (`tests/test_server.py`).

## 0.1.0

- First release: an example export format that writes definitions to a single JSON file, and an import source
  `example-json` that reads the same file. Format names and field names are option data.
