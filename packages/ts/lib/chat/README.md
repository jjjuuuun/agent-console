# @agent-console/chat

A chat **presentation** package: the message list, the message box, and the interaction card. It knows nothing about networking, routers, or storage.
Data and callbacks come in as props, and text comes in as `messages` (a partial object). It imports no other TS package (only `@agent-console/contracts` types).

## Minimal usage
This block matches `test/readme.test.ts`, and the test actually runs it (`pnpm pkg-lint` checks that they match).

```ts readme
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Composer } from "@agent-console/chat";

const html = renderToStaticMarkup(createElement(Composer, { value: "안녕", onChange: () => {}, onSend: () => {} }));
```

## Installation and styles
Add it as a workspace dependency (React 19 is required). Once, at the app entry point:
```ts
import "@agent-console/ui/tokens.css";
import "@agent-console/chat/styles.css";
```
All colors and spacing are `--ac-*` tokens, and the package relies only on the class conventions `.ac-btn` for buttons and `.ac-status-box[data-status]` for status.

## Another usage example
```tsx
<MessageList turns={turns} replyDisplay="separate" agentView={(id) => ({ name: id })}
  renderInteraction={(i, d) => <InteractionCard interaction={i} descriptor={d} onRespond={respond} now={nowSec} />} />
<Composer value={text} onChange={setText} onSend={send} />
```

## Public API
- `MessageList` / `TurnView` / `ReplyGroup` / `ProgressStrip` / `Markdown`: reply display `separate | merged | final_only` (an unknown value is treated as `separate`), collapsing of intermediate results, a streaming caret, queue rows (a `held` item gets a paused chip plus [Run], [Cancel], and [Move to message box], and Enter or Delete on a focused row), a resume chip on a `resumed_from` turn (a turn that resumes the turn right before it does not draw the same user message again), a notice the app can place above the turn footer through `renderTurnNotice` (such as the resume banner for an interrupted turn), the progress strip (the app passes the method label), and following the bottom only while the view is pinned there.
- `Composer`: controlled. The send key (`enter` by default, or `ctrl_enter`), and **Enter is ignored during and right after Korean IME composition**. Answer mode: `answerTarget` (plus `describedBy`), `answerMode`, `onSwitchToMessage`, `onSwitchToAnswer`, and `onSendAsMessage` (Ctrl+Shift+Enter, which does not change the mode). The banner is a two-way toggle `[Answer | New message]` (`radiogroup`, `Alt+Shift+A`). The hint shown when not in answer mode is `placeholderHint`.
- `InteractionCard`: the renderer is looked up by the descriptor's `ui_hints.renderer` name in `defaultRenderers` (`choices`, `permission`, `review`) plus the `renderers` prop. If it is not in the table, `renderFallback` is used (the app injects a SchemaForm), and without that, a built-in JSON fallback. Kind ids are not used. With `answerVia="external"`, the card draws only the question and the hint, with no input element or submit button (`RendererProps.readOnlyInput`). Whether the answer field is the message box or the card is decided by the pure function `resolveAnswerSurface` (it looks only at the descriptor fields and the shape of the payload and response_schema). The card state changes only through the `interaction` prop (no optimistic updates). If `onRespond` rejects, the error is shown in the error area.
- A new renderer: a `RendererComponent` (it receives `RendererProps` and calls `onSubmit(response)`, optionally with a static `summarize`).
- Decision button appearance: `ui_hints{color, icon, dashed}`. `color` accepts only the token names listed in `tokens.md` 5.5 (`DECISION_COLOR_TOKENS`); anything else is ignored.
- `now` is injected as **epoch seconds** (the unit of the contract's `created_at`).

## Nested progress display
Optional fields of `ProgressStep` (all of them are data the app builds from events, and the component knows no kinds): `indent` (an integer of 0 or more; the screen shows at most 4 levels × `--ac-progress-indent`), `badge` ("Separate session" and the like), `iterationLabel` and `callLabel` ("Iteration 2" / "Call 2"), `tone: "warning"` (the glyph `▲` plus a border), `hint` (a tooltip), `child: {runId, href, nodeLabel, progress?}`, and `children`.
- A chip that has `children` collapses and expands from the chip body (`Enter` or `Space`, `aria-expanded`). It is collapsed by default, and a collapsed chip shows `Node 2/5` (only when `child.progress` is present) and `Now: …` (the running descendant). The child run link is a separate `external-link` icon link at the end of the row (`child.href`, `onOpenChild`).
- Control: `expandedStepKeys` plus `onStepToggle(key, expanded)`. When omitted, internal state keeps the user's choices.
- "N progress steps" and the rule for more than 8 (the latest 3 plus "…and N more steps") are based on the full list with descendants expanded (`flattenSteps`).
- The actual indentation of a descendant chip is `max(its own indent, parent indent + 1)`.
- `onOpenChildRun(runId)` on `TurnView` and `MessageList` receives the child run icon link.
- `locale` on `TurnView` and `MessageList` (BCP 47, normally the display language) sets the turn time tooltip and the token count format (default `"en-US"`); `formatTime` still sets the visible time text.

## Dependencies (what / why / alternatives)
- `react-markdown` + `remark-gfm`: Markdown display. It does not render raw HTML (text is escaped), allows only http(s) links, and shows images only as alt text. Writing our own parser would add a heavy security and maintenance burden, so we adopted this. Alternatives: `markdown-to-jsx`, `marked` + DOMPurify.

## Text and language
The default text is Korean (`src/locales/ko.json`), and an English bundle ships alongside it. There is no dependency such as i18next. Placeholders are `{name}`, filled by `fill()` inside the package.
Each component has its own `messages` prop, so the bundles are split by name: `chat` (`MessageList`, `TurnView`, `ReplyGroup`, `ProgressStrip`), `interaction` (`InteractionCard`), `composer` (`Composer`), and `markdown` (`Markdown`).
`ko` and `en` have the same keys and placeholders (`test/locales.test.ts` checks this). To use English, pick from the bundle and pass it in.

```tsx
import en from "@agent-console/chat/locales/en";

<MessageList turns={turns} replyDisplay="separate" agentView={agentView} messages={en.chat} />
<Composer value={text} onChange={setText} onSend={send} messages={en.composer} />
<InteractionCard interaction={i} descriptor={d} onRespond={respond} now={nowSec} messages={en.interaction} />
```
The Korean bundle is `@agent-console/chat/locales/ko` (`defaultChatMessages`, `defaultInteractionMessages`, and `defaultComposerMessages` stay Korean). To change only part of a bundle, override it as in `messages={{ ...en.chat, stop: "…" }}`. For a new language, build an object with the same keys (the `ChatLocale` type) and pass it in.
The component source contains no Korean strings (the same test checks this; only the sample data `fixtures.ts` is excluded). The default units of `formatSeconds` also come from the ko bundle.

## Testing
`pnpm test`
