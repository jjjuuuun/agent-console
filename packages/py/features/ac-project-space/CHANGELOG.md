# Changelog

## Unreleased

- Numbering of manifest backup names now uses `agent_console_store.numbered_id` (same behavior).
- The `.gitignore` template has name placeholders (`{state_dir}`, `{memory_file}`, `{records_file}`,
  `{sessions_dir}`), and `init_space`, `missing_gitignore_lines` and `append_gitignore` fill them from the space
  layout (`SpaceLayout`). New public `render_gitignore_template(template, layout)`, `GITIGNORE_FIELDS` and
  `default_gitignore_template(layout=None)` (when omitted, the text is filled with the default layout, giving the same
  result as before).
- Moved `testing.FolderSpaces` (`open_space` from a list of registration ids to folders) here from
  `link-projects-sdd` (`link-projects-wiki` uses it too).

## 0.1.0

- `SpaceError` extends `agent_console_store.StoreError` (the shared error mapping of definition routes responds with
  the `code` as is, for example `project.config_readonly` 409). `SecretRejected.field_issues()` (one
  `secret.plain_found` error issue per location, without the value). The pre-write check calls `ensure_writable()`
  (`VersionWriteCheck`) of the version store, so when the record database cannot be written (for example, an older
  revision) the definition file is not written either (`RecordsUnavailable` 409).
- `missing_gitignore_lines` and `append_gitignore` (check and append missing lines of the `.gitignore` template).
- First release: `open_space` and `init_space` (create the manifest and the `.gitignore` template only when missing,
  adopt them when present, and report `config_writable=false` when the folder cannot be written), `read_manifest`,
  `write_manifest` (If-Match, keeps unknown keys and comments) and `reset_manifest`, rejection of stored secrets (only
  `secret://` references), and the injected file system (`SpaceFiles`).
