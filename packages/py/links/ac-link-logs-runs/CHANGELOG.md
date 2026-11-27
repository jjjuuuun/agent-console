# Changelog

## Unreleased (0.2.0)

- Titles that mix in values get source template + values (`LogEvent.text_templates["/title"]`). The event map
  template `{/JSON pointer}` placeholders become named placeholders (the last pointer segment, `{/payload/status}` →
  `{status}`; template names stay, `{node}`; clashes use two segments, `{source_node}`), values are the filled strings.
  Fixed titles, value-only titles (`{/payload/text}`), cut titles and titles whose filled text differs (an empty value
  trimmed at the end) have no template. New `event_map.resolve_text_template`. English entries for the default
  map's title templates (`실행 {status}` → `Run {status}`, `사용 한도 {window} {status}`, `세션 시작 {session_id}` and
  others) in `locales/en.json`. A title an installer changes through `event_map` is not translated unless a catalog folder
  has its template as a `text` key. Requires `agent-console-logs>=0.2,<0.3` and `agent-console-contracts>=0.16.1,<0.17`.
  Consumer range: `agent-console-link-logs-runs>=0.2,<0.3`.
- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-link-logs-runs`, so the web app can show the link module description and
  settings and the `logs.invalid_query` issue in English (data only, no API change). The default description of event
  map value fields is now one fixed text (it no longer repeats the field name, which is the title). Log lines are now
  in English.
- The default mapping table data has `wiki.*` (category `wiki`, document markers `{kind: wiki, path: <wiki>/<path>}`,
  two documents for moves, state and action mappings in the map data, evidence `tool_use_id` and `wiki`). No code
  changes.
- `run_tree_ids` uses the optional reader method `descendants` (one index query for a root run). Without it, or for
  an intermediate run or an empty result, it follows direct children as before. A measurement test with 1,000
  descendants.
- Mapping table list values `{each: <list pointer>, ...item template}` for `tags`, `correlation` values and the new
  key `documents` (one document template or a list, in the `LogDocumentRef` shape). Inside an item template, `{./key}`,
  `{.}` and `pointer: ./key` are relative to the element; empty items are dropped and identical items appear once. Pure
  functions `resolve_strings` and `resolve_documents`, constants `EACH_KEY` and `DOCUMENT_FIELDS`. The default mapping
  table moves the resources attached to `agent.context_prepared` into documents (kind `rule` becomes the document kind
  `rules`, and rules are the first document). Existing value formats keep their meaning.
- Registered the log scope kinds `run` and `run-tree` through the port `logs.scope_kinds` (`RunScopeKind`,
  `run_scope_kinds`, `run_sessions`, `run_tree_ids`). The consumer protocol `RunReader.list` has `parent_run_id`, and
  `testing.run_record(parent_run_id=)`. `/runs/{id}/logs` is unchanged (the session calculation moved to
  `run_sessions`).
- Mapping table rule field `cwd_from` (a pointer): the run folder announced by a run becomes the `cwd` of later events
  of the same run (cursor `state.cwd`). Default mapping table `run.started: cwd_from: /payload/cwd`.
- The mapping table data gained rules for `run.child_started` and `run.child_finished` (child run state, `child_run`
  correlation), `edge.skipped`, `loop.iteration` and `loop.exhausted`, and `node.started` (for a call NodeRun, a
  handoff from the delegator to the target, via `delegate`). Child runs are also read as run units of the source
  `platform-runs` (tests).

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- The runtime log source `platform-runs` (classifier `platform-run-event`, mapping table data `run_event_map.yaml`
  plus the setting `event_map`), collection scheduling on `runs.event` subscriptions (debounced),
  `GET /runs/{id}/logs` (fills `total`), and the web role `logs:runs`.
