# agent-console-imports

Imports definitions (agents, resources) from external settings by **copying** them. The source is only read (no writes, deletes, or renames).
Flow: source list → candidate scan (preview, writes nothing) → import the chosen items (copy into the workspace).
Contracts: `agent_console_contracts.imports`.

- **Sources are an extension point.** A source = `ImportSource{descriptor, scan()}`. Factories that create sources are registered through the entry point
  `agent_console.import_sources`. The server does not know source names.
- **Default source (first implementation)**: the `claude` factory creates `user-claude` (`~/.claude` in the home folder) and `project-claude` (`.claude/` in the project folder +
  `CLAUDE.md` + `.mcp.json`). `user-claude` is a general-purpose part that exists only when `ImportSourceContext.home` is given.
  **The Agent Console app (`mod-imports`) does not pass `home`** (the app does not integrate with anything outside registered project
  folders and its own workspace, so it does not import the user's global `~/.claude` configuration).
- Values that look like secrets (plain `env` and `headers` of MCP servers) are **not stored**; they are turned into `secret://NAME` references and a warning
  reports only their location (`import.secret_replaced`). The `${VAR}` form becomes `secret://VAR`.
- Values that look like secrets in arguments (`--token x`, `--api-key=x`, token-shaped values) and URLs (queries such as `api_key=`, user info) are also
  turned into `secret://` references with an `import.secret_suspected` warning (these fields do not resolve references, so the warning suggests moving them to env or headers).
  The judgement rules are `ac-secret-rules` (shared with the server's save checks). The app can pass `ImportSourceContext.secret_rules` (a function that returns
  the current rules, including user-added rules); without it, the default rules are used. Arguments that contain token shapes inside a string
  (`Bearer x`, JWT, and so on) are turned into references too.
- **Symbolic links are not followed**: link files, files whose real location is outside the source scope (the settings folder, or for a named file, its folder),
  and linked subfolders are skipped (with a log warning). Files are opened with `O_NOFOLLOW`.
- Imported definitions keep `attributes.imported_from{source, path, sha256}`.

## Installation

```bash
uv sync --all-packages                      # inside the workspace
uv pip install ./packages/py/features/ac-imports     # standalone (contracts, registry, secret-rules, claude-format)
```

| Dependency | Why | Alternatives |
| --- | --- | --- |
| `agent-console-contracts` | Candidate and result contract models | — |
| `agent-console-registry` | Loads source factory entry points (the same way as other extension points) | `importlib.metadata` directly |
| `agent-console-secret-rules` | Judges suspected secrets in arguments and URLs (the same rules as the server's save checks, including user rules) | A module inside the contracts package (the earlier design) |
| `agent-console-claude-format` | `.claude` format conversion (shared with the `claude-dir` export, `ClaudeMapping`, `ClaudeLayout`) | Conversion inside this package (the earlier design) |

It does not import the store (`agent-console-store`). Writes go through the structural protocol `DefinitionWriter`
(`list_ids`, `get`, `create`, `save`, `write_content`, `list_files`, `write_files`). The in-memory implementation is
`agent_console_imports.testing.MemoryDefinitionWriter` (for examples and tests). Only some tests use the real store as a dev dependency.

## Minimal usage

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import ImportRequest, ImportSelection
>>> from agent_console_imports import (
...     ImportService,
...     ImportSourceContext,
...     build_import_sources,
...     load_import_source_factories,
...     new_import_source_factories,
... )
>>> from agent_console_imports.testing import MemoryDefinitionWriter

```

Put one agent file in an example home folder (in real use, `Path.home()` or the project folder). The source is only read.

```python
>>> tmp = tempfile.TemporaryDirectory()
>>> home = Path(tmp.name)
>>> (home / ".claude" / "agents").mkdir(parents=True)
>>> _ = (home / ".claude" / "agents" / "reviewer.md").write_text(
...     "---\nname: reviewer\ndescription: 코드 검토\n---\n\n변경을 검토한다.\n", encoding="utf-8"
... )

>>> factories = new_import_source_factories()
>>> [r.status for r in load_import_source_factories(factories)]  # entry points (default: claude)
['loaded']
>>> sources = build_import_sources(factories, ImportSourceContext(home=home, project_dir=None))
>>> store = MemoryDefinitionWriter()  # in real use, a definition store (for example ac-store FileDefinitionStore)
>>> service = ImportService(sources, store)
>>> [d.id for d in service.descriptors()]
['user-claude']

>>> preview = service.preview("user-claude")  # ImportPreview (candidates, conflicts, warnings), no writes
>>> [(c.kind, c.suggested_id, c.conflict) for c in preview.candidates]
[('agent', 'reviewer', False)]
>>> request = ImportRequest(
...     source="user-claude",
...     items=[ImportSelection(candidate_id=c.id, on_conflict="rename") for c in preview.candidates],
... )
>>> [(i.target_id, i.action) for i in service.apply(request).items]
[('reviewer', 'created')]
>>> [(i.target_id, i.action) for i in service.apply(request).items]  # a new name when the id already exists
[('reviewer-2', 'renamed')]
>>> store.documents[("agent", "reviewer")]["system_prompt"]
'변경을 검토한다.'
>>> scoped = request.model_copy(update={"project": "app"})  # request project → stamped into the scope field
>>> [(i.target_id, i.action) for i in service.apply(scoped).items]
[('reviewer-3', 'renamed')]
>>> store.documents[("agent", "reviewer-3")]["project"]
'app'
>>> tmp.cleanup()

```

## What the default source reads

`.claude` format conversion (frontmatter, agent files, rules, settings, `.mcp.json`) is done by `ac-claude-format` (shared with export).

| Source | Definition it creates |
| --- | --- |
| `CLAUDE.md` (instruction file) | Resource `instruction` + body `content.md` |
| `agents/*.md` | Agent: frontmatter `name`, `description`, `tools`, `disallowedTools`, `model` (except `inherit`), body = `system_prompt`. Other keys go to `attributes.claude_frontmatter` (warning `import.fields_ignored`; restored on export) |
| `rules/**/*.md` | Resource `rule`: config `paths` (frontmatter) and `name` (from the relative path), body = the content without the frontmatter |
| `skills/<name>/` (`SKILL.md` + supporting files) | Resource `skill`: config `name` = folder name, name and description = `SKILL.md` frontmatter, **multi-file body** (`write_files` as one version). Skipped when the main file is missing; total size 10 MiB (`max_skill_bytes`) |
| `permissions.allow/deny` in `settings.json` | Resource `tool-permission` (`tools`, `disallowed_tools`) |
| `hooks` in `settings.json` (per command handler) | Resource `hook` (`event`, `matcher`, `command`, `timeout_seconds`). Handlers that are not commands get the preview warning `import.hook_unsupported`; suspected secrets in commands are masked with `import.secret_suspected` |
| `mcpServers` in `.mcp.json` (project source) | Resource `mcp-server` |

Kind names (`agent`, `resource`) and resource kind ids are `ClaudeMapping` data, and subfolder and file names are `ClaudeLayout` data.
You can change them in the server settings with the factory options `{claude: {mapping: {...}, layout: {...}}}`. Files larger than 1 MiB are skipped.

**Skipped link warning**: symbolic link files and folders, and files whose real location is outside the source, are not read and are reported in the preview
`ImportPreview.warnings` as `import.skipped_link` (keys = source paths). They do not block the import.
A race where a parent folder is swapped while it is being read is low risk and only recorded (files are opened with `O_NOFOLLOW`).

## Conflict handling (`ImportSelection.on_conflict`)

`skip` (leave as is) / `overwrite` (save with If-Match against the current version) / `rename` (default, `<id>-2`, `<id>-3`…).
A failure of one item reports only that item as `failed` (with only the error type name).

## Writing a new source

```python
from agent_console_imports import ImportSourceContext, ScanResult


class MySource:
    descriptor = ImportSourceDescriptor(id="my-tool", title="내 도구 설정")

    def scan(self) -> ScanResult: ...  # read only


def my_sources(ctx: ImportSourceContext) -> list[MySource]:
    return [MySource()]
```

```toml
[project.entry-points."agent_console.import_sources"]
my-tool = "my_pkg.imports:my_sources"
```

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-imports`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/features/ac-imports
```

Tests build a fake home and project folder and check, after preview and import, that the source files' contents, modification times, and modes are unchanged.
