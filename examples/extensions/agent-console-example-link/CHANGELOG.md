# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `agent-console-example-link`, so the web app can show the
  `example_notes.access_invalid` issue in English (data only, no API change). Internal log messages are now in English.
- Raised the development dependency range to `agent-console-server>=1.0,<2` (server display version 1.0.0). No code
  changes.

## 0.1.0

- First release: an example link module `link-example-notes-runs`. Through the run scope (`runs.scopes`) it provides a
  note reading tool provider for each run, the resource type `example-notes` (field `example_notes`), the event
  `example_notes.read` (no content), and the test double `testing.static_notes_module`.
