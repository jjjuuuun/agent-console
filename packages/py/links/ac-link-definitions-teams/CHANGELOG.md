# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-definitions-teams`, so the web app can show the link module description and settings in English (data
  only, no API change).
- Provided port `graphs.session_summary` (`TeamViews.session_summary(graph)` calls
  `ac-teams.session_summary(plan, catalog.strategies)`; a graph that cannot be resolved gives None). The
  `session_summary` of `GET /graphs` rows is this value. Protocol `SessionSummaries`.
- With the presets feature removed, the development dependency `agent-console-mod-presets` and its consumer protocol
  check were dropped. The `definitions.dependencies` port is still provided (no default module consumes it).
- The three effective settings routes take an optional query `project`, and the optional port
  `settings.scope_layers` (`ScopeLayersSource`) inserts scope layers right below Common and adds provider warnings to
  `warnings`.
- Provided port `definitions.references` (multiple providers, `multi=True`): the reference extraction function
  `TeamDocumentDependencies.references(kind, doc) -> [(kind, id)]` (no duplicates; invalid documents and unknown kinds
  give an empty list).
- Provided port `definitions.dependencies` (`TeamDocumentDependencies`, from a document to the definitions it uses).
  Dev dependency `agent-console-mod-presets` (consumer protocol contract tests).

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- Moved the usage, effective settings, run plan and bundle preview routes of `apps/server` (`_rest_graph_views` and
  others). Provided ports `graphs.entry_labels` and `definitions.usages`.
- Tests: assertions on common settings defaults (removed tautologies), and masking of bundle previews (saved and
  draft) when a fake `secrets.redact` is injected.
- Declared the web role `definitions:teams` (`WEB_ROLES`, team draft preview and agent usage panel) in the
  descriptor.
