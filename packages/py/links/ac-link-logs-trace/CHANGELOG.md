# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-logs-trace`, so the web app can show the link module description and settings in English (data only, no
  API change).

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- `build_log_trace` (session log to `Trace`), `LogTraceViews`, `GET /logs/sessions/{session}/trace`, the web role
  `logs:trace`, and the settings `link_keys` and `max_events`.
