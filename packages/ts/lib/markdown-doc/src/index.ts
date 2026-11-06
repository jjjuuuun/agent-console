/**
 * @agent-console/markdown-doc — 마크다운 문서 편집·미리보기와 작은 공용 표현 부품.
 * `DocumentEditor`(text-editor + 미리보기 + 비교 + 충돌·외부 변경·없음·읽기 전용 띠)·`MarkdownPreview`(react-markdown + GFM, 링크·원문 훅)
 * ·`ToneChip`/`DocumentStateChip`(상태·톤 칩)·`RulesSourceBadge`(값 출처 배지)와 순수 함수.
 * API·저장소·api-client를 모른다(데이터와 콜백은 props). 상태·톤·출처 이름은 코드에 없고 전부 데이터다.
 */
export { DocumentEditor, EDITOR_VIEW_MODES } from "./DocumentEditor";
export type { DocumentEditorHandle, DocumentEditorProps, DocumentIssue, EditorViewMode } from "./DocumentEditor";
export { MarkdownPreview } from "./MarkdownPreview";
export type { MarkdownPreviewProps } from "./MarkdownPreview";
export { DocumentStateChip, ToneChip } from "./ToneChip";
export type { DocumentStateChipProps, ToneChipProps } from "./ToneChip";
export { RulesSourceBadge } from "./RulesSourceBadge";
export type { RulesSourceBadgeProps } from "./RulesSourceBadge";
export { NEUTRAL_TONE, statusTone, toneAttr } from "./tone";
export type { StatusLike, ToneDisplay } from "./tone";
export { defaultMessages, formatMessage, messageOr, resolveMessages } from "./messages";
export type { MarkdownDocMessageKey, MarkdownDocMessages } from "./messages";
