# Changelog: @agent-console/chat

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [Unreleased]
- Duration units (0.2.2): the English minute unit is "m" (was "min"), so waits read "4m 14s" like the app's `duration` formatter.
- Locale (0.2.1): `MessageList` and `TurnView` take an optional `locale` (BCP 47, normally the display language) for
  the turn time tooltip and the token count; the default is `"en-US"` instead of the host locale.
- Message data (0.2.0): moved the default messages to `src/locales/ko.json` (`chat`, `interaction`, `composer`,
  `markdown`; `defaultChatMessages`, `defaultInteractionMessages` and `defaultComposerMessages` are still Korean) and
  added `en.json`. Subpath exports `./locales/ko` and `./locales/en`, and the public `ChatLocale` type. Moved the
  hardcoded Korean defaults inside `Composer`, `Markdown` and `formatSeconds` into the ko bundle (same behavior and
  default messages). Added tests that check keys and placeholders match and that the source has no Korean strings.
- A single answer box for questions: `resolveAnswerSurface`, `answerViaOf` and `answerCardIds` are public.
  `InteractionCard` has `answerVia`, `answerPaused` and `onDraftChange`, and `RendererProps` has `readOnlyInput` and
  `onDraftChange` (optional renderers and the built-in fallback follow them). The `Composer` answer mode banner is a
  two-way toggle (`Alt+Shift+A`, `aria-describedby`, announced on switch), `placeholderHint` was added, and
  `pendingHint` is kept for compatibility (deprecated). Message keys: `answerPlaceholder`, `answer` (string),
  `answeringTo`, `switchToMessage`, `messageMode` and `switchToAnswer` of `ComposerMessages` moved to the `answer.*`
  group and were removed, and `InteractionMessages.answer` was added. Ctrl+Shift+Enter only calls `onSendAsMessage`
  (nothing happens without it).
- Chat turn redesign: inline styles of the message area (`MessageList`, `TurnView`, `ReplyGroup`, `ProgressStrip`)
  moved to `ac-chat-*` classes in `styles.css` (tokens only). Your messages are right-aligned bubbles (no "me" label;
  time, copy and resend icon buttons shown on hover or focus). Progress is a one-line summary of the current step plus
  a tree when expanded, and durations under one second are hidden (`showDuration` is public). The child run link is a
  single icon, the run detail link in the reply header was removed (one per turn in the footer), and the final reply
  has no card. Turns have `tabindex=0` and `↑↓`/`C`/`R`/`Alt+Enter`. Added `formatTime` to `TurnView` and
  `MessageList` and the messages `yourMessage`, `copyReply`, `progressNow`, `progressSummaryDuration` and
  `childOpenTip`; `progressSummary` no longer uses `{duration}`. The inline styles of interaction cards and the message
  box were not moved in this change.
- Nested progress lines: `ProgressStep` gained `indent` (an integer), `badge`, `iterationLabel`, `callLabel`, `tone`,
  `child`, `children` and `hint`, chip expand and collapse (`expandedStepKeys`/`onStepToggle`), child run links
  (`onOpenChild`/`onOpenChildRun`), and step counts including descendants with a summary beyond eight. `flattenSteps`,
  `visibleSteps` and `currentStepLabel` are public. Existing steps (`indent` 0|1, no new fields) look the same.

## [0.1.0]
- First release.
