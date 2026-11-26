# agent-console-mod-wiki

Agent Console wiki server module (`mod-wiki`). It attaches `ac-wiki` (syntax, parsing, link resolution, index, repository,
rules, checks, history, search, zip) to the server. It does not know about runs or projects; link modules attach both through ports.

- REST `/wiki/*`: screen information `GET /wiki/info` (page folder, capabilities, limits, definition kind names, and `reserved_page_names`, the last path segments that cannot be read with `GET`; the graph has no depth limit with `?depth=all`), the wiki list, create, view, save, and delete
  (`/wiki/wikis[/{wiki}]`; the list card values (pages, broken links, orphans, check counts, recent changes) in one request), pages
  (`…/pages[/{path}]`, `ETag` = body sha256, new pages with `If-None-Match: *`), the pre-save trial `…/preview`, moving
  `…/move` (only the link strings are changed), history `…/history[/{version}]` and `…/restore`, link insertion `…/link-text`, page templates
  `…/templates[/{id}/render]`, search, graph, checks, changes (`?op=`, `?author_run=`; the whole space with `GET /wiki/changes`),
  the effective syntax, rescanning external changes `…/scan`, and zip `…/export` (`Content-Disposition`) and `…/import`. Wiki rules:
  `/wiki/rules[/{id}[/files[/{path}]]]`, `POST /wiki/rules/check`, and versions `/wiki/rules/{id}/versions[/{hash}[/files[/{path}]]]` and
  `POST …/versions/{hash}/restore` (these work without the definitions module). Every route
  accepts `?project=<space name>`.
- WS topic `wiki.changed` (no content; the screen reads again). The repository does not notify; the module looks at the results and publishes them through the kit's
  `LoopPublisher`. Previews and `dry_run` do not notify.
- Definition kind contributions: wiki rules (library and project, several body files: instructions and page templates) and wikis
  (`library=False`, reference extraction `rules` → wiki rules). Kind names and folder names are administrator options (the defaults are the package
  data `data/defaults.json`).
- User settings section `wiki` (`include_default_syntax`, `syntax`, `secret_scan`, `max_versions_per_page`,
  `search_backend`, `write_checks`). Unknown keys are kept, and only the broken parts are left out and reported in `server.warnings` as
  `wiki.settings_invalid`.
- Spaces: `wiki.spaces` (optional, provided by `link-projects-wiki`). Requests without a space name use the standalone root
  (`standalone_root`, by default `wiki/` inside the workspace). When a name is given but the link is missing, 409
  `wiki.spaces_unavailable`. The wiki rules of the standalone space are read from the app library (when `definitions.store` has the rule kind),
  and otherwise from the standalone root.
- History: lineage `wiki` (the revisions are owned by `ac-wiki.sqlite`; scopes `app` and `project`). Standalone space = the host database
  (process memory when it is an in-memory database or there is no database); project space = that folder's record database from `records.spaces` (without it,
  no history; it does not write to the host database instead).
- Search: user `search_backend` → administrator `search.backend` (default `sqlite-fts`) → `search.fallback`
  (default `scan`). The index files go into the `index_dir` the space provides for a project space, and into the host state folder
  `wiki-index/` for the standalone space. With the fallback method, `GET /wiki/info` shows `wiki.search_degraded`. Index factory options = the administrator
  `search.tokenizer` + `search.index_options.<method>` of the chosen method (the search implementation defines the keys, for example `token_pattern`), overlaid with the
  app values `case_insensitive` (wiki syntax), `max_results` (`max_search_results`), `redact` (masking with the current suspected-secret rules of the port `secrets.rules`,
  including user rules, or the default rules without it), and `redact_signature` (the signature of those rules). When the rules change, the
  repository and the index are rebuilt.
- Write checks: the port `wiki.write_checks` (always on; turn one off with the setting `enabled: false`) + the entry point
  `agent_console.wiki_write_checks` (turned on with the setting `wiki.write_checks[{id, enabled, options}]`; the value is a check object
  or a factory that receives the options).
- The capabilities `WikiInfo.capabilities` are computed from which ports exist (`runs` = a link that provided `runs` in `wiki.integrations`).
- Search text hash: administrator options `query_hash` (`hmac` by default, `sha256`, `off`) and `query_hash_salt_env` (the name of the environment variable to read the salt from;
  the value is never kept in the settings. When missing or empty, a random salt on every server start). There is one hasher per service
  (`WikiService.query_hash`, `search_query_hasher(cfg, environ)`), and the runs link uses it for `query_sha256` in agent wiki search events.
  Whether to share the variable with the memory module is decided in each module's settings.

## Freshness window

Every wiki request used to recompute the repository fingerprint (wiki definition, rule versions, user settings, write checks, suspected-secret
rule signature) and list and stat every page file. On slow drives or wikis with thousands of pages that dominated the response time. The module
now remembers, per space and wiki, when it last checked, and inside the window it reuses that check and the page listing it built
(link index, listing issues, history summaries).

| Administrator option (`modules.options.mod-wiki`) | Default | Meaning |
| --- | --- | --- |
| `freshness_seconds` | `2.0` | Seconds after the last check during which the module does not check the page folder, the wiki definition, the rules, or the settings again. `0` checks on every request (the 1.0.0 behavior). |
| `scan_interval_seconds` | `0` | Seconds between background rescans of opened wikis (records external changes as history). `0` = only on read and **Rescan**. |
| `summary_cache_entries` | `256` | Wiki list cards kept so that the checks are not recomputed while the page files stay the same. |

What shows up at once, whatever the window:

- Changes made through this server: page writes, deletes, moves, restores, and zip imports (REST and agent tools); wiki definition create, save, and
  delete; wiki rule create, save, and delete, rule body file writes and deletes, and rule version restores.
- Definition saves announced on the module topic `definitions.saved` (optional subscription): a wiki or wiki rules kind drops the checks of that space
  (no space = the standalone space and the library), and any other kind (for example the common settings that hold the wiki and secret settings)
  drops all checks.
- `POST …/scan` (**Rescan** on the screen) and the periodic scan ignore the window.
- Opening a page whose own file changed outside the app (a different size or modification time from the listing) rebuilds the listing first.

What can be late by up to `freshness_seconds`: files changed by another editor or process (other pages in the list, links, and backlinks), and
definitions or settings changed outside this process without an event. Press **Rescan** to see them at once. On slow drives (for example a
Windows drive mounted in WSL or a network drive) or wikis with thousands of pages, 10 to 30 seconds keeps the screens fast; set `0` if you always
want edits from other editors to show immediately. As a reference, with 2,000 pages in a project on a Windows drive mounted in WSL, a repeated page
list request took about 8 s on every request before and about 0.1 s inside the window (on a Linux file system: about 0.5 s and 0.07 s).

```yaml
modules:
  options:
    mod-wiki:
      freshness_seconds: 15
```

What is fixed in code: the roles of front matter, the default checks, and the meaning of link target resolution (`ac-wiki`); the paths that enforce write rules (tools, screen,
REST; files edited directly show up on the next read or `scan` as `external` history entries and as rule violations in the checks); and the original =
the files. A page whose last path component is `history` (or `history/<number>`) cannot be read with `GET`
(it overlaps the history route, `PAGE_ROUTE_WORDS`).

## Dependencies: what, why, alternatives

- In-house: `agent-console-wiki[sqlite]` (wiki core, SQLite history, FTS5 index), `agent-console-store` (definition
  store, versions, record database shape), `agent-console-conditions` (write and check rule operators), `agent-console-registry`
  (plugins), `agent-console-secret-rules` (secret checks for bodies and definitions), `agent-console-safe-zip` (zip limits), and
  `agent-console-modkit[host]` (module, host). No new external dependencies (FastAPI and pydantic are the same as other modules).

## Install

```bash
pip install agent-console-mod-wiki
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-wiki
```

## Minimal usage (one module + the standalone root)

```python
>>> import tempfile
>>> from pathlib import Path
>>> from fastapi.testclient import TestClient
>>> from agent_console_mod_wiki import module
>>> from agent_console_modkit import BaseServices, Paths, assemble
>>> from agent_console_modkit.host import SecurityPolicy, create_host_app

>>> tmp = Path(tempfile.mkdtemp())
>>> base = BaseServices(paths=Paths(base_dir=tmp, workspace=tmp / "ws", state=tmp / "state"))
>>> assembly = assemble([module], base=base)
>>> policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
>>> client = TestClient(create_host_app(assembly, policy=policy))
>>> client.headers["X-Console-Token"] = "t" * 32
>>> with client:
...     print(client.get("/api/v1/wiki/wikis").json())
...     wiki = client.post("/api/v1/wiki/wikis", json={"name": "Notes"}).json()["wiki"]["id"]
...     page = client.put(
...         f"/api/v1/wiki/wikis/{wiki}/pages/index",
...         json={"content": "# Home\n\n[[other]]\n"},
...         headers={"If-None-Match": "*"},
...     ).json()
...     print(wiki, [(link["target"], link["status"]) for link in page["links"]])
[]
notes [('other', 'broken')]

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

Standalone run: `python -m agent_console_mod_wiki [--with ID] [--config PATH] [--port 0] [--check]`. User
settings go in the `wiki` section of the workspace `settings.yaml`. Definition versions and page history are in `<state>/console.sqlite3`.

## Ports

| Port | Direction | Shape |
| --- | --- | --- |
| `wiki.service` | Provides | `WikiServicePort`: `settings()`, `wiki_ids(space)`, `repository(space, wiki)`, `tool_targets(space)`, `notify(space, wiki, paths)` (+ `scope(space)` of the implementation `WikiService`) |
| `definitions.kind_contributions` | Provides (several) | Two `KindContribution(DefinitionKind, references, title, delete)` (`delete` does the same as the module's own delete route; the common delete for all kinds calls it) |
| `server.warnings` | Provides (several) | Settings format problems, write checks that are not installed |
| `wiki.spaces` | Optional | `WikiSpaces.open(space) -> WikiSpace{store, config_writable, pages_root[, pages_dir, config_dir, index_dir]}` |
| `records.spaces` | Optional | `agent_console_store.RecordsSpaces` (space name = `records_space_prefix` + project id) |
| `wiki.write_checks` | Optional (several) | `agent_console_wiki.WikiWriteCheck{id, check(subject, text)}` |
| `wiki.integrations` | Optional (several) | `WikiIntegration{id, capabilities}` (`runs` → `capabilities.runs`) |
| `workspace.settings`, `secrets.rules`, `definitions.store` | Optional | Settings, secret rules, library |
| Topic `definitions.saved` | Subscribes (optional) | `{kind, id, space?}` → drops freshness window checks (see "Freshness window") |

## Viewing the wiki in logs and the architecture map (example data)

The run events `wiki.<op>` left by the runs link (`link-wiki-runs`) are mapped by the platform run log map
(`wiki.*` in `run_event_map.yaml` of `ac-link-logs-runs`) to the category `wiki`, the document marker
`{kind: wiki, path: <wiki id>/<page path>, action: read|read_links|written|removed|moved_from|moved_to}`,
and the evidence `tool_use_id` and `wiki` (wiki id). Searches and lists have no page, so they have no document marker. The file change words
(`created`, `modified`, `deleted`) are not used (so that they do not mix into the Workspace cell of the default architecture map).

The default architecture map profile has no Wiki cell. To see one, duplicate the default profile (`profile` of `GET /architecture/profiles/agent-architecture`)
and add a cell, an edge, and coverage (`...` is the rest of the duplicate). This data is not kept in the repository.

```yaml
architecture:
  profiles:
    with-wiki:
      title: Agent architecture + wiki
      # ... duplicate canvas, zones, error_when, source_priority, cells, edges, and coverage of the default profile as they are ...
      cells:
        # ... default cells ...
        wiki:
          label: Wiki
          description: Wiki reads and writes
          x: 810
          y: 730
          zone: runtime
          tone: gold
          metrics: [count, errors]
          group_by: /correlation/wiki          # group by wiki
          when: {all: [{path: /category, op: eq, value: wiki}]}
      edges:
        # ... default edges ...
        - id: wiki_access
          from: dispatch
          to: wiki
          label: Wiki access
          kind: observed
          style: request
          points: [[1054, 610], [1030, 610], [1030, 730], [906, 730]]
          label_at: [968, 730]
          metrics: [count, errors]
          when: {all: [{path: /category, op: eq, value: wiki}]}
      coverage:
        platform-runs:
          cells: [sdk, api, rules, context, llm, dispatch, hook, tools, mcp, result, delegation,
                  subagents, response, wiki]
```

- Category names are data too. When you rewrite the whole `wiki.*` rule in `logs.sources[id=platform-runs].config.event_map`
  and change it to `category: knowledge`, change the `value` of the condition above to `knowledge` as well.
- To turn the rule off, write `"wiki.*": {}` in the same place. Wiki events remain in the category `other` (title = type name), and
  the Wiki cell shows 0.
- Cell count = the number of wiki events of that run = the number of rows in the event table when you click the cell (the repository integration test
  `test_integration_wiki_cell_7r15.py`).

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```
