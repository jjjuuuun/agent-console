# agent-console-projects

Pure project rules. A project = **one local folder + the configuration copies inside that folder**
(`<folder>/.agent-console/`). You use it without the server, the web app, or a store (dependencies: `agent-console-contracts`,
`agent-console-local-folders`). It does not write files; the file system, reference extraction, and reference rewriting are injected.

- **It knows no definition kind names or settings field names.** Copy plans handle only (kind, id), and references are
  injected through `references(kind, doc)` and `rewrite_references(kind, doc, renames)`. Path guarding looks only at
  the schema annotation `x-path`.
- Path comparison reuses `ac-local-folders` (`path_key`, `is_within`, `normalize_lexical`).
  Windows paths always ignore case. POSIX path prefixes that should ignore case are added through the data file
  `data/path_rules.json` (`case_insensitive`, empty by default) or `load_path_rules(extra)`.
  Examples: WSL drvfs `{"pattern": "/mnt/?"}`, macOS external volumes `{"pattern": "/Volumes/*"}`.
- Messages come from default tables (`DEFAULT_COPY_MESSAGES` and others, `string.Template`) and can be replaced with `messages=`.

| Function | What it does |
| --- | --- |
| `folder_conflicts(projects, folder, *, exclude_project_id)` | Identical or overlapping registrations. Identical includes unregistered ones; overlapping excludes them |
| `conflict_status`, `conflict_error_code`, `conflict_details` | Conflict → check status, 409 code, `details` |
| `registry_conflicts(projects)` | Overlaps between old files (status `folder_conflict`) |
| `project_status(project, *, fs, conflicts, manifest_invalid)` | Status `ready`, `folder_missing`, `not_a_directory`, `no_access`, `folder_unset`, `folder_conflict`, `manifest_invalid` |
| `project_for_path(projects, path)` | The id of the registered project that contains the path (including subfolders) |
| `project_folders(projects, *, base_dir)` | All registered (not unregistered) folders plus ids (`ProjectFolderSet.entries`, `project_for`) |
| `folder_slug`, `registration_id`, `suggest_project_id` | Folder name slug (`proj-<4-character hash>` when it cannot be converted), `-2`… on overlap |
| `merge_project(registration, manifest)` | Registry + manifest → `Project` (old registry values when there is no manifest) |
| `split_project`, `initial_manifest`, `legacy_manifest_values` | Splitting values to store, the first manifest, moving old values |
| `combined_version(reg, manifest)` | An `If-Match` value that combines both file versions |
| `ignored_key_issues(doc)` | Old keys (`uses`, `import_mode`, `log_projects`) → info issue `settings.ignored_key` |
| `copy_plan(requested, source_docs, target_index, *, references, target_label, plain_secrets)` | A copy plan between spaces (reference closure, `target_state`, default action, cycles, missing reference warnings). Items caught by `plain_secrets` (the same judgement as the target space's write check, injected) are blocked (`blocked`, default action skip, error `secret.plain_found`, no value) |
| `copy_target_label(project_name, *, messages)` | The `${target}` of messages (Shared library / Project “name”, from the message table data) |
| `skip_warnings(plan, actions, *, target_index)` | Definitions that would be blocked before running because of skipped references |
| `apply_decisions(items, *, source_index, target_index)` | Apply decisions (only changed items are `conflict`) |
| `apply_renames(docs, renames, *, rewrite_references)` | New ids plus rewriting references inside the set |
| `reserved_target_issues(items, reserved_ids, *, target_index, messages, target_label)` | For each item in an apply request whose id to write in the target (copy and overwrite = the source id, rename = the new id) is a reserved word of that kind (case-insensitive), error `project.copy_reserved_id` (`details{kind, id, action, target_id, reserved, suggested_id}`, plus `new_id` for rename; message keys `COPY_RESERVED_RENAME`, `COPY_RESERVED_WRITE`). reuse and skip are not checked. If there is even one, the caller writes nothing and rejects the request |
| `find_referrers(target, documents, references, *, messages)` | Reverse references: definitions in the same space that use `target` (reference extraction injected, kind names unknown). Without reference extraction, `checked` is False plus info `project.references_unavailable` |
| `path_fields(schema, value)`, `outside_paths(value, schema, root, allowed)` | Finds `x-path` values, paths outside the project folder |
| `FolderGuard(folder, *, reserved, realpath)`, `normalize_reserved`, `relative_inside` | Path guarding for file access inside a folder: reserved paths (case-insensitive) and whether the real path with links resolved is inside the folder. Checking path strings is up to the caller |
| `legacy_items`, `legacy_counts`, `without_scope_field` | Interpreting old project-only definitions (`project` field) (cleanup = copy plan input, input shape `ScopedDefinition`) |
| `project_layer_value(project)` | The project layer value (fields set in `settings` + project folder = `folder`) |
| `CODE_UNKNOWN`, `CODE_REFERENCES_UNAVAILABLE` | Issue code aliases (`project.unknown` and `project.references_unavailable` of the contract `KnownIssueCodes`) |

## Dependencies: what / why / alternatives

- Internal: `agent-console-contracts` (contract models), `agent-console-local-folders` (path normalization and containment checks,
  so the same rules are not kept in two places; alternative: copy string rules into this package). It does not import `ac-teams` (references),
  `ac-store` (definition store), or `ac-project-space` (folder files) (import-linter contract).

## Installation

```bash
pip install agent-console-projects
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> agent-console-projects
```

## Minimal usage

```python
>>> from agent_console_projects import (
...     SourceDefinition, copy_plan, folder_conflicts, merge_project, outside_paths,
...     suggest_project_id)
>>> regs = [{"id": "pay", "folder": "/w/pay"}]
>>> [(c.project_id, c.relation) for c in folder_conflicts(regs, "/w/pay/api", flavor="posix")]
[('pay', 'parent')]
>>> suggest_project_id("/w/pay-wt", manifest_id="pay", taken_ids=["pay"], flavor="posix")
'pay-2'
>>> merge_project({"id": "pay-2", "folder": "/w/pay-wt"}, {"id": "pay", "name": "결제"}).name
'결제'
>>> lib = {("graph", "team"): SourceDefinition({"id": "team", "uses": ["coder"]}, "g1"),
...        ("agent", "coder"): SourceDefinition({"id": "coder"}, "a1")}
>>> def refs(kind, doc):  # injected reference extraction (on the server, the port definitions.references)
...     return [("agent", x) for x in doc.get("uses", [])]
>>> plan = copy_plan([("graph", "team")], lib, {("agent", "coder"): "a1"}, references=refs)
>>> [(i.id, i.target_state, i.default_action) for i in plan.items]
[('team', 'absent', 'copy'), ('coder', 'identical', 'reuse')]
>>> from types import SimpleNamespace
>>> def plain(kind, doc):  # injected judgement (on the server, scan_secrets with the target space's secret rules)
...     return [SimpleNamespace(path="/api_key", reason="key_name")] if "api_key" in doc else []
>>> leaky = {("agent", "a"): SourceDefinition({"id": "a", "api_key": "plain-value"}, "v1")}
>>> plan = copy_plan([("agent", "a")], leaky, {}, references=None, plain_secrets=plain)
>>> item = plan.items[0]
>>> item.blocked, item.default_action, [(i.code, i.path) for i in item.issues]
(True, 'skip', [('secret.plain_found', '/api_key')])
>>> "plain-value" in plan.model_dump_json()
False
>>> schema = {"properties": {"cwd": {"x-path": "directory"}}}
>>> [p.resolved for p in outside_paths({"cwd": "../x"}, schema, "/w/pay", flavor="posix")]
['/w/x']

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```
