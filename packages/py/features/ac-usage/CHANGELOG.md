# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-usage`, so the web app can show the usage sources, window names, setup help and
  usage source errors in English (data only, no API change). The comments in the status line setup snippets are now
  in English (they are pasted into your own script). Internal log messages are now in English.
- Sources not listed in the settings are turned on when they are `auto_enable` and not `test_only` (`auto_enabled`;
  previously all were turned on, and external sources stay on by default with `auto_enable=True`). Default source
  data `data/sources.json` (auto enable, window names, setup help `setup_help` and `setup_snippets`; the README
  snippets are checked against the same data by doctest). `UsageService(setup_values=)`, the optional source methods
  `setup_values(ctx)` and `received_at(ctx)`, `fill_setup_snippets` and `fill_setup_text` (quoting per shell and
  language), `UsageSourceInfo.last_received_at`. `statusline-file` also reads a raw statusLine input file
  (`load_statusline_windows`), `default_window_labels`.
- `counts_toward_usage(run)` (only root runs are counted), and `load_usage_records` skips child runs.
- Follow-up: public API for source settings validation `source_config_issues`, `config_error` and
  `UsageService.config_issues`, with the codes `SOURCE_CONFIG_INVALID` and `SOURCE_SCHEMA_INVALID`. `sources()` shows
  current settings errors even before collecting, and when a source schema itself is invalid only that source fails
  (previously the whole collection raised).

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
