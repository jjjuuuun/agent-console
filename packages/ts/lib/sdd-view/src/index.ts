/**
 * @agent-console/sdd-view — 스펙(SDD) 표현 컴포넌트.
 * 스펙 목록·문서 목록·문서 편집기(markdown-doc에서 다시 내보냄)·작업 표(가상 목록, 단계 묶음)·계획 그래프(@xyflow/react + elkjs, 읽기 전용)
 * ·추적 표·관문 안내와 순수 함수. API·저장소·api-client를 모른다(데이터와 콜백은 props).
 * 상태·문서 종류·단계·톤 이름은 코드에 없고 전부 props 데이터다.
 */
export { SpecList, SPEC_ROW_HEIGHT } from "./SpecList";
export type { SpecListProps, SpecSortColumn, SpecSortState } from "./SpecList";
export { DocumentNav } from "./DocumentNav";
export type { DocumentNavProps } from "./DocumentNav";
// 문서 편집기·칩·출처 배지는 @agent-console/markdown-doc로 옮겼고(7R.6) 같은 이름으로 다시 내보낸다(공개 API 그대로).
export { DocumentEditor, DocumentStateChip, EDITOR_VIEW_MODES, RulesSourceBadge, ToneChip } from "@agent-console/markdown-doc";
export type {
  DocumentEditorHandle,
  DocumentEditorProps,
  DocumentStateChipProps,
  EditorViewMode,
  RulesSourceBadgeProps,
  ToneChipProps,
} from "@agent-console/markdown-doc";
export { TaskTable, STAGE_ROW_HEIGHT, TASK_DETAIL_HEIGHT, TASK_ROW_HEIGHT } from "./TaskTable";
export type { TaskRowMenuItem, TaskTableHandle, TaskTableProps } from "./TaskTable";
export { TaskStatusMenu } from "./TaskStatusMenu";
export type { TaskStatusMenuProps } from "./TaskStatusMenu";
export { TaskFieldChips } from "./TaskFieldChips";
export type { TaskFieldChipsProps } from "./TaskFieldChips";
export { TaskRunChips } from "./TaskRunChips";
export type { TaskRunChipsProps } from "./TaskRunChips";
export { PlanGraph } from "./PlanGraph";
export type { PlanGraphProps } from "./PlanGraph";
export { PlanBundles } from "./PlanBundles";
export type { PlanBundlesProps } from "./PlanBundles";
export { TraceMatrix, TRACE_ROW_HEIGHT } from "./TraceMatrix";
export type { TraceMatrixProps } from "./TraceMatrix";
export { GateNotice } from "./GateNotice";
export type { GateNoticeProps } from "./GateNotice";

export { codeDisplay, NEUTRAL_TONE, statusTone, taskTitle, toneAttr } from "./display";
export type { CodeDisplayTable, StatusLike, ToneDisplay } from "./display";
export { flattenTaskRows, groupByStage, progressRatio } from "./stages";
export type { StageGroup, TaskRow } from "./stages";
export { applyPositions, createElkPlanLayout, PLAN_DEFAULTS, planBundles, planToFlow } from "./plan";
export type { PlanBundle, PlanEdgeModel, PlanFlow, PlanFlowOptions, PlanLayoutEngine, PlanLayoutInput, PlanNodeData, PlanNodeModel } from "./plan";
export { filterTraceRows, gapLabelKey, hasGaps, verificationLabelKey } from "./trace";
export { defaultMessages, formatMessage, messageOr, resolveMessages } from "./messages";
export type { SddViewMessageKey, SddViewMessages } from "./messages";
export { useVirtualRows } from "./hooks";
export type { UseVirtualRowsOptions } from "./hooks";
