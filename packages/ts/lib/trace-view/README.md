# @agent-console/trace-view

A **presentation** package for the delegation flow (`Trace`) timeline: a tree on the left and time bars on the right. Data and callbacks are props, and text comes from `messages`.
It imports no other TS package (only `@agent-console/contracts` types).

## Minimal usage
This block matches `test/readme.test.ts`, and the test actually runs it (`pnpm pkg-lint` checks that they match).

```ts readme
import { formatDuration } from "@agent-console/trace-view";

const text = formatDuration(125, { s: "s", m: "m", h: "h" });
```

## Text and language
The default text is Korean (`src/locales/ko.json`, `defaultTraceMessages`), and an English bundle ships alongside it. There is no dependency such as i18next. Placeholders are `{name}`, filled by a pure function inside the package.
`ko` and `en` have the same keys and placeholders (`test/locales.test.ts` checks this). To use English, pass one bundle as `messages`.

```tsx
import en from "@agent-console/trace-view/locales/en";

<TraceTimeline trace={trace} messages={en} />
```
The Korean bundle is `@agent-console/trace-view/locales/ko`. To change only part of a bundle, spread it and override, as in `messages={{ ...en, empty: "…" }}`. For a new language, build an object with the same keys and pass it in. The component source contains no Korean strings (the same test checks this).

## Styles
```ts
import "@agent-console/ui/tokens.css";
import "@agent-console/trace-view/styles.css";
```

## Another usage example
```tsx
<TraceTimeline trace={trace} now={nowSec} running labelFor={(s) => ({ title: nodeLabel(s.node_id) })}
  methodBadgeFor={(s) => ({ text: methodTitle(s) })} selectedSpanId={sel} onSelect={setSel} />
```

## Rules
- A parent-child relation exists only when the span that `parent_id` points to is present (no inference from timing) → an indented row plus "Same session". A top-level span gets "Separate session", plus the handoff arrow from `trace.links` and an `order` chip. The session is decided by comparing `session_id`, or by whether a parent exists when there is none.
- A wait for the user is a span that has an `interaction_id` (a bar with waiting hatching). Kind strings are not compared, so an unknown `kind` is an ordinary row.
- The text of the method badge comes from `methodBadgeFor` (the app passes the edge type or delegation strategy `title`). `now` is epoch seconds.
- Keyboard: `↑↓←→ Enter Home End + -`. The accessible name is "{name}, {method}, {status}, {duration}".

## Calls, iterations, and child runs
Kind ids are not compared; decisions use only span fields.
- A call span (a span with `call` or `invoked_by`): an indented row under the delegator span, always with a "Separate session" badge, and the task preview (`task_preview`) on one line inside the bar.
- When the same node has two or more iterations (`iteration`; or one or more), ` #n` follows the name; when it has two or more calls, ` · call n` follows (the number is the value plus 1, and the text is `messages.iterationSuffix` and `callSuffix`). See `spanOrdinals`.
- A child run (`span.run_id` differs from `trace.run_id`) is gathered under one group row per run (`runId` in `flattenRows`). The group sits under the parent span that the run's topmost span points to, and descendant runs nest inside the parent group. Group row: `Enter` or a click toggles collapse, and `Ctrl+Enter` or [Open] calls `onOpenChildRun(runId)`.
- Collapse can be controlled: `expandedGroupIds` plus `onGroupToggle(runId, expanded)`. When omitted, it starts from `defaultExpandedGroups` (expanded if any span is unfinished, collapsed once finished) and the view keeps the user's choices.
- App injection: `groupBadgeFor(group)` (the group title, subtitle, and badge) and `linkBadgeFor(link)` (the chip on the arrow between spans, for example `↻` for a loop edge).

## Row layout
- A row is one CSS grid (label column / bar column / number columns). An element never leaves its own column, and hover and selection change only the background color. Container queries hide the subtitle, tokens, and link chip in narrow panels (under 560) and under 640.
- The method and the session are icons, not text chips: the method is `MethodBadge.iconName` (the edge type's `ui_hints.icon`), and the session is a dashed circle (same) or a solid circle (separate). The text goes in `aria-label` and `title`. Turning on `showMethodText` (with `onShowMethodTextChange`) shows the text in place of the subtitle.
- App injection (the package does not import `ui`): `renderIcon(name, size)`, `renderTooltip(content, children)` (default: a glyph and `title`), and `labelWidth` (px, clamped to 200-360).
- Attributes for machine checks: `data-trace-{toggle,order,label,icons,open,bar,link,tail}`.

## Testing
`pnpm test`
