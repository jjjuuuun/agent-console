# agent-console-link-wiki-runs

Agent Console wiki and runs link module (`link-wiki-runs`). It gives agents wiki tools (search, read, list, links, write, move, delete)
and wiki rule instructions. The runs module (`mod-runs`) and the wiki module (`mod-wiki`) do not know each other; this link connects them by
adding an agent tool provider (`TOOL_PROVIDERS`) to every run through the run scope (`runs.scopes`).

| What | Details |
| --- | --- |
| Received ports | Required `wiki.service` (`mod-wiki`: `tool_targets`, `notify`, `wiki_ids`; the optional attribute `query_hash` = the search text hasher, and without it this link uses one hasher with a random salt). Without it this link is off. Optional `projects.lookup` (the pre-save check also looks at the wiki ids of project spaces) |
| Provided ports | `runs.scopes` (a wiki tool provider per run), `definitions.checks` (an unknown wiki id → warning `wiki.unknown_wiki`), `wiki.integrations` (`{runs}` → `capabilities.runs` of the wiki screen) |
| Resource type | `wiki` (entry point `agent_console.resource_types`, package data `data/wiki_resource_type.yaml`, settings schema = contract `WikiAccessConfig`; the wiki field uses the `x-ui` widget `wiki-ref`) |
| Run events | `wiki.read`, `wiki.search`, `wiki.list`, `wiki.links`, `wiki.write`, `wiki.move`, and `wiki.delete` per tool call (payload = contract `WikiEventPayload`: wiki, path, status, reason code, version, byte count, hash, rule id, result count, search text length and hash, tool name, `tool_use_id`, duration. **No content or search text**) |
| Instructions | `ToolProvision.instructions` = the merged wiki rule instructions of every usable wiki (`include_rules_instructions`) + a path hint (`path_hint`; `{pages_dir}` = the page folder relative to the agent's project folder) |
| Administrator option | `modules.options.link-wiki-runs.max_writes_per_run` (default 100; empty = no limit. Writes, moves, and deletes each use one; above it, `rate_limited`) |
| Web role | `wiki:runs` (the wiki chips and links in the run detail) |
| Node type | `wiki-update` (entry point `agent_console.node_types`; updates a page without an LLM, see below). The node services are provided through `runs.services` |

- **Opt-in**: only agents with a `wiki` resource attached get the tools and instructions. Tool names, descriptions, result header lines, and permissions per wiki are
  the resource config (data). Tools for actions that no wiki allows are not offered.
- **Layers**: when the same slot has several attachments (common → team → agent → node), the allowed actions of the closest layer are used for each wiki.
  For the other keys (default wiki, tool names, path hint, and so on), the value set by the closest layer also wins (`merge_access`, the same rule as the memory
  link, `agent_console_nodes_core.merge_access_layers`).
- **Which wiki**: only the wikis of the run's space. When the root run has a `project_id`, that project's space; otherwise the
  standalone space. When a wiki that a resource points to is not in that space, the tools are still given, calls to that wiki return
  `wiki.wiki_unavailable`, and that node gets one warning (`wiki.wiki_unavailable`, details `wikis`).
- **Author**: `WikiAuthor{kind: agent, agent_id, node_id, node_path, run_id, root_run_id, graph_id, label}`.
  `label` is the agent definition `name` at run time and stays in the history as it is (the name is still shown after the definition is deleted). "Pages this run
  changed" on the wiki screen is `GET /wiki/changes?author_run=<run or root run id>`.
- **The write limit per run** is shared by all agents of one root run (including child runs).
- **Notifications**: after a successful write, move, or delete, `wiki.service.notify` (WS `wiki.changed`). A move reports only the old and new paths
  (other pages whose links were updated show up on the next read because the wiki summary cache is cleared).
- **The pre-save check** does not know the space being saved to. It warns only about ids that are in none of the wikis of the standalone space and (when
  `projects.lookup` exists) all project spaces.
- **Turning it off**: when `mod-wiki` or this link is off, runs still finish, and each node with a wiki resource attached gets one "slot the backend could not
  apply" warning (`resource.slot_unsupported`). When this link is off, `capabilities.runs` of the wiki screen is
  false. While this package is installed, the resource type stays registered even with the link off.
- Wiki content can be read by other agents as if it were instructions (it is not a security boundary). The result header line says it is "reference material",
  write permissions are narrowed with the resource, and content with the wiki rules (write rules). Agents that edit files directly are not
  blocked (the next read or periodic check records it as `external`).

## Node type `wiki-update`

Writes the result of the previous node (input port `in`) to one wiki page without calling an agent. For example: implement → (handoff) → update
wiki → (reply) → person.

- **Settings** (`WikiUpdateConfig`; the form is drawn from the schema `x-ui`): `wiki` (widget `wiki-ref`), `path` (path template), `mode`
  (`append` by default, `section`, `replace`), `section` (section heading template; required for `section`, otherwise a validation error), `content` (content template, default
  `{input}` + a line break), `page_template` (the id of the wiki rule page template to use when the page does not exist), `title` (the title for that template), and `message`
  (history note). Templates are `ac-text-template` (only `{name}` is substituted), and the variables are `input` (the previous node's value; JSON when it is not text), `node_id`,
  `run_id`, `graph_id`, `date`, and `time`; when the previous node's value is an object, its top-level keys are variables too.
- **Writing**: `ac-wiki` `compose_write` (the same method as the wiki tool `write`) → `WikiRepository.write`. Write rules, write checks,
  secret checks, history, and the search index are the repository's job. Author = `WikiAuthor{kind: system, label: node id, node_id,
  node_path, run_id, root_run_id, graph_id}`. Wiki space = the `project_id` of this run (the standalone space when there is none).
- **Result**: on success, the output `out` = `{wiki, path, sha256, version, created, changed}` (no content) and the RunEvent
  `wiki.write` (the same `WikiEventPayload` as tool calls), plus `notify` when something changed. Rule rejections, secret rejections, missing paths or sections, and wikis
  not in the space make the node `failed` (`ErrorInfo.code` = `wiki.rule_rejected` and so on; `details` = details without the original values) with the same
  event (status = reason).
- **Off**: without the wiki service (node service `WIKI_UPDATE_SERVICE`), graph validation warns `wiki.update_unavailable`,
  and when run the node is `skipped` (same code) with one `log.warning`, and its outgoing edges are not followed.
- The write limit per run (`max_writes_per_run`) is for agent tools, so this node does not use it (one node run = one write).

```python
>>> import asyncio
>>> from agent_console_contracts import Graph
>>> from agent_console_runtime import Services, as_node_type
>>> from agent_console_runtime.testing import entry, make_harness, with_entries
>>> from agent_console_link_wiki_runs import WikiNodeServices, WikiUpdateNode
>>> from agent_console_link_wiki_runs.testing import StaticWikiService, memory_repository
>>> repo = memory_repository("notes", files={"log.md": "# 기록\n"})
>>> service = StaticWikiService({None: {"notes": repo}})
>>> h = make_harness()
>>> _ = h.registries.node_types.register("wiki-update", as_node_type(WikiUpdateNode))
>>> graph = with_entries(Graph.model_validate({"id": "g", "name": "g", "nodes": [{"id": "keep",
...     "type": "wiki-update", "config": {"wiki": "notes", "path": "log"}}], "edges": []}),
...     entry("keep", tp="in", key="text"))
>>> runtime = h.make(services=Services(WikiNodeServices(lambda: service).services()))
>>> run = asyncio.run(runtime.run(graph, {"text": "첫 결과"}))
>>> run.status, repo.current("log").text
('completed', '# 기록\n첫 결과\n')
>>> repo.history.list("notes", "log").items[0].author.kind
'system'

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Dependencies: what, why, alternatives

- In-house: `agent-console-wiki` (tool set `WikiToolkit`, write limit), `agent-console-nodes-core` (provider
  protocol, service keys), `agent-console-runtime` (`HostTool`), `agent-console-resources` (resource type base),
  `agent-console-store` (definition kind name `resource`), `agent-console-modkit` (module), and
  `agent-console-text-template` (template substitution in the `wiki-update` node; SDD and resource types use the same template rules. The alternative, Jinja2, has
  more features than needed and the burden of a sandbox).
- External: pydantic, ruamel.yaml (descriptor data). No new external dependencies.

## Install

```bash
pip install agent-console-link-wiki-runs
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-wiki-runs
```

## Minimal usage

Without a server or a run engine, build the tools from one provider and call them (the wiki service is injected).

```python
>>> import asyncio
>>> from agent_console_contracts import BackendCapabilities, ResourceBundle
>>> from agent_console_nodes_core import ToolProvisionContext
>>> from agent_console_runtime import CancelToken
>>> from agent_console_wiki import WikiToolTarget
>>> from agent_console_link_wiki_runs import WikiToolProvider
>>> from agent_console_link_wiki_runs.testing import StaticWikiService, memory_repository
>>> repo = memory_repository("notes")
>>> service = StaticWikiService({None: {"notes": WikiToolTarget(repo, pages_dir="wiki/notes")}})
>>> events = []
>>> async def emit(event_type, payload):
...     events.append((event_type, payload["status"], payload["path"]))
>>> config = {"wikis": [{"wiki": "notes", "access": ["read", "write"]}],
...           "path_hint": "페이지는 {pages_dir}/ 아래입니다.",
...           "tools": {"write": {"name": "jot", "description": "페이지를 씁니다"}}}
>>> ctx = ToolProvisionContext(
...     run_id="r1", root_run_id="r1", graph_id="team", node_id="a", node_path=["a"],
...     agent_id="a", call=0, iteration=0,
...     bundle=ResourceBundle(slots={"wiki": [{"config": config}]}),
...     backend_capabilities=BackendCapabilities(host_tools=True), emit=emit, cancel=CancelToken())
>>> provision = WikiToolProvider(lambda: service, slot="wiki").provide(ctx)
>>> [t.name for t in provision.host_tools][1:], list(provision.instructions)
(['jot'], ['페이지는 wiki/notes/ 아래입니다.'])
>>> asyncio.run(provision.host_tools[1].handler({"path": "결정", "content": "v2"})).is_error
False
>>> events, repo.current("결정").text
([('wiki.write', 'ok', '결정')], 'v2')
>>> [(n.wiki_id, n.paths) for n in service.notices]
[('notes', ('결정',))]

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

Standalone run (with a stand-in wiki service module): `python -m agent_console_link_wiki_runs --check`.
With the real modules: `--with mod-wiki --with mod-runs`.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```
