# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-resources`, so the web app can show the `prepend` merge strategy and the
  `resource.*` issues in English (data only, no API change).
- Moved the safe substitution implementation to the base package `ac-text-template`. `render_template`, `fill_value`
  and `DEFAULT_MAX_RENDER_CHARS` are re-exported under the same names (public API and behavior unchanged).

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
