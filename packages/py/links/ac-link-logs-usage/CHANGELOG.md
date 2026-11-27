# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-logs-usage`, so the web app can show the link module description and settings in English (data only, no
  API change).
- Default data window names changed from `5시간(로그 추정)` and `7일(로그 추정)` to `5시간` and `7일` (the trust
  level badge conveys reliability; `short_title` is unchanged). The window states `active` and `idle` are values this
  source produces, not contract vocabulary (`UsageWindowSnapshot.status` is an open string).
- Log sources whose log folder exists on this machine are turned on by default (port `logs.source_defaults`, rule data
  `data/auto_log_sources.json`, `autoenable`), `local-logs` gained `auto_enable` and window names (default data
  `title` and `short_title`, `window_infos`), and the first query waits for collection (optional port `logs.ingest`,
  `first_scan_wait_seconds`). Options `auto_enable_log_sources`, `auto_log_sources_file` and
  `first_scan_wait_seconds`.

## 0.1.0

- First release (from the scripts/pkgkit template `link`): the usage source `local-logs` (`LocalLogsUsageSource`,
  trust level `estimated`), the pure calculation `estimate_windows`, the default data
  `data/local_logs_defaults.json`, cache invalidation on `logs.ingested`, and the server administrator options
  `source_id` and `defaults_file`.
