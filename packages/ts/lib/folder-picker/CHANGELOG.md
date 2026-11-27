# Changelog: @agent-console/folder-picker

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [Unreleased] (pick-first layout)
- Fix: the primary button (`.ac-fp-btn[data-variant="primary"]`) showed the light neutral hover background under white text on hover (contrast 1.12:1). It now has its own hover rule using `--ac-accent-hover`, so text contrast stays at least 4.5:1 in light and dark themes.
- Messages (0.2.0): moved the default messages to `src/locales/ko.json` (`defaultMessages` is still the Korean table) and added `en.json`. New subpath exports `./locales/ko` and `./locales/en` (`messages={en}` for English). Added tests for matching keys and placeholders and for no Korean string literals in the source. The public API only grew and the default behavior is the same.
- `FolderPicker`: the layout is now "pick first". [Select folder…] is the primary button with the first focus, followed by the selected folder box and a collapsed "Enter the path directly". New props `capabilities`, `onPickNative(initial, signal)`, `configDir`, `autoFocus`, `pickRef`, `defaultManualOpen`, `onSelectPhaseChange`, `waitingEscapeMs`, `cancelledNoticeMs` and `copy`.
- Pick states `picked`, `cancelled`, `unavailable`, `busy`, `timeout` and `failed`, plus waiting (`waiting`). `unavailable` and `failed` switch to browsing automatically, and Esc while waiting cancels the pick.
- New check states `manifest_found` and `manifest_invalid` (the optional field `FolderCheckData.manifest`; hidden when absent). `ok_readonly` uses the `{dir}` message when `configDir` is given.
- New exports: `SelectedFolder` and `FolderPickStatusLine`, and the types `FolderCapabilitiesData`, `FolderPickFn`, `FolderPickOutcome`, `FolderPickStatus`, `FolderManifestInfo` and `FolderSelectPhase`. `useFolderCheck` gained `checkNow` and `adopt`.
- **Breaking changes** (no consuming app; 0.1.0 was not used anywhere): (1) the "Browse…" button became [Select folder…], and the input field is collapsed by default (`defaultManualOpen` expands it). (2) The input field label is `folder.path.input_label` ("Folder path"), and `folder.path.label` is the title of the selection box. (3) `folder.path.help` no longer says to browse. (4) `inputRef` is attached only while direct input is expanded. (5) `FolderPathInput` gained the `label` and `showResult` props (the defaults keep the previous behavior).
- Added the tokens it uses, `--ac-pick-box-min-h` and `--ac-pick-btn-h`, to `@agent-console/ui` tokens.css.

## [0.1.0]
- First release.
