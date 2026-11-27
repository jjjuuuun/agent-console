# Changelog

## 0.1.1 (unreleased)

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-link-logs-architecture`, so the web app can show the link module description
  and settings and the `architecture.invalid_query` issue in English (data only, no API change).
- `MemoMatcher.match_row` (looks only at the decision cache by `seq` and `uid`), `ScopeCache.lookup_seq` and
  `ScopeEvents.match_seq`. Queries on the `arch` table within the range the architecture map was drawn for do not read
  bodies (about four times faster for a first page whose matching rows are only at the end). Scale tests have a strict
  0.3 second limit.
- Provides the port `architecture.profile_checks` (`UnlistedPathCheck`): when a profile condition looks at a path that
  is not in the list body, a warning `architecture.condition_path_unlisted` is reported. The prefixes are the server
  administrator option `unlisted_paths` (default `DEFAULT_UNLISTED_PATHS` = `/detail` and `/raw`).

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- `GET /logs/architecture` and `GET /logs/events/{uid}/architecture`, the extension log filters `arch`,
  `arch_group` and `arch_sources`, a scope cache (incremental reads, reuse of decisions, result cache), source kind
  mapping options, the web role `logs:architecture`, and standalone run and test tools.
