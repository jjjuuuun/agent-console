import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import type { Extension } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { tags as t } from "@lezer/highlight";

/**
 * `--ac-*` 토큰만 참조하는 테마. 다크/라이트 전환은 CSS 변수가 처리하므로 `dark` 플래그와 무관하게 동작한다.
 * 토큰이 없는 환경(다른 프로젝트)을 위해 var() 폴백을 둔다.
 */
export const editorTheme: Extension = EditorView.theme({
  "&": {
    color: "var(--ac-text, #e6e9ef)",
    backgroundColor: "var(--ac-surface-1, #161a20)",
    border: "1px solid var(--ac-border, #2e3541)",
    borderRadius: "var(--ac-radius-md, 6px)",
    fontSize: "var(--ac-text-code, 12.5px)",
    height: "100%",
  },
  "&.cm-focused": { outline: "2px solid var(--ac-accent, #6aa6ff)", outlineOffset: "-1px" },
  ".cm-scroller": {
    overflow: "auto",
    fontFamily: "var(--ac-font-mono, ui-monospace, 'Malgun Gothic', monospace)",
    lineHeight: "var(--ac-lh-code, 1.5)",
  },
  ".cm-content": { caretColor: "var(--ac-accent, #6aa6ff)", wordBreak: "keep-all", overflowWrap: "break-word" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--ac-accent, #6aa6ff)" },
  ".cm-gutters": {
    backgroundColor: "var(--ac-surface-2, #1d222a)",
    color: "var(--ac-text-subtle, #9099a9)",
    borderRight: "1px solid var(--ac-border, #2e3541)",
  },
  ".cm-activeLine": { backgroundColor: "color-mix(in srgb, var(--ac-accent, #6aa6ff) 8%, transparent)" },
  ".cm-activeLineGutter": { backgroundColor: "var(--ac-surface-3, #262c36)" },
  // 비교 보기에서 접힌 변경 없는 구간 줄(@codemirror/merge 기본은 흰 바탕 그라데이션이라 다크에서 튄다)
  ".cm-collapsedLines": {
    backgroundImage: "none",
    backgroundColor: "var(--ac-surface-3, #262c36)",
    color: "var(--ac-text-muted, #a3acba)",
  },
  "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection": {
    backgroundColor: "color-mix(in srgb, var(--ac-accent, #6aa6ff) 30%, transparent)",
  },
});

const highlight = HighlightStyle.define([
  { tag: [t.heading, t.strong], fontWeight: "600", color: "var(--ac-accent, #6aa6ff)" },
  { tag: t.emphasis, fontStyle: "italic" },
  { tag: [t.keyword, t.tagName, t.propertyName], color: "var(--ac-info, #6aa6ff)" },
  { tag: [t.string, t.attributeValue], color: "var(--ac-success, #3fb871)" },
  { tag: [t.number, t.bool, t.null, t.atom], color: "var(--ac-warning, #f0b429)" },
  { tag: [t.link, t.url], color: "var(--ac-accent, #6aa6ff)", textDecoration: "underline" },
  { tag: [t.comment, t.meta, t.processingInstruction, t.quote], color: "var(--ac-text-muted, #a3acba)" },
  { tag: t.invalid, color: "var(--ac-danger, #f26b6b)" },
]);

export const editorHighlight: Extension = syntaxHighlighting(highlight);
