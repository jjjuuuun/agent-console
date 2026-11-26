# agent-console-sdd

The core Agent Console SDD (spec-driven development) library. It does not know the server, runs, or projects, and handles only **Markdown document strings**,
the contract models (`agent_console_contracts.sdd`), and the injected definition store (`ac-store` `DefinitionStore`) and file access
(`SpecFiles`).

- **Task syntax is data.** The package default (`data/default_syntax.yaml`) → the user setting `sdd.syntax` → the spec's
  `rules.syntax` (+ `rules.task_statuses`) override in that order. None means "inherit", and an empty list means "none at this layer".
  The first level (`task`, `requirement`, `stage`) is merged per key, and the values below it (lists, `roles`) are replaced as a whole.
  The provenance of each value (`default`, `settings`, `spec`) is kept in `EffectiveSyntax.sources`. The default syntax can be turned off
  (`SddSettings.include_default_syntax: false` → 0 tasks + `sdd.syntax_missing`).
- **The source of tasks is the Markdown text.** `parse_spec` builds tasks, fields, requirement ids, and phases every time it reads (nothing is stored).
  Block structure (lists, headings, code blocks, quotes, line ranges) is read by markdown-it-py, and the check boxes, ids, and `[key: value]` fields in the head line
  by syntax regexes (`ac-safe-regex`, with time and length limits). Lists inside code blocks and quotes are not tasks.
- **The only field roles the code understands are dependencies (`dependencies`), requirements (`requirements`), and assignee (`assignee`)** (+ the optional `weight`).
  Which field has which role is the syntax `roles` data. Statuses, fields, phases, and document names are all data.
- **Changing a status = editing one line.** `patch_task` changes only the check box character and the field values in that task's head line, and leaves the other
  bytes (line break style, indentation, trailing spaces, other lines) as they are. Conflicts are detected by the head line hash (`line_hash`).
- **Leading-word statuses** (instead of check boxes, `- TODO: payment`): give only data in the syntax, such as `task: {list_item: bullet, status_pattern:
  '^(?P<status>TODO|DONE):\s+', status_format: '{marker}: ', statuses: [{id: todo, marker: TODO}, {id: done,
  marker: DONE, done: true}]}` (not in the default syntax; when given together with the check box shape, check boxes come first).

## Dependencies: what / why / alternatives

- **markdown-it-py** (MIT, active): a CommonMark block parser. The token `map` gives line ranges, which makes editing source lines easy.
  Inline parsing is turned off (block structure only), so it is fast even on large documents. Alternatives: mistune (weak line ranges), a hand-written line parser (many code block
  and nested list exceptions). `mdit-py-plugins` (tasklists) is not used: check box characters are data
  (`~`, `?`, and so on), so a plugin that knows only the standard tasklist (`[ ]`, `[x]`) cannot read them, and head line analysis is needed anyway.
- **ruamel.yaml**: reads the package default syntax data (the YAML library used across the repository).
- Internal: `agent-console-contracts` (models), `agent-console-safe-regex` (user regexes),
  `agent-console-conditions` (gate and profile conditions, so there is no new expression language), `agent-console-text-template`
  (run input templates, so the same safe substitution is not kept in two places), `agent-console-store` (the definition store protocol,
  `DefinitionKind`, path checks; specs and templates are definition kinds, so there is no new store).
- The standard `graphlib`: topological layers of the plan (alternative networkx, a heavy dependency).

## Installation

```bash
pip install agent-console-sdd
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> agent-console-sdd
```

## Minimal usage (document strings → task list, without the server)

```python
>>> from agent_console_contracts.sdd import SpecDefinition
>>> from agent_console_sdd import effective_syntax, find_task, parse_spec, patch_task

>>> spec = SpecDefinition.model_validate({
...     "kind": "spec", "id": "demo", "name": "데모",
...     "documents": [{"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]}],
... })
>>> text = (
...     "## 1단계\n"
...     "- [x] 1.1 뼈대 [owner: be] [depends: —]\n"
...     "- [ ] 1.2 화면 [owner: fe] [depends: 1.1]\n"
...     "- [ ] 1.3 검증 [depends: 1.1~1.2]\n"
... )
>>> syntax = effective_syntax()          # the package default syntax (can be turned off)
>>> index = parse_spec(spec, {"tasks.md": text}, syntax)
>>> [(t.key, t.status, t.ready, t.dependencies) for t in index.tasks]
[('1.1', 'done', False, []), ('1.2', 'todo', True, ['1.1']), ('1.3', 'todo', False, ['1.1', '1.2'])]
>>> index.stages[0].id, index.stages[0].done, index.stages[0].total
('1단계', 1, 3)

>>> task = find_task(index, "1.2")
>>> print(patch_task(text, task, syntax=syntax, status="done", fields={"owner": "qa"}), end="")
## 1단계
- [x] 1.1 뼈대 [owner: be] [depends: —]
- [x] 1.2 화면 [owner: qa] [depends: 1.1]
- [ ] 1.3 검증 [depends: 1.1~1.2]

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

Changing the syntax: pass spec rules (`SpecRules.syntax`, `task_statuses`) and user settings
(`SddSettings`) to `effective_syntax(rules, settings)`, or give the layers directly with `merge_syntax(("default", ...), ("spec", {...}))`. Parsing problems
are all collected in `index.issues` as `SpecIssue` (document, line, task key, code; no raw values), and those tied to one task also go into that task's
`issues`. Codes: `sdd.duplicate_task_id`, `unknown_dependency`, `dependency_cycle`,
`unknown_status_marker`·`range_unresolved`·`unknown_requirement`·`document_missing`·`parse_timeout`·
`too_many_tasks`·`syntax_missing`·`invalid_pattern`·`duplicate_status_marker`·`status_pattern_ignored`.

## Plan, trace, gates (without the server)

```python
>>> from agent_console_sdd import compile_syntax, plan, trace
>>> compiled = compile_syntax(syntax)
>>> index = parse_spec(spec, {"tasks.md": text}, compiled)
>>> p = plan(index, compiled)   # unfinished tasks: layers (= parallel groups), bottlenecks, cycles
>>> p.layers, p.critical_path
([['1.2'], ['1.3']], ['1.2', '1.3'])
>>> trace(index, [], [], syntax=compiled).rows   # without a requirements document, there are no rows
[]

>>> from agent_console_conditions import builtin_operators
>>> from agent_console_contracts.sdd import SpecRules
>>> from agent_console_sdd import evaluate_gates, gate_context
>>> ops = {op.descriptor.id: op for op in builtin_operators()}
>>> rules = SpecRules.model_validate({"gates": [{
...     "id": "design-ok", "applies_to": ["run"], "message": "설계 승인 전",
...     "require": {"all": [{"path": "/documents/design/state", "op": "eq", "value": "approved"}]}}]})
>>> [b.details.document_ids for b in evaluate_gates(rules, "run", gate_context(spec), operators=ops)]
[['design']]

```

- `plan(index, syntax)`: finished dependencies are resolved, and dependencies not in the documents are ignored. Tasks in cycles and the tasks that depend on them
  are not put into layers but into `blocked` and `cycles`. The bottleneck weight is the field with the `weight` role in the syntax `roles` (1 if none).
- `trace(index, links, results, *, syntax, max_runs, run_kinds, failed_results)`: gaps `no_task`, `no_run`,
  `not_verified`, `verification_failed`, `task_not_done`, and orphans (tasks without requirements, references to unknown requirements, links pointing to task keys
  that no longer exist). The verification result values that count as failures (`failed_results`) and the link kinds counted as runs are arguments.
- When gates are evaluated (`run`, `task_status`, `document_state`) is a code concept, and the context is
  `{spec, documents: {<id>: {state, title}}, task, stage, change}`. Unknown operators and missing values are false, so they block.
- `check_rules(rules, *, operators, documents, settings, graphs)`: duplicate syntax regexes and markers, condition checks,
  unknown statuses, profiles, and variables, teams missing from the space (when the list is given). Broken rules become issues too, without exceptions.
- `render_run_input(profile, task, spec, *, spec_dir)`: the variable table is `run_input_variables(documents)` (shared by specs and
  templates). `spec_dir` must be a path relative to the project folder (absolute paths raise `SpecPathError`).

## Store, import and export

```python
>>> from agent_console_sdd.testing import MemorySpecFiles, memory_repository
>>> from agent_console_sdd import import_documents, list_import_files
>>> repo = memory_repository()   # in real use, SpecRepository(store, spec_kind=…, template_kind=…)
>>> folder = MemorySpecFiles({"docs/tasks.md": "# 작업\n- [ ] 1 첫 일\n", "docs/.x.md": "숨김"})
>>> [f.name for f in list_import_files(folder, "docs", extensions=[".md"]).files]
['tasks.md']
>>> [d.name for d in list_import_files(folder, "", extensions=[".md"]).dirs]   # subfolders (not recursive)
['docs']
>>> got = import_documents(folder, ["docs/tasks.md"])
>>> stored = repo.create(name="Demo", documents=got.documents, contents=got.contents)
>>> stored.id, [d.title for d in stored.spec.documents]
('demo', ['작업'])

```

- `SpecRepository(store, *, spec_kind, template_kind, operators, settings, directory, …)`: definition kind names and
  folders are caller data (`definition_kinds(...)` builds two `DefinitionKind`s; specs are `library=False`).
  Create (copying a template; the spec file has no template id, only the version message / imported documents / an empty spec = the package data
  `data/blank_spec.yaml`), saving rules, document bodies (`If-Match` with the file sha256; `DocumentMissingError` when missing,
  reads never create; only `create_only` creates; status `on_edit`), status transitions (`from`, `to`, `by` of `transitions`,
  gates), editing tasks (reparse the latest source → task key → compare the head line hash; passes even if other lines changed; on a definition save
  conflict, retries once), template lists, and saving as a template (`fail`, `overwrite`, `rename`). When document templates are in another store,
  pass it as `template_store` (for example a spec in a standalone space + templates in the app library; the default target of reading templates, listing them, and saving as a template).
- `SpecFiles` (protocol): only paths relative to the project folder. This package rejects `..`, absolute paths, drives, links, and reserved folders
  first (`check_project_path`), and the default implementation `LocalSpecFiles(root)` checks once more that the real path with links resolved is inside the folder.
  Import and export are copies and are not linked to the source.
- Errors are subclasses of `SddError` (`code` = contract error code, no raw values in `details`): `SpecNotFoundError`,
  `DocumentMissingError`·`DocumentExistsError`·`DocumentChangedError`·`TransitionDeniedError`·
  `GateBlockedError`, `TemplateExistsError`, `SpecPathError`. Store errors (`VersionConflict` and others) are raised as is.

## Extension points

- **`VerificationSource`**: `id` + `async collect(VerificationContext) -> list[VerificationResult]`.
  Sources that read files use only `ctx.spec.files` (inside the folder only).
- **`TaskIntegration`**: `id` + `async actions(ctx, task)`·`invoke(ctx, task, action, args)`·
  `links(ctx, tasks)` (collected at once). Optional capabilities `ProfileChecker.check_profile`,
  `TaskIssueSource.task_issues(ctx, tasks) -> list[SpecIssue]` (synchronous, added to `ParsedTask.issues` per task key;
  for example `sdd.status_not_applied`, `sdd.automation_skipped`), `AutomationControl`
  (`automation_state`·`control(op)`).
- Example implementations (test fakes): `agent_console_sdd.testing.FakeVerificationSource`, `FakeTaskIntegration`.

## Rules in brief

| What | Rule |
| --- | --- |
| Task key | The task id, otherwise `@<document id>:<index within that document>`. When the same id appears again, the later one gets a position key + `sdd.duplicate_task_id` |
| Task and requirements documents | Only documents whose `roles` include `tasks` or `requirements` are read. Documents without roles are checked only for existence and hash |
| Range `a~b` | Everything from a to b in document order (for both dependencies and requirements). A word after the end (`T11 all`) is looked up by its first word |
| Unknown dependencies | Only reported as issues; they do not block readiness (`ready`) |
| Unknown requirements | `sdd.unknown_requirement` (info) only when the requirements document was read |
| Limits | `max_tasks` (the whole spec), `timeout_ms` (one document; beyond it, that document's tasks and requirements are dropped) |
| Lists without check boxes (`list_item: bullet`, `ordered`) | Treated as the first task status; changing the status inserts `[char] ` after the list marker |
| Appending missing fields | At the end of the head line (before trailing spaces) with `field_format` (default `[{key}: {value}]`); refused if it cannot be read back |

## Test helpers

`agent_console_sdd.testing`: sample documents (`sample_spec`, `sample_files`, `render_tasks`), a syntax with every name changed
(`RENAMED_SYNTAX`, `RENAMED_NAMES`), the fake file access `MemorySpecFiles`, fake verification sources and task integrations, and a memory store
assembly `memory_repository` (kind names `TEST_SPEC_KIND`, `TEST_TEMPLATE_KIND`). These are test samples, not a default syntax
or presets.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
AGENT_CONSOLE_PERF=strict uv run pytest -k perf   # wall-clock assertions (on an idle machine)
```
