/**
 * @agent-console/trace-view 공개 API. 위임 흐름(`Trace`) 타임라인. 표현 전용: 데이터와 콜백은 props.
 * 스타일: `@agent-console/ui/tokens.css`를 먼저, 이어서 `@agent-console/trace-view/styles.css`를 한 번 불러온다.
 */
export const PACKAGE_NAME = "@agent-console/trace-view" as const;

export { TraceTimeline } from "./TraceTimeline";
export type { GroupBadge, LinkBadge, MethodBadge, SpanLabel, TraceTimelineProps } from "./TraceTimeline";
export { GROUP_SPAN_KIND, computeTimeScale, defaultExpandedGroups, flattenRows, compactCount, formatDuration, formatTailDuration, groupSpanId, isCallSpan, isChildRunSpan, isSameSession, isUserWait, niceTicks, spanOrdinals, visibleHandoffs } from "./layout";
export type { FlattenOptions, Handoff, SpanOrdinal, TimeScale, TraceGroupInfo, TraceRow } from "./layout";
export { defaultTraceMessages } from "./messages";
export type { TraceMessages } from "./messages";
