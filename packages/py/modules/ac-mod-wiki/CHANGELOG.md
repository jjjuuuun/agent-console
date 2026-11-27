# Changelog

## Unreleased (0.2.0)

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs` `ac-mod-wiki`,
  so the web app can show the module description and settings in English (data only, no API change). Log lines are
  now in English.
- The kind contributions carry `open_role` (wiki `wiki`, wiki rules `wiki:rules`, `WIKI_OPEN_ROLE` and
  `RULES_OPEN_ROLE`), so the copy dialog kind list (`CopyKindInfo.open_role`, contracts 0.16.0) can offer "Open" for
  these rows.
- Added the freshness window, server administrator option `freshness_seconds` (default `2.0`, `0` = check on every
  request as in 1.0.0). Inside the window the service reuses the last fingerprint check per space and wiki (wiki
  definition, rule versions, user settings, write checks, secret rule signature; the space values are still compared on
  every request), and the repository reuses its page listing (`agent-console-wiki`
  `WikiRepository(freshness_seconds=)`). Concurrent opens of the same wiki check once. Changes made through this server
  show at once: page writes (`notify` also drops the listing), wiki definition create, save and delete, wiki rule
  create, save and delete, rule content file writes and deletes, and rule version restores
  (`WikiService.rules_changed`), and the optional topic subscription `definitions.saved`
  (`WikiService.on_definition_saved`; the wiki or rules kind = that space, other kinds = all). `POST …/scan` and the
  periodic scan ignore the window. Files edited outside the app can show up to the window late. Cards
  (`GET /wiki/wikis`) and `GET /wiki/wikis/{id}` read the wiki definition once per request instead of twice. New:
  `WikiService.repository_of(..., fresh=)` and `ports.DEFINITIONS_SAVED`. Consumer range:
  `agent-console-mod-wiki>=0.2,<0.3`; requires `agent-console-wiki>=0.2,<0.3`.
- Contract 0.15.0 (wiki 1.3.0): `GET …/graph?depth=all` (contract `WIKI_GRAPH_DEPTH_ALL`) means no depth limit;
  omitted is still 1, and other values must be integers of 0 or more (otherwise 422). `GET /wiki/info` fills
  `wiki_kind` (the name of the wiki definition kind) and `reserved_page_names` (`PAGE_ROUTE_WORDS`, final path segments
  that cannot be read with `GET`). `PAGE_ROUTE_WORDS` moved to `service` (the public name and the import from `routes`
  are unchanged).
- The index factory options receive the masking function `redact` of the current suspected secret rules
  (`secrets.rules`, including user rules) and its signature `redact_signature` (`service.secret_rules_signature`).
  Previously index implementations masked only with the default rules. When the rules change, the store and index are
  rebuilt. The index cache key holds the signature instead of the function.
- Server administrator option `search.index_options` (search method name to the options that method accepts, for
  example `token_pattern`). The options of the chosen method are passed to the index factory (previously only
  `tokenizer`, `case_insensitive` and `max_results` were passed). The app values `case_insensitive` and
  `max_results` are not overridden. `WikiSearchOptions.factory_options(backend)`.
- Server administrator options `query_hash` (`hmac` by default, `sha256` or `off`) and `query_hash_salt_env` (the name
  of the salt environment variable) for `query_sha256` in agent wiki search events. The default changed from unsalted
  sha256 to HMAC with a random salt each time the server starts. `WikiService(query_hash=)`, `WikiService.query_hash`
  and `search_query_hasher(cfg, environ)`.
- `unique_id` is a re-export of `agent_console_store.unique_id` (the copy is removed, same rules).

## 0.1.0

- First release (from the scripts/pkgkit template `module`).
- Wiki server module: REST `/wiki/*` (wikis, pages, preview, move, history, revert, link insertion, template rendering,
  search, graph, checks, changes, syntax, scan, zip, wiki rules), WS `wiki.changed`, definition kind contributions
  (wikis and wiki rules), the user settings section `wiki`, the port `wiki.service`, the optional ports `wiki.spaces`,
  `records.spaces`, `wiki.write_checks` and `wiki.integrations`, the lineage `wiki` (app and project), host plugin
  loaders for search indexes and write checks, and standalone runs.
- Contract 0.14.1 follow-up: `GET /wiki/info` fills `writable` (the space `config_writable`; true for the standalone
  space).
- Contract 0.14.2 follow-up: wiki rule version routes `GET /wiki/rules/{id}/versions[/{hash}]`,
  `…/versions/{hash}/files[/{path}]` and `POST …/versions/{hash}/restore` (the same shape as `/sdd/templates`, with
  content file secret checks and 409 for read-only spaces), and `GET /wiki/info` fills `rules_kind`.
- Wiki folders are opened with `LocalWikiPages(within=)` (project = the space `folder`, standalone = the standalone
  root folder, `WikiService(standalone_boundary=)`). The base folder is not created. Even if a wiki folder becomes a
  link pointing outside after the space is opened, nothing outside is read or written.
