# Changelog: @agent-console/sdd-view

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [Unreleased]
- Layout (0.2.1): the spec list updated column is 112px (was 72px, 64px when narrow) so English relative times such as "15 min. ago" fit; the task table ready column is 112px (`--ac-sdd-col-ready`, was 80px) and its chip does not shrink, so the English "Blocked" fits.
- Messages (0.2.0): moved the default messages to `src/locales/ko.json` (`defaultMessages` is still the Korean table) and added `en.json`. New subpath exports `./locales/ko` and `./locales/en` (`messages={en}`). Depends on `@agent-console/markdown-doc` `^0.2.0` for `flattenMessageTree`. Added tests for matching keys and placeholders and for no Korean string literals in the source. The public API only grew and the default behavior is the same.
- `TraceMatrix`: added `showGapsToggle` (default true). When the app puts the same switch in its toolbar, it turns this off and passes only `onlyGaps` (removes the duplicate "gaps only" checkbox inside the table).
- Moved `DocumentEditor`, `ToneChip`, `DocumentStateChip` and `RulesSourceBadge`, plus `toneAttr`, `statusTone`, `formatMessage` and `messageOr`, to `@agent-console/markdown-doc` and re-exported them under the same names (public API unchanged). The `editor.*` and `source.*` message keys moved to the `defaultMessages` of markdown-doc, and overriding through the `messages` prop still works. Chip and editor CSS is in the markdown-doc `styles.css` (classes `ac-sdd-chip*`, `ac-sdd-editor*` and `ac-sdd-source` → `ac-md-*`), which `styles.css` imports with @import. Removed text-editor, react-markdown and remark-gfm from the dependencies and added markdown-doc.
- `TaskTable`: row selection (`selectable`), overriding phase collapse plus a default (phases where everything is done are collapsed), inline notices under rows (`renderRowNotice`), row menus (`rowMenuItems`) and the handle `TaskTableHandle`. Existing props are unchanged (storing selection and collapse is up to the caller).

## [0.1.0]
- First release.
