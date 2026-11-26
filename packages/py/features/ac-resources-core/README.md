# agent-console-resources-core

The 7 default resource kind plugins. `ac-resources` does not know these names;
this package only registers them through the entry point `agent_console.resource_types`. If you remove this package or
leave a kind out in `load_resource_types(..., enabled={...})`, that kind disappears from the list, and its attachments
drop out of the bundle with a `resource.unknown_type` warning (the system keeps working).

## Installation

```bash
uv sync --all-packages                            # inside the workspace
uv pip install ./packages/py/features/ac-resources-core    # standalone
```

## Registration (entry point)

| Name (= key = descriptor id) | Object | Slot filled | Slot key |
| --- | --- | --- | --- |
| `instruction` | `instruction:InstructionType` | `instructions` | `title` |
| `file` | `file:FileType` | `files` | `name` |
| `mcp-server` | `mcp_server:McpServerType` | `mcp_servers` | `name` |
| `tool-permission` | `tool_permission:ToolPermissionType` | `tools` | (none → only replacing the same resource) |
| `skill` | `skill:SkillType` | `skills` | `name` |
| `rule` | `rule:RuleType` | `rules` (fallback `instructions`) | `name` |
| `hook` | `hook:HookType` | `hooks` | (none) |

## Slot value format (the shape backends and agent nodes read)

Every slot is a **list of items**, and the default combination is `append` (layer order = list order).

| Slot | Item | What the receiver does |
| --- | --- | --- |
| `instructions` | A string (instruction body, with a `## Title` heading when `heading` is set) | Concatenates them in order (instructions with `position: prepend` are already at the front) |
| `files` | `{name, content, encoding: utf-8\|base64, media_type?}` | The agent node writes them into the run folder and replaces them with paths. The writer also checks that `name` does not leave the folder |
| `mcp_servers` | `{name, type: stdio\|http\|sse, command?, args?, env?, url?, headers?}` | `name` → SDK `McpServerConfig`. For the same name, the later item wins. `env` and `headers` values are `secret://` references, so resolve them with the secret provider |
| `tools` | `{tools?, disallowed_tools?, commands?}` | Combined with the receiver's rules, such as allow = union and deny takes precedence |
| `skills` | `{name, files: [{name, content, encoding, media_type?}]}`: every file in the body folder (path = `name`) | When the agent node writes them into the run folder with `write_item_trees`, they become `{name, root, tree_root, files: [{name, path}]}`. The backend passes that folder on in its own format (claude-sdk: a local plugin) |
| `rules` | `{name, paths, text, instruction, files: [{name: "<rules_dir>/<name>.md", content}]}` | `instruction` = path header (config `paths_header`) + body; when delivered as instructions, this is what gets concatenated. When delivered as files, use the `root` the node wrote (containing `.claude/rules/<name>.md` with `paths` frontmatter). For backends that do not accept `rules`, `instruction` goes into the `instructions` slot (fallback contribution) |
| `hooks` | `{name, event, matcher?, command, timeout_seconds?}` | `event` is a free string (no fixed list). Whether and how hooks run is decided by the backend and the server administrator settings |

## Minimal usage

```python
>>> from agent_console_contracts import Resource, ResourceAttachment
>>> from agent_console_resources import (
...     AttachmentLayer,
...     InMemoryResources,
...     compose_bundle,
...     load_resource_types,
...     new_resource_types,
... )

>>> types = new_resource_types()
>>> loaded = {r.key for r in load_resource_types(types) if r.status == "loaded"}
>>> {"file", "hook", "instruction", "mcp-server", "rule", "skill", "tool-permission"} <= loaded
True

>>> resources = InMemoryResources(
...     [
...         Resource(
...             id="team-md",
...             type="instruction",
...             name="팀 지침",
...             config={"title": "CLAUDE.md"},
...             content={"file": "content.md"},
...         ),
...         Resource(
...             id="gh",
...             type="mcp-server",
...             name="GitHub",
...             config={
...                 "name": "github",
...                 "transport": "http",
...                 "url": "https://example.invalid/mcp",
...                 "headers": {"Authorization": "secret://github_token"},  # secrets only as references
...             },
...         ),
...     ],
...     contents={"team-md": "팀 규칙"},
... )
>>> result = compose_bundle(
...     [AttachmentLayer("team", [ResourceAttachment(ref="team-md"), ResourceAttachment(ref="gh")])],
...     types=types,
...     resources=resources,
... )
>>> result.bundle.slots["instructions"]
['팀 규칙']
>>> result.bundle.slots["mcp_servers"][0]["type"], result.issues
('http', ())

```

## Security

- `env` and `headers` values of `mcp-server` accept only `secret://name` (`resource.plain_secret` error, which reports the location
  but not the value). Pass plain flags through `args`. The value schemas of `env` and `headers` in the schema have `x-secret: true`
  (a structural hint for the screen to draw a secret input field; see "Secret field display" in the `ac-resources` README).
- No issue message contains input values. Config schema violation messages are built by `ac-resources` only from the schema's
  expectations (type, list of allowed values, presence of a pattern, and so on).
- The `name` of `file` cannot contain control characters (including NUL).
- The `name` of `file` must be a relative path (`..`, absolute paths, drives, and backslashes are rejected with `resource.unsafe_path`).
- No kind writes files or resolves secrets.
- If the `command` of `hook` contains a value suspected to be a plain-text secret (`ac-secret-rules` default rules: `--token x`, known token prefixes, and so on),
  it is not saved and reports `resource.plain_secret` (path `/command`, no value). Pass secrets through environment variables.
- `skill` does not check the contents of body files (there are many files with free formats). Do not put secrets in skill files.
- `skill` and `rule` names and the `rules_dir` of `rule` accept only values that are safe as folder and file names.

## Event suggestions (`hook`)

`HookType(event_examples=[…])` changes only the schema `examples` (suggestions for the screen's combo box). The default suggestions
`DEFAULT_EVENT_EXAMPLES` are data and are not used for validation; event names that are not in the list are saved too.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-resources-core`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/features/ac-resources-core
```
