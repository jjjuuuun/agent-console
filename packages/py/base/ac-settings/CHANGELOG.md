# Changelog

## Unreleased

- English for the `merge` and `intersect` merge strategy descriptions (data only).
- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs` `ac-settings`,
  so the web app can show the merge strategy descriptions in English (data only, no API change).

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
