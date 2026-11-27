# Changelog

## 0.1.1 (unreleased)

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-architecture`, so the web app can show the default architecture map profile (cells, edges and notes) in English
  (data only, no API change).
- The Instructions cell condition of the default profile now uses `any_item` on `/documents` (skills, specs and
  others after a leading rules document are counted, fixing an undercount). The group value is still the kind of the
  first document.
- `ProfileMatcher.row_fields` and `match_row(row)` (None by default). When there is a source restriction or the
  matcher can answer from column values, `selector_predicate` gets a row-level prefilter (`row_fields` and
  `check_row`, the same shape as ac-logs `RowPredicate`). Targets that are always false (edges that are not observed,
  unassigned turned off) are false at the row level. The decisions are the same.
- `unlisted_path_issues(profile, unlisted_paths)`, `profile_issues(..., unlisted_paths=())` and
  `check_profile_data(..., unlisted_paths=())`: when a condition path (cell or edge `when`, `error_when`) equals a
  given prefix or is below it, a warning `architecture.condition_path_unlisted` is reported (`details.prefix`,
  `condition_path`). The package has no prefix names; the caller provides them. Without them, behavior is unchanged.
- Restored `rules` to the collection scope of the default profile `platform-runs` (rules resources of the platform
  context configuration become a first document `kind: rules` through the mapping table). Added `documents` to the
  context configuration event of the sample `run_with_session_log`; the golden Rules cell changes from `partial` with
  0 occurrences to `observed` with 1 (group `house-rules`).
- `project_architecture(..., matches=)` (project from precomputed decisions, for result caching and incremental reads
  in link modules) and `selector_predicate(..., matcher=)` (inject a matcher that remembers decisions). Without them,
  behavior is unchanged.
- Default profile data `agent-architecture` (16 cells, 21 edges, 3 areas, collection scope and source priority) and
  `testing.load_sample`, `SAMPLES` and `Sample` (two collected samples: a Claude Code session, and platform records
  plus a session log).

## 0.1.0

- First release: profile documents and merging (`merge_profiles`, origin, overrides, null removal), checks
  (`profile_issues`, `check_profile_data`), projection (`project_architecture`: five metrics, three states, collection
  scope, grouping, nested architecture maps, unassigned, source priority, `max_seq`), matching (`ProfileMatcher`,
  `event_membership`, `selector_predicate`), the profile plugin loader, and `testing` tools. The default profile data
  was only a placeholder at first.
