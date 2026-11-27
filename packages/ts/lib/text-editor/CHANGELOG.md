# Changelog: @agent-console/text-editor

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [Unreleased]
- Collapsed ranges in the diff view: fixed a lost tab stop because `@codemirror/merge` 6.13 sets only `role=button`
  without a tabindex (role and tabindex are now checked separately).
- Added `TextDiffMessagesProvider` (`@agent-console/text-editor/messages`) and `TextDiffMessages.before` and `after`:
  the default diff view messages are injected once at the app root.
- Added `TextEditorHandle.insertAtCursor(text)` (for the wiki link insertion): replaces the selection with the text and
  moves the cursor after it. Returns false when read-only.

## [0.1.0]
- First release.
