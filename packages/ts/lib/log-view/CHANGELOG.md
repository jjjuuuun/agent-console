# Changelog: @agent-console/log-view

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [Unreleased]
- Locale (0.2.1): `Formatters` gains `fullTime(epochSeconds)` (tooltip time, default `fullTimeTitle`);
  `fullTimeTitle(epochSeconds, locale = "en-US")` takes a locale instead of the host locale. `LogEventDetail`,
  `SessionList` and `formatEventTime` use `formatters.fullTime`, so an app that injects `formatters` (duration, number,
  fullTime) localizes every number and time on screen.
- Message data (0.2.0): moved the default messages to `src/locales/ko.json` (`messages` and `builtinWidgets`;
  `defaultLogViewMessages` and `builtinWidgets` are still Korean) and added `en.json`. Subpath exports `./locales/ko`
  and `./locales/en`, and the public `createBuiltinWidgets(texts)`, `BuiltinWidgetTexts` and `LogViewLocale` (build the
  built-in widget titles and descriptions per language). Moved the Korean default units of `formatDurationMs` into the
  ko bundle. Added tests that check keys and placeholders match and that the source has no Korean strings.
- Layout options that simplify the screen (same features, the default layout changes).
  `LogFilterBar`: `savedPlacement` (`menu` by default = saved filters in a section at the bottom of the [+ Filter]
  menu; `button` = the previous [★ ▾] button). Added the message `saveCurrentFilter`.
  `PlaybackBar`: `settingsPlacement` (`popover` by default = speed and gap skipping inside a [Playback settings ▾]
  popover, with "2×" next to the button when the speed is not 1×; `inline` = the previous layout). Added the messages
  `playSettings` and `playSettingsShort`.
  `CategoryChips`: selected chips stay visible while collapsed, and the collapse button shows the hidden count `(+n)`.
- Additional APIs so the app does not have to read the DOM (all optional; existing usage keeps working).
  `LogEventTable`: `ref` (`LogEventTableHandle`: `scrollToUid`, `focus`) and `onActivate(uid)` (Enter).
  `LogEventDetail`: `activeTab` and `onActiveTabChange` (controlled), and `ref` (`LogEventDetailHandle`:
  `selectTabAt`, `focusTab`, `visibleTabs`).
  `SessionList`: `onActiveChange(id|null)` (the keyboard cursor row).
- dependency-cruiser `log-view-contracts-types-only`: only `import type` is allowed from contracts.

## [0.1.0]
- First release: event table (virtual scrolling), filter bar, category chips, event detail, session list, playback
  bar, lane strip, handoff matrix, dashboard grid, widget editor, template picker and color slot picker; a widget
  registry (`builtinWidgets`: metric, bar, line, table); a lazily loaded recharts chart adapter; the playback hook
  `usePlayback`; and pure functions (sorting, truncation, grouping, URL parameter splitting, layout, retention).
- The only internal dependency is the types of `@agent-console/contracts`. New external dependencies:
  `@tanstack/react-virtual`, `recharts` and `react-is`.
