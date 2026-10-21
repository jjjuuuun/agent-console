/** @agent-console/text-editor 공개 API. CodeMirror 6 기반 문서 편집기. 다른 @agent-console 패키지에 의존하지 않는다. */
export const PACKAGE_NAME = "@agent-console/text-editor" as const;

export { TextEditor } from "./TextEditor";
export type { TextEditorMessages, TextEditorProps, TextEditorStatus } from "./TextEditor";
export { jsonParseError, resolveLanguage } from "./languages";
export type { EditorLanguage } from "./languages";
export { TextDiff } from "./TextDiff";
export type { TextDiffMessages, TextDiffMode, TextDiffProps } from "./TextDiff";
