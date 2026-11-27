# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-link-wiki-runs`, so the web app can show the link module description and
  settings and the `wiki.access_invalid` issue in English (data only, no API change). Log lines are now in English.
- The wiki tool set receives a search query hasher: the optional service attribute `query_hash` (`QueryHashSource`,
  `service_query_hash`) comes first, otherwise `WikiRunScope(query_hash=)` (default: one hasher with a random salt per
  scope). `WikiToolProvider(query_hash=)`.
- `merge_access` merges with `agent_console_nodes_core.merge_access_layers` and then only validates (the same rules as
  the memory link module, same behavior).

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- Resource type `wiki` (package data `data/wiki_resource_type.yaml`, settings schema = contract `WikiAccessConfig`),
  entry point `agent_console.resource_types`.
- Tool provider `WikiToolProvider` (layer merging `merge_access`, only the wikis of that run's space, instructions =
  `WikiToolkit.instructions()`, author `author_for` (plus the agent definition name `label`), a RunEvent `wiki.*` per
  tool call, `notify` after successful writes, moves and deletes, and a warning `wiki.wiki_unavailable` for wikis not
  in the space), the run scope `WikiRunScope` (`runs.scopes`, a provider and write limit per root run), the pre-save
  check `WikiResourceCheck` (`definitions.checks`, warns about unknown wiki ids with `wiki.unknown_wiki`), and the
  `wiki.integrations` declaration `{runs}`. `wiki.service` is required and `projects.lookup` is optional.
- Setting `max_writes_per_run` (default 100). `testing.wiki_service_module`, `StaticWikiService` and
  `memory_repository` for standalone runs.
- Node type `wiki-update` (entry point `agent_console.node_types`): writes the previous node's result to a wiki page
  without an LLM (`WikiUpdateNode` and `WikiUpdateConfig`: wiki, path template, `mode` append, section or replace,
  section heading, content template, new page template and history note; templates use `ac-text-template`, variables
  `WIKI_UPDATE_VARIABLES` and `render_values`). The author is `system` (`label` = node id, `system_author`). The node
  service `WIKI_UPDATE_SERVICE` is provided through `runs.services` (`WikiNodeServices`). Without the service, a
  validation warning is shown and the node is skipped at run time (`wiki.update_unavailable`). New internal
  dependency `agent-console-text-template`.
- Contract 0.14.1 follow-up: `WikiUpdateCodes.UNAVAILABLE` uses the contract document constant
  `KnownIssueCodes.WIKI_UPDATE_UNAVAILABLE` (same value). Validation of the `wiki` and `page_template` id settings uses
  the public contract alias `Slug` instead of a copied regular expression (same shape). Because of the contract
  default change, in a workspace whose settings were not changed, plain-text secret writes by this node (author
  system) are rejected (previously: warned, then saved).
