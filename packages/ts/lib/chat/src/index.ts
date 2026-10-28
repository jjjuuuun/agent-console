/**
 * @agent-console/chat 공개 API. 채팅 표현 전용: 데이터와 콜백은 props로 받고 네트워크·라우터·저장소를 모른다.
 * 스타일: 앱이 `@agent-console/ui/tokens.css`를 먼저, 이어서 `@agent-console/chat/styles.css`를 한 번 불러온다.
 */
export const PACKAGE_NAME = "@agent-console/chat" as const;

// 메시지 영역 (1R.19)
export { MessageList, isNearBottom } from "./messages/MessageList";
export type { MessageListProps } from "./messages/MessageList";
export { TurnView } from "./messages/TurnView";
export type { TurnViewProps } from "./messages/TurnView";
export { ReplyGroup } from "./messages/ReplyGroup";
export type { ReplyGroupProps } from "./messages/ReplyGroup";
export { ProgressStrip } from "./messages/ProgressStrip";
export type { ProgressStripProps } from "./messages/ProgressStrip";
export { Markdown, closeOpenFence, isSafeHref } from "./messages/Markdown";
export type { MarkdownProps } from "./messages/Markdown";
export { defaultChatMessages } from "./messages/messages";
export type { ChatMessages } from "./messages/messages";
export { isIntermediate, isReplyExpanded, normalizeReplyDisplay, selectVisibleReplies, sortReplies } from "./messages/replyLogic";
export { currentStepLabel, flattenSteps, visibleSteps } from "./messages/progressLogic";
export type { FlatStep } from "./messages/progressLogic";
export type { AgentView, AvatarSpec, StepAvatar, ProgressChild, ProgressStep, QueuedRow, ReplyDisplay, ReplyItem } from "./messages/types";

// 입력창 (1R.19 + 답변 모드 1R.31)
export { ANSWER_MODES, ANSWER_TOGGLE_SHORTCUT, Composer, defaultComposerMessages, resolveSendKey } from "./composer/Composer";
export type { AnswerMode, ComposerHandle, ComposerMessages, ComposerProps } from "./composer/Composer";

// 상호작용 카드 (1R.31)
export { InteractionCard, cardKind } from "./interaction/InteractionCard";
export type { InteractionCardProps } from "./interaction/InteractionCard";
export { answerCardIds, answerViaOf, resolveAnswerSurface } from "./interaction/answerSurface";
export type { AnswerSurface, AnswerSurfaceContext, ResolveAnswerSurfaceInput } from "./interaction/answerSurface";
export { defaultRenderers } from "./interaction/renderers";
export { ChoicesRenderer, parseQuestions } from "./interaction/ChoicesRenderer";
export { PermissionRenderer, PERMISSION_DECISIONS, decisionValues } from "./interaction/PermissionRenderer";
export { ReviewRenderer, parseDecisions } from "./interaction/ReviewRenderer";
export { FallbackRenderer } from "./interaction/FallbackRenderer";
export { DECISION_COLOR_TOKENS, decisionButtonStyle, isDecisionColorToken } from "./interaction/decisionStyle";
export { defaultInteractionMessages } from "./interaction/messages";
export type { InteractionMessages } from "./interaction/messages";
export type { FallbackArgs, FieldError, RenderEditor, RendererComponent, RendererProps } from "./interaction/types";
export { formatCountdown, formatSeconds, showDuration } from "./shared/util";
