# How this project is developed

**English** | [한국어](DEVELOPMENT.ko.md)

This project was built with [Claude Code](https://docs.claude.com/en/docs/claude-code). The full rules are in
`CLAUDE.md` at the root. This page is a short summary of the workflow.

## Roles

- **The main session coordinates.** It reads the task list, hands each task to the lead that owns it, takes the
  result, and decides what comes next. It does not write the implementation itself.
- **Lead agents do the work.** They are subagents defined in `.claude/agents/`.

  | Agent | Responsibilities |
  | --- | --- |
  | `pl` | Reads the requirements, writes the design documents, breaks the work into tasks with owners, reviews integration (writes no code) |
  | `web-designer-lead` | Screen layout, flows and design token specs (writes no code) |
  | `publisher-lead` | Web UI implementation |
  | `backend-lead` | Server, run engine, extension points, CLI, log collection |
  | `db-lead` | Data model, schema, migrations |
  | `qa-lead` | Checks acceptance criteria, writes tests, looks for hard-coded lists and reuse problems (does not change implementation code) |

- Subagents cannot call each other, so every hand-off goes through the main session.

## Workflow (spec-driven development)

1. **Design.** At the start of a phase, `pl` writes the design document and the task list for that phase. Nothing is
   implemented until a person approves them.
2. **Task breakdown.** Every task gets an owner (`[owner: ...]`), the requirements it covers (`[req: ...]`) and the tasks
   it waits for (`[depends: ...]`). Only tasks without open dependencies run in parallel.
3. **Implementation.** A lead implements one package at a time and reports the changed files and any contract changes.
4. **QA.** `qa-lead` checks the acceptance criteria and the no-hard-coding and reuse rules. A failed task goes back to
   its owner. After three failures in a row, the work stops and a person is asked.
5. A task that passes is checked off. If the code ended up different from the design, the design document is updated
   too. Only one phase runs at a time.

A task is done when `uv run poe check` and `pnpm check` pass, plus `uv run poe contracts-check` if a contract changed.
At the end of a phase, `pnpm e2e` and `uv run poe portability --wheels` (copy each package out of the repository,
install it and run its checks) must pass as well. Commit messages follow Conventional Commits
([CONTRIBUTING.md](../CONTRIBUTING.md#commit-messages)).

## What is not committed

- Runtime data: the workspace (`.agent-console/`, `.state/`), SQLite databases and `agent-console.yaml`.
- Test data (recorded logs, session logs `*.jsonl`, fixtures, snapshots), screenshots and screen recordings. The only
  exception is the README images under `assets/readme/` (including the per-language folders). The data shown in those
  images is created in an empty workspace and is not committed.
- Internal working documents such as requirements, designs and task lists. They are not in the public repository.
- Secrets. They live in environment variables only, and settings and definitions refer to them as `secret://<name>`.
- These rules are reflected in [.gitignore](../.gitignore).

## Extension points

A new kind of thing is added as a package with a Python entry point, without changing existing code. The server does
not know any names in advance. It only loads what is registered.

| Entry point group | What it adds |
| --- | --- |
| `agent_console.node_types` · `agent_console.edge_types` | Node types, edge types |
| `agent_console.backends` | Execution backends |
| `agent_console.delegation_strategies` · `agent_console.condition_operators` · `agent_console.interaction_kinds` | Delegation strategies, condition operators, interaction kinds |
| `agent_console.resource_types` · `agent_console.secret_providers` | Resource types, secret providers |
| `agent_console.log_sources` · `agent_console.log_classifiers` · `agent_console.collectors` | Log sources, log classifiers, run observation collectors |
| `agent_console.usage_sources` | Usage sources |
| `agent_console.import_sources` · `agent_console.exporters` | Import sources, export formats |
| `agent_console.memory_scope_kinds` · `agent_console.wiki_write_checks` · `agent_console.wiki_search_indexes` | Memory scope kinds, wiki write checks, wiki search indexes |
| `agent_console.architecture_profiles` · `agent_console.sdd_verification_sources` | Architecture map profiles, spec verification sources |
| `agent_console.server_modules` | Server feature modules and link modules |

The complete list, with the interface of each extension point, is in the
[extension guide reference](extending/reference.md), which is generated from the package declarations. On the web
side there are extension points for settings form widgets and dashboard widgets.

[`examples/extensions/`](../examples/extensions/README.md) has a working example package for each group. Install one
and restart the server, and the new kind shows up in the editor and the settings forms.

```bash
uv pip install -e examples/extensions/agent-console-example-nodes
```

The server starts with an empty workspace. Agents and teams are created by the user in the UI, or imported from an
existing `.claude/` folder.
