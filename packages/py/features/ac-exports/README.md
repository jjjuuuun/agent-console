# agent-console-exports

The extension point that **exports** definitions (agents, resources, teams) into other tools' formats. Flow:
format list → preview (file list, conflicts, warnings, no writes) → an archive file (zip, in memory) or a write into an allowed folder.
Contracts: `agent_console_contracts.exports`.

- **Formats are plugins.** A format = `Exporter{descriptor, plan(items, catalog, options) -> ExportOutput}`.
  `plan` is pure (it only reads the catalog and returns the file contents it builds). Format factories (server administrator options → format) are
  registered through the entry point `agent_console.exporters`. The service does not know format names.
- **Default format (first implementation)**: `claude-dir`, the Claude Code project artifacts (`.claude/agents`, `.claude/skills`,
  `.claude/rules`, `.claude/settings.json`, `CLAUDE.md`, `.mcp.json`). Conversion is done by `ac-claude-format`.
- **Definitions are only read.** The app passes an `ExportCatalog` (`document`, multi-file bodies `files`, single-file body `content`, `dependencies`).
  The catalog reports the agents, resources, and child teams a team uses (the Agent Console server uses
  `ac-teams.graph_dependencies`). `claude-dir` follows teams among the used definitions (children of nested team nodes) and exports their members
  as agents too (main nodes only from the chosen team; cycles once each).
- **Write safety rules**:
  - The default is an archive (zip) response; nothing is written to the server disk.
  - Folder writes go only to `subdir` under a root the server administrator registered (`ExportRoot`). Path escapes, absolute paths, Windows reserved names,
    and symbolic links or junctions from the root to the target are rejected.
  - Protected locations (for example `~/.claude`) are never written, even if registered as a root (case-insensitive comparison).
  - Conflict handling `on_conflict`: `fail` (default; if anything differs, nothing is written), `skip`, `overwrite`.
    Identical content is always skipped. Each file is written to a temporary file → `os.replace`.
- **Plain-text secret safety net**: the artifacts of every format are checked last with `ac-secret-rules`, suspected values are masked,
  and a warning (`export.secret_redacted`, location only) is emitted. `${NAME}` environment variable expansion counts as a reference.

## Installation

```bash
uv sync --all-packages                     # inside the workspace
uv pip install ./packages/py/features/ac-exports    # standalone (contracts, registry, claude-format, secret-rules, jsonschema)
```

| Dependency | Why | Alternatives |
| --- | --- | --- |
| `agent-console-contracts` | Request, preview, and result contract models (`ExportRequest` and others) | — |
| `agent-console-registry` | Loads format factory entry points (the same way as other extension points) | `importlib.metadata` directly |
| `agent-console-claude-format` | `.claude` conversion for the default format `claude-dir` (shared with import) | Copy it into the format |
| `agent-console-secret-rules` | The last plain-text secret check on artifacts (the same rules as the server's save checks) | A check per format |
| `jsonschema` | Validates options against the format's `config_schema` (the same library as resource kinds) | Hand-written checks |

It does not import store or team semantics (`ac-store`, `ac-teams`). Definitions come in through the `ExportCatalog` protocol.

## Minimal usage

```python
>>> import io
>>> import tempfile
>>> import zipfile
>>> from pathlib import Path
>>> from agent_console_contracts import ExportRequest, ExportSelection, ExportWriteRequest
>>> from agent_console_exports import (
...     ExportRoot,
...     ExportService,
...     FolderWriter,
...     build_exporters,
...     load_exporter_factories,
...     new_exporter_factories,
... )
>>> from agent_console_exports.testing import MemoryCatalog

>>> catalog = MemoryCatalog().add(  # in real use, an ExportCatalog implementation the app builds on the definition store
...     "agent", {"id": "pl", "name": "pl", "system_prompt": "너는 리더다.", "tools": ["Read"]}
... )
>>> factories = new_exporter_factories()
>>> [r.key for r in load_exporter_factories(factories)]  # entry points (default: claude-dir)
['claude-dir']
>>> tmp = tempfile.TemporaryDirectory()
>>> out = Path(tmp.name)  # an export root the user allowed (absolute path)
>>> service = ExportService(
...     build_exporters(factories, {"claude-dir": {}}),  # server administrator options per format
...     catalog,
...     writer=FolderWriter([ExportRoot("out", out)], protected=[Path.home() / ".claude"]),
... )
>>> request = ExportRequest(exporter="claude-dir", items=[ExportSelection(kind="agent", id="pl")])
>>> [(f.path, f.action) for f in service.plan(request).files]  # file list and warnings (no writes)
[('.claude/agents/pl.md', 'create')]
>>> zipfile.ZipFile(io.BytesIO(service.archive(request).data)).namelist()  # zip bytes
['.claude/agents/pl.md']
>>> result = service.write(
...     ExportWriteRequest(exporter="claude-dir", items=request.items, root="out", subdir="proj")
... )
>>> print((out / "proj" / ".claude" / "agents" / "pl.md").read_text(encoding="utf-8"))
---
name: pl
description: ''
tools: Read
---
<BLANKLINE>
너는 리더다.
<BLANKLINE>
>>> tmp.cleanup()

```

## Writing a new format

```python
from agent_console_contracts import ExporterDescriptor
from agent_console_exports import ExportOutput, OutputFile


class MyExporter:
    descriptor = ExporterDescriptor(
        id="my-format", title="내 형식", kinds=["agent"], config_schema={"type": "object"}
    )

    def plan(self, items, catalog, options) -> ExportOutput:
        files = [
            OutputFile(f"{i.id}.txt", str(catalog.document(i.kind, i.id)).encode()) for i in items
        ]
        return ExportOutput(files=files)


# format factory: server administrator options (exports.options.my-format)
def my_exporter(options):
    return MyExporter()
```

```toml
[project.entry-points."agent_console.exporters"]
my-format = "my_pkg.export:my_exporter"
```

The registered name must equal the descriptor `id` (otherwise it is skipped with a warning). Removing the package removes the format too.

## `claude-dir` options (`config_schema`, omitted = default)

| Option | Default | Meaning |
| --- | --- | --- |
| `main_node` | none | The agent of this team node becomes the `CLAUDE.md` body. **Never inferred**. Error if it is not an agent node |
| `agent_file_name` | `{id}.md` | Agent file name template (`{id}`, `{name}`) |
| `instructions_mode` | `inline` | `inline` = appended to `CLAUDE.md`, `separate_files` = `.claude/instructions/<id>.md` + `@path` |
| `include_shared_resources` | true | Also exports attachments of the team layer and the common layer |
| `secret_style` | `env_var` | `secret://NAME` → `${NAME}`, `omit` = secret fields are not written |

The server administrator options `exports.options.claude-dir.mapping` and `layout` change kind names and paths (`ClaudeMapping`, `ClaudeLayout`).
Teams lose their edges, reviews, and per-node settings, so the warning `export.semantics_approximate` is emitted.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-exports`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/features/ac-exports
```

Tests check formats with a fake catalog, the write safety rules (escapes, links, protected locations, conflicts) with a temporary folder, and the plain-text secret safety net.
