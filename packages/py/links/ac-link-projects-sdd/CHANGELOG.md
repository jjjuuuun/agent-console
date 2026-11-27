# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-projects-sdd`, so the web app can show the link module description and settings in English (data only, no
  API change).
- The path guard (reserved paths and real paths after resolving links) now uses `ac-projects` `FolderGuard`,
  `normalize_reserved` and `relative_inside` (same behavior, one set of rules shared with `link-projects-wiki`).
  `normalize_reserved` is still re-exported. `testing.FolderSpaces` is a re-export of the one in
  `agent_console_project_space.testing`.

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- Provides `sdd.spaces` (`ProjectSddSpaces`, `ProjectSddSpace`), `ProjectSpecFiles` that only reads and writes inside
  the folder (reserved paths, links, 409 when not writable), manifest checks, the setting `reserved_dirs`, and
  standalone runs.
- `ProjectSpecFiles.list` marks subfolders whose real path after resolving links is outside the folder as links
  (`is_link=True`). Reparse points that are not recognized as links are also left out of the import list, and opening
  them raises `SpecPathError(link)`.
