# Changelog: @agent-console/trace-view

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [Unreleased]
- Plural (0.2.1): new message `tokensTotalOne` (singular form, used when the count is 1).
- Message data (0.2.0): moved the default messages to `src/locales/ko.json` (`defaultTraceMessages` is still Korean)
  and added `en.json`. Subpath exports `./locales/ko` and `./locales/en` (`messages={en}` for English). Added tests that
  check keys and placeholders match and that the source has no Korean strings. The public API only grew, and the
  default behavior is the same.
- Separate session badges and task previews for call spans (`call`/`invoked_by`), names with the iteration ` #n` and
  the call number, child run group rows (controlled expand and collapse with `expandedGroupIds`/`onGroupToggle`,
  `onOpenChildRun`, `groupBadgeFor`), and link chips `linkBadgeFor`. The `flattenRows` options `runId` and
  `expandedGroups`, and the public `spanOrdinals`, `defaultExpandedGroups`, `isCallSpan` and `isChildRunSpan`. Traces
  without the new fields look the same as before.

## [0.1.0]
- First release.
