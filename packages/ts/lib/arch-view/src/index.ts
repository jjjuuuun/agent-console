/**
 * @agent-console/arch-view — 관측 구조도 표현 컴포넌트.
 * 서버가 좌표·라벨·지표까지 채워 준 `ArchitectureView`를 영역·칸·연결로 그린다. API·저장소·다른 사내 UI 패키지를 모른다.
 */
export { ArchitectureDiagram } from "./ArchitectureDiagram";
export type { ArchitectureDiagramProps } from "./ArchitectureDiagram";
export type { ToolbarParts } from "./Toolbar";
export { ArchitectureCellList } from "./ArchitectureCellList";
export type { ArchitectureCellListProps } from "./ArchitectureCellList";
export { ArchitectureInfoBar } from "./ArchitectureInfoBar";
export type { ArchitectureInfoBarProps } from "./ArchitectureInfoBar";
export { ArchitectureLegend } from "./ArchitectureLegend";
export type { ArchitectureLegendProps } from "./ArchitectureLegend";

export { hasBatchim, josa, withJosa } from "./josa";
export { defaultMessages, formatMessage, resolveMessages } from "./messages";
export type { ArchViewMessages } from "./messages";
export {
  defaultEdgeStyles, defaultMetricKinds, defaultTones, defaultZoneLegend, isTokenVar, resolveEdgeStyle, resolveTone,
} from "./defaults";
export {
  abbreviateNumber, compareMetricValue, formatDurationMs, formatMetric, groupDigits, metricPieces, sumMetrics,
} from "./format";
export type { FormatMetricOptions, MetricText } from "./format";
export {
  AUTO_CONTAIN_MIN, EDGE_GAP, MORE_BELOW_SCROLL, autoFit, canvasSize, checkLayout, chipCenter, chipWidthCap, distanceToRect, edgePath, ensureVisible, fitChip, fitViewport,
  gridLayout, nearestInDirection, pathData, polylineMidpoint, zoomAround,
} from "./layout";
export type { AutoFit, ChipContent, ChipFit, FitOptions, Direction, LayoutIssue, LayoutIssueKind, Size, Viewport } from "./layout";
export { cellAriaLabel, cellBlockedReason, edgeAriaLabel, edgeBlockedReason, sameSelection } from "./model";
export type {
  ArchFitMode, ArchLevel, ArchSelection, ArchSelectionKind, ArchViewMode, BlockedReason, CellRenderProps, CellRenderer,
  EdgeStyleSpec, MetricKindSpec, Pt, Rect, ZoneLegendItem,
} from "./types";
