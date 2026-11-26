# agent-console-claude-format

A **pure conversion** package that reads and writes Claude Code `.claude` artifacts (agent files, skill folders, rule files, permissions and hooks in `settings.json`, `.mcp.json`).
It never touches the file system: it takes text, bytes, or JSON values and returns value objects,
and builds them back the other way. It has no internal dependencies (only ruamel.yaml), so you can take it to another project as is.

Where Agent Console uses it: `ac-imports` (import source `claude`), `ac-exports` (default export format `claude-dir`),
`ac-resources-core` (rendering rule files of the `rule` kind).

## Installation

```bash
uv sync --all-packages                              # inside the workspace
uv pip install ./packages/py/base/ac-claude-format       # standalone (ruamel.yaml only)
```

| Dependency | Why | Alternatives |
| --- | --- | --- |
| `ruamel.yaml` | Reads and writes frontmatter (YAML), the same library the store and imports use | PyYAML |

## Minimal usage

```python
>>> from agent_console_claude_format import (
...     agent_document,
...     dump_json,
...     mcp_entry_from_config,
...     parse_agent_md,
...     parse_rule,
...     parse_settings,
...     render_agent_md,
...     render_mcp,
...     render_rule,
... )
>>> md = "---\nname: reviewer\ndescription: 코드 검토\ntools: Read, Grep\n---\n\n변경을 검토한다.\n"
>>> agent = parse_agent_md(md, default_name="reviewer")  # usually the contents of '.claude/agents/<name>.md'
>>> agent.tools
['Read', 'Grep']
>>> agent_document(agent)["system_prompt"]  # agent definition document (omitted = inherit)
'변경을 검토한다.'
>>> parse_agent_md(render_agent_md(agent), default_name="reviewer") == agent  # a file with the same meaning
True

>>> rule = parse_rule('---\npaths:\n  - "src/**"\n---\n\n세미콜론\n')
>>> rule.paths, parse_rule(render_rule(rule.paths, rule.body)) == rule
(['src/**'], True)

>>> settings = parse_settings({"permissions": {"allow": ["Bash(git status)"]}})  # a settings.json value
>>> settings.allow, settings.hooks
(['Bash(git status)'], [])

>>> entry = mcp_entry_from_config(
...     {"name": "gh", "transport": "stdio", "command": "npx", "env": {"TOKEN": "secret://GH_TOKEN"}},
...     fallback_name="gh",
... )
>>> print(dump_json(render_mcp({entry.name: entry.entry})), end="")  # secret reference → "${GH_TOKEN}"
{
  "mcpServers": {
    "gh": {
      "type": "stdio",
      "command": "npx",
      "env": {
        "TOKEN": "${GH_TOKEN}"
      }
    }
  }
}

```

## Claude Code folder rules

`project_key(folder, keep="", replacement="-")`: project folder path → folder name under Claude Code `projects`
(for example `/work/demo` → `-work-demo`). The log source (`agent-console-logs-claude`, which re-exports it) and the session
storage of the execution backend (`agent-console-backend-claude-sdk`) both use this one function. It does not touch files.

## Data (what is not fixed in code)

- `ClaudeMapping`: names of the definition kinds it creates and reads (`agent`, `resource`, `graph`), resource kind ids
  (`instruction`, `rule`, `skill`, `hook`, `tool-permission`, `mcp-server`), and the name of the single-file body.
  Change it with `ClaudeMapping.from_options(dict)` (unknown keys raise `ValueError`).
- `ClaudeLayout`: `.claude`·`CLAUDE.md`·`.mcp.json`·`agents`·`skills`·`rules`·`settings.json`·`SKILL.md`·
  `instructions` names.
- hook event names are handled as plain strings (no fixed list). Handlers that are not commands (`type: command`) are only reported by location
  in `skipped_hooks`.

## Secrets

`.mcp.json` uses `${NAME}` environment variable expansion; Agent Console uses `secret://NAME` references.
`mcp_entry_from_config` turns references into `${NAME}` (`secret_style="env_var"`) or drops them (`"omit"`),
and **does not write** env or headers values that are not references; it only records their location in `omitted`. Turning plain text into references is
the job of the importing side (`ac-imports`).

## Round-trip rules

`render(parse(x))` has the same meaning as `x` (only key order, whitespace, and list notation `a, b`/`[a, b]` may differ). Tests
check the round trip for agents, rules, settings, skills, and MCP each.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-claude-format`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/base/ac-claude-format
```
