# Changelog

## Unreleased

- The description of the `doc_<id>_file` template variables listed by `template_variables` is now one fixed text (the
  document id is in the variable name and the file name is its example), so the web can translate it.
- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs` `ac-sdd`, so
  the web app can show the run input template variable descriptions in English (data only, no API change). The
  placeholder row of task field variables is now named `task_field_<field>`.
- The description of the `task_field_<field>` template variables listed by `template_variables` is now one fixed
  text (`변수 이름에 적힌 작업 필드의 값입니다.`) instead of naming the field, so the web app can translate it by
  source text. The field name is still in the variable name.
- `SpecRepository.save_as_template(..., taken=())`: like `create_template`, ids made from the name and new ids from
  `rename` avoid `taken` (for example, reserved path words, case-insensitive). A given id is kept as is (rejecting it
  is up to the caller). Omitted means the current behavior.
- Numbering of imported document content file names now uses `agent_console_store.numbered_id` (same behavior).
- `slug_id` and `unique_id` are re-exported from `agent_console_store` (the `_ids` copy is removed, same rules).

## 0.1.0

- First release: package default task syntax data `data/default_syntax.yaml`, `load_default_syntax`,
  `merge_syntax` and `effective_syntax` (origin per value, turning defaults off), `status_infos` and
  `document_state_infos`, `compile_syntax`, `parse_spec` (markdown-it-py block structure plus head line analysis),
  `patch_task` (a single line, with line hash conflicts), and the test helpers `agent_console_sdd.testing`.
- Plan `plan` (graphlib layers plus the longest path, cycles, the `weight` role), trace `trace` (five kinds of gaps
  and orphans), gates `gate_context`, `evaluate_gates`, `require_gates` and `gate_documents`, rule checks
  `check_rules`, run input `run_input_variables`, `run_input_values` and `render_run_input`, template to spec and back
  `instantiate`, `spec_to_template`, `definition_kinds` and `blank_documents` (`data/blank_spec.yaml`),
  `SpecRepository` (on top of the definition store: create, document content, state transitions, task edits, save as
  template), `SpecFiles`, `LocalSpecFiles` and `check_project_path`, `import_documents`, `export_documents` and
  `list_import_files`, the extension point protocols `VerificationSource` and `TaskIntegration` with optional
  capabilities, errors under `SddError`, and test fakes (`MemorySpecFiles`, `FakeVerificationSource`,
  `FakeTaskIntegration`, `memory_repository`). Added dependencies: conditions, store and text-template.
- `SpecRepository(template_store=…)`: document templates are read from and written to a store other than the specs
  (default = `store`).
- Contract follow-up (0.13.1): documented and published the optional capability protocol
  `TaskIssueSource.task_issues(ctx, tasks)` (task issues from a task integration go to `ParsedTask.issues`). The
  method shape is the one already in use.
- `list_import_files` also returns the immediate subfolders `ImportFileListing.dirs` (not recursive; hidden folders,
  links and reserved root folders are excluded; sorted by name; each up to `limit`, with `truncated` beyond that).
- `SpecRepository.create_template` (an empty template, `taken` = ids to avoid), `save_template` (`If-Match`) and
  `delete_template` write to the template store (`template_store`).
- Status words at the start of a line: when the syntax has `task.status_pattern` (named group `status`), the status
  of a task line without a checkbox is read from that word (the matched range is removed before reading the id,
  fields and title), and `patch_task` replaces only the `status` group range or inserts `task.status_format` before
  the body of a line without a status. The shape for appending fields is `task.field_format` (the argument
  `field_format` takes priority when given; the default None means the syntax). The defaults of both shapes are
  package data (`"{marker} "` and `"[{key}: {value}]"`), and only `{name}` placeholders are replaced (not
  `str.format`). Syntax check warning `sdd.status_pattern_ignored` (`no_status_group`, `checkbox`). When the status
  cannot be read back from a line where only fields were edited, `validation_failed`
  (`details.reason = status_lost`). `HeadLine.body_start` and `status_span`, `CompiledSyntax.status_pattern`, `status_format` and
  `field_format`. The default syntax behaves as before.
- Rule checks look at the run profile `document_state_on`: unknown documents report `sdd.not_found` (only when a
  document list is given), unknown states report `sdd.unknown_state` (error), and a missing transition to that state
  with `run` in `by` reports `sdd.transition_denied` (warning).
- Performance (the `parse_spec` target of 300 ms): cyclic GC is paused during parsing and restored afterwards (left
  alone when already off, and restored on exceptions too; markdown-it tokens are alive all at once, and full-heap GC
  took about a quarter of the time), position calculations in head line analysis use expressions instead of function
  calls, single-line bodies strip leading spaces and tabs instead of calling `textwrap.dedent` (same result), blank
  lines of requirement documents skip the regular expression, and tokens that need no work are filtered first in the
  token loop. 400 KB with 3,000 tasks went from about 315 ms to about 210 ms. The output is unchanged.
