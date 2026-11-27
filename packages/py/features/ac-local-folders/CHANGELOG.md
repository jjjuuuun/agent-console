# Changelog

## 0.1.0

- First release (from the scripts/pkgkit template `feature`).
- `normalize_lexical`, `normalize`, `check_folder` (`FolderCheck`, `status`), `list_dirs` (`FolderListing`),
  `make_folder`, `default_roots`, `nearest_existing`, `path_key`, `is_within` and `validate_folder_name`, the injected
  file system `FileSystem` (`LocalFileSystem`, `MemoryFileSystem`), and the rule data `data/browse_defaults.json`.
- Removed features specific to one runtime environment: path translation suggestions for another OS
  (`suggest_native`, `TranslationRule`, `load_path_translations`, `FolderCheck.suggestion`,
  `data/path_translations.json`), the default list of Windows system folders hidden by name (`hidden_names` now
  defaults to an empty list; the hidden attribute check is unchanged), and the rule that used drive mount folders as
  the starting location. Paths from another OS are only reported as `foreign_path`.
- Native folder picker dialog: command table data `data/folder_dialogs.json` (Windows PowerShell
  `FolderBrowserDialog`, macOS `osascript`, `zenity`, `kdialog`), `load_dialog_specs`, `probe_dialogs`,
  `select_dialog` and `run_dialog` (`DialogSpec`, `DialogArg`, `DialogAvailability`, `DialogProbe`, `DialogResult`,
  `DialogStatus`, `DialogUnavailableReason`), the injected command runner `CommandRunner`, `CommandOutcome` and
  `CancelSignal`, and the real `SubprocessRunner`.
