# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-projects-wiki`, so the web app can show the link module description and settings in English (data only, no
  API change).

## 0.1.0

- First release (from the scripts/pkgkit template `link`): `projects.spaces` to `wiki.spaces` (`ProjectWikiSpaces`,
  `ProjectWikiSpace`), a page folder path guard (`ac-projects` `FolderGuard`: reserved folders and real paths after
  resolving links, `UnsafePagesRoot` 422 `folders.invalid_path`), `config_writable=false` for folders that cannot be
  written (the index stays in memory), 409 for a broken manifest or a missing folder, and the settings `pages_dir`
  (inherits `mod-wiki.pages_dir`), `index_dir` and `reserved_dirs`.
