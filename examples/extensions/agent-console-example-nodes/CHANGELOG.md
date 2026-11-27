# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `agent-console-example-nodes`, so the web app can show the `example.*` codes in
  English (data only, no API change).

## 0.1.0

- Set up as a standalone project: version ranges for internal dependencies, pytest, mypy and ruff settings with a
  `dev` dependency group, LICENSE and CHANGELOG. Removed from the root `pythonpath` and `mypy_path`.
