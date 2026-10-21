/** 독립 위임·반복·조건·중첩 팀 화면 조각(5R.17). 팀 구성 편집기·실행 상세·채팅이 함께 쓰는 순수 함수·위젯·훅. */
export { ConditionList, type ConditionError, type ConditionListProps, type OperatorsState } from "./ConditionList";
export { ConditionListField, UnknownWidgetField, pathExamples, pathTitlesOf } from "./ConditionListField";
export { ConfigIssuesProvider, configRelativePath, useConfigIssuesUnder, type ConfigIssue } from "./ConfigIssuesContext";
export { CONDITION_WIDGET_NAME, CONFIG_FIELDS, CONFIG_WIDGETS } from "./configWidgets";
export {
  actualPreview,
  conditionShape,
  forbidsValue,
  formatConditionValue,
  mapConditionOutcome,
  summarizeConditions,
  valueKindOf,
  type ConditionItemOutcomeView,
  type ConditionOutcomeView,
  type ConditionSummary,
} from "./conditions";
export { DEFAULT_TEAM_CONVENTIONS, numberAt, stringAt, type TeamConventions } from "./conventions";
export { resolveCycleLimit, type CycleLimit, type CycleLimitSource } from "./cycleLimit";
export { deriveAllEdgeChips, deriveEdgeChips, edgeStrategyIds, effectiveStrategyId, type EdgeChipContext } from "./edgeChips";
export { buildBindSummary, deriveBindSummaries, nestedDefinitionList, nestedInfoOf, type BindSummaryContext, type NestedInfo } from "./bindSummary";
export { conditionPayloadOf, isChildRunNotice, parseDelegationEvent, summarizeDelegationEvent, type DelegationEventView, type EventSummary, type EventSummaryContext } from "./eventSummaryMap";
export { DelegationSettings, delegatorStrategies, type DelegationSettingsProps } from "./DelegationSettings";
export { shortRunId } from "./ids";
export { retryFocus, type RetryFocusOptions } from "./focusRetry";
export { delegationMessages } from "./messages";
export { displayNumber, formatRunOrdinal, type OrdinalKind } from "./ordinal";
export { useRenderIcon } from "./useRenderIcon";
export { useConditionOperators, type ConditionOperatorsResult } from "./useConditionOperators";
export { UNKNOWN_WIDGET_FIELD, bridgeWidgetUi, chipsFromWidgets, widgetFieldsOf, type ConfigWidget, type WidgetField, type WidgetRegistry, type WidgetSummaryContext } from "./widgetRegistry";
import "./delegation.css";
