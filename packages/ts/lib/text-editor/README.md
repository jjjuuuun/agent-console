# @agent-console/text-editor

`<TextEditor>`, a text editing component built on CodeMirror 6, with Markdown, HTML, and JSON syntax highlighting. It knows nothing about saving, resources, or the API (it is controlled).
It imports no other `@agent-console/*` package (react is a peer). Colors and fonts use `--ac-*` CSS variables (with fallbacks), so when `@agent-console/ui/tokens.css` is loaded, dark and light follow automatically.

## Minimal usage
This block matches `test/readme.test.ts`, and the test actually runs it (`pnpm pkg-lint` checks that they match).

```ts readme
import { jsonParseError } from "@agent-console/text-editor";

const broken = jsonParseError('{"a": ');
const fine = jsonParseError('{"a": 1}');
```

## Installation and usage
Inside the repository, `pnpm install` links the package. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`) (React 19 is required).

```tsx
import { TextEditor } from "@agent-console/text-editor";

<TextEditor
  value={text}
  onChange={setText}            // called only for user edits (including during IME composition); applying the value prop does not call it
  language="markdown"           // markdown | html | json | text (an unknown value = text)
  ariaLabel="Content editor"    // required
  onSave={save}                 // Ctrl/Cmd+S (ignored during composition)
  maxBytes={1_000_000}
  onTooLarge={(bytes) => warn(bytes)}   // read-only when exceeded
  onStatus={({ line, col, chars, parseError }) => setStatus(...)}   // for json, parseError (editing is not blocked)
  onCompositionChange={(composing) => setBusy(composing)} // true when IME composition starts, false when it ends
  handleRef={ref}               // ref.current.isComposing()
  height="fill"                 // a number of px, or fill the parent
  messages={{ tooLarge: "Read-only because it exceeds the size limit" }}
/>
```

## Behavior
- Korean IME: auto-completion and auto-closing brackets are not turned on, and the save shortcut is not handled during composition. When `value` equals the current document, the editor does not touch it, so the cursor and composition are kept.
- Composition state API: `onCompositionChange(composing)` is called only when the state changes at compositionstart or compositionend. `TextEditorHandle.isComposing()`, received through `handleRef`, returns the same value. Consumers that want to defer side work such as checking or saving during composition (Settings › Architecture map, the memory editor) use it. `onChange` is called during composition as well.
- `TextEditorHandle.goToLine(line)`: moves the cursor to a line counted from 1 and scrolls it to the center (a line out of range goes to the first or last line, and it returns false when there is no editor). The caller builds the go-to-line UI and shortcut.
- The Tab key indents by 2 spaces (press `Esc` and then `Tab` to leave the editor). Line numbers are shown, and line wrapping is on by default (`lineWrap`).
- The editor element carries `data-ac-editable`, so the app-wide single-key shortcut handler can ignore it.
- Public API: `TextEditor`, `resolveLanguage(name)`, `jsonParseError(text)`, and the types `TextEditorHandle`, `TextEditorProps`, `TextEditorStatus`, `TextEditorMessages`, and `EditorLanguage`.

## `<TextDiff>` — read-only text comparison

```tsx
import { TextDiff } from "@agent-console/text-editor";

<TextDiff
  before={oldText}
  after={newText}
  language="markdown"
  ariaLabel="Compare SKILL.md"
  mode="auto"            // split (side by side) | unified | auto (unified when the width is below unifiedBelow (900px))
  context={3}            // lines kept before and after when collapsing an unchanged section (negative = do not collapse)
  messages={{ unchangedLines: "$ unchanged lines", split: "Side by side", unified: "Unified", toolbar: "View mode" }}
/>
```
- It takes only two strings (it knows nothing about saving or the API). `F3` and `Shift+F3` go to the next and previous change block (when the editor has focus). Line numbers and `--ac-font-mono` are used.
- The mode buttons in the toolbar (`showToolbar`) use `aria-pressed`. A collapsed section is a click widget from `@codemirror/merge` (it cannot be expanded with the keyboard; use `context={-1}` to avoid collapsing).
- Public API additions: `TextDiff` and the types `TextDiffProps`, `TextDiffMessages`, and `TextDiffMode`.
- The default text is English. An app places `TextDiffMessagesProvider` (in the light subpath `@agent-console/text-editor/messages`, which does not pull in CodeMirror) once at the root to inject text in its own language. An individual `messages` prop takes priority.

## Dependencies (what / why / alternatives)
- `@codemirror/state`, `view`, `commands`, and `language`: the editor core — light, with mature IME handling. Alternatives: Monaco (heavy), a textarea (lacks syntax highlighting and extensions).
- `@codemirror/lang-markdown`, `lang-html`, and `lang-json`: per-language syntax highlighting. Alternative: hand-written regex highlighting (a maintenance burden).
- `@codemirror/merge` (MIT): `TextDiff`'s side-by-side (`MergeView`) and unified (`unifiedMergeView`) comparison, folding of unchanged sections, and jumping to the next change. It is part of the CodeMirror family we already use, so the theme and language extensions are shared as they are. Alternatives: `diff2html` or `react-diff-viewer` (separate renderers that would need theme, IME, and accessibility rework), or our own LCS diff (a maintenance burden).
- `@lezer/highlight`: a highlight style that maps token tags to `--ac-*` colors. Alternative: the default highlighting (not connected to tokens or the theme).

## Testing
`pnpm test` — `TextDiff` (side by side, unified, switching, folding, updating), value display, telling `onChange` apart, readOnly, maxBytes, Ctrl+S, IME (composition), no auto-closing brackets, and onStatus.
