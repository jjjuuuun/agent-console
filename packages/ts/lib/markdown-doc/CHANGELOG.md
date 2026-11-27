# Changelog: @agent-console/markdown-doc

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [Unreleased]
- Messages (0.2.0): moved the default messages to `src/locales/ko.json` (`defaultMessages` is still the Korean table) and added `en.json`. New subpath exports `./locales/ko` and `./locales/en` (`messages={en}`), plus `flattenMessageTree` and the `MessageTree` type (`wiki-view` and `sdd-view` reuse them). Added tests for matching keys and placeholders and for no Korean string literals in the source. The public API only grew and the default behavior is the same.
- Added `DocumentEditorHandle.insertAtCursor(text)`.
- `MarkdownPreview`: passes `renderLink` through context and builds the component table only once. Previously link elements were removed and recreated every time the parent re-rendered, so they lost focus and hover.
- `styles.css`: added `line-height` to `.ac-md-editor-status` (for the line height pairing check).

## [0.1.0]
- First release. Moved `DocumentEditor` (with compare, go to line and the external change banner), `ToneChip`, `DocumentStateChip` and `RulesSourceBadge` from `sdd-view`. The issue type is `DocumentIssue` (optional `line`), based on the contract `Issue`, so `SpecIssue` fits too. New `MarkdownPreview` (hooks `renderLink`, `transformSource` and `urlTransform`) and `DocumentEditor.previewHooks`.
