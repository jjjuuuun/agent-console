/**
 * @agent-console/graph-editor 공개 API.
 * 캔버스 라이브러리(React Flow)는 이 패키지 안에만 있고, 아래 export에는 그 타입이 나오지 않는다.
 */
export const PACKAGE_NAME = "@agent-console/graph-editor" as const;

export { GraphEditor } from "./components/GraphEditor";
export { NodeCard, nodeAriaLabel, issueAriaText } from "./components/NodeCard";
export type { NodeCardProps } from "./components/NodeCard";
export { NodePalette, PaletteItem, groupNodeTypes } from "./components/NodePalette";
export type { PaletteItemProps } from "./components/NodePalette";
export { TeamPalette, buildTeamPalette } from "./components/TeamPalette";
export type { DefinitionSection, DefinitionSubgroup, TeamPaletteProps } from "./components/TeamPalette";
export { RoleToggleRow } from "./components/RoleToggleRow";
export type { RoleToggleRowProps } from "./components/RoleToggleRow";
export { ResourceChips } from "./components/ResourceChips";
export type { ResourceChipsProps } from "./components/ResourceChips";
export { IssueSuggestionButtons } from "./components/IssueSuggestionButtons";
export type { IssueSuggestionButtonsProps } from "./components/IssueSuggestionButtons";
export { TeamSharedBar } from "./components/TeamSharedBar";
export type { TeamSharedBarProps } from "./components/TeamSharedBar";
export type { NodePaletteProps, PaletteGroup } from "./components/NodePalette";
export { inferKindPorts, resolveEnds } from "./logic/inferPorts";
export type { ConnectEnd, InferPortsResult, InferredKindConnection, ResolvedEnds } from "./logic/inferPorts";
export { EdgeKindDialog } from "./components/EdgeKindDialog";
export type { EdgeKindCandidateInfo, EdgeKindDialogProps } from "./components/EdgeKindDialog";

// 독립 위임·반복 연결(5R.16): 디스크립터 속성만 보는 순수 함수
export { EDGE_PATTERN_COUNT, resolveEdgeStyle } from "./logic/edgeStyle";
export type { ResolveEdgeStyleHints, ResolvedEdgeStyle, StyleSource } from "./logic/edgeStyle";
export { closesFlowLoop, loopRegion } from "./logic/loops";
export type { NewEdgeLike } from "./logic/loops";

export { safeCssColor, safeIconText, firstGlyph } from "./logic/hints";
export { categoryColorSlot, categoryColorVar, fnv1a32 } from "./logic/color";
export type { CategoryColorSlot } from "./logic/color";
export { measureNodeSize, textWidth } from "./logic/size";
export type { MeasureInput, NodeSize } from "./logic/size";
export { defaultMessages, mergeMessages } from "./messages";
export type { GraphEditorMessages } from "./messages";

// 편집 연산·포트 해석(UI 없이 재사용 가능한 순수 로직)
export {
  addEdge,
  addNode,
  centerFreePosition,
  checkConnection,
  decideEdgeKind,
  defaultIdFactory,
  defaultsFromSchema,
  duplicateNodes,
  moveNodes,
  removeSelection,
} from "./logic/ops";
export type { Connection, ConnectionCheck, ConnectionKindContext, IdFactory, Point, PortLookup } from "./logic/ops";
export { schedulingOf } from "./logic/ops";
export { planAutoConnect, rankEdgeKinds, withoutEdges } from "./logic/autoConnect";
export type { AutoConnectPlan, PlanAutoConnectInput } from "./logic/autoConnect";
export {
  applyGraphPatch,
  applyRoleToggle,
  candidateEdgeKinds,
  canHaveResources,
  deriveNodeBadges,
  deriveResourceChips,
  edgeKindBadge,
  formatElapsed,
  getRoleToggleInfo,
  isChipShape,
  isHiddenType,
  nonExecutableNodeIds,
  toggleChoices,
} from "./logic/team";
export { declaredLabels, declaredTexts, evaluateCondition, evaluateWhen, readValuePointer } from "./logic/declared";
export type { DeclaredCondition, DeclaredContext, DeclaredItem, DeclaredText } from "./logic/declared";
export type { EdgeKindBadge, NodeBadgeId, ResourceChip, RoleToggle, ToggleChoice, ToggleContext, ToggleInfo, ToggleKindInfo, ToggleOptions, ToggleResult } from "./logic/team";
export { summarizeIssues } from "./logic/issues";
export type { IssueCounts, IssueSummary } from "./logic/issues";
export { deriveAutoSides } from "./logic/autoSide";
export type { AutoSideBox, AutoSideEdge, AutoSideMap } from "./logic/autoSide";
export { PortResolver, stableStringify } from "./logic/portResolver";
export type { PortEntry, PortResolverOptions, ResolvePortsFn } from "./logic/portResolver";
export { buildNodePorts, toPortViews } from "./logic/ports";
export type { NodePorts } from "./logic/ports";

export { WAYPOINT_CLEARANCE, pushOutOfRects, pushWaypointsOut } from "./logic/waypointClearance";
export { orderByPeer, placeHandles } from "./logic/handles";
export type { PlaceHandlesInput } from "./logic/handles";

// 화면 배치 결정(모양·방향·면)과 연결선 경로 계산(순수 함수, React Flow 비의존)
export {
  BUILTIN_DIRECTIONS,
  FALLBACK_DIRECTION,
  DEFAULT_EDGE_SHAPE,
  FALLBACK_EDGE_SHAPE,
  builtinEdgeShape,
  hasManualRoute,
  newGraphUi,
  AUTO_DIRECTION,
  AUTO_SIDE,
  SIDES,
  isAutoDirection,
  SIDE_GLYPH,
  portLayoutKey,
  resolveDirection,
  resolveEdgeShape,
  resolvePortSide,
} from "./logic/layout";
export type {
  DirectionSides,
  DirectionSource,
  PortIo,
  ResolveDirectionInput,
  ResolveEdgeShapeInput,
  ResolvePortSideInput,
  Resolved,
  ShapeSource,
  SideSource,
} from "./logic/layout";
export { DEFAULT_BEND, DEFAULT_EDGE_RADIUS, EDGE_STUB, MAX_EDGE_RADIUS, MAX_WAYPOINTS, buildEdgePath, sideNormal } from "./logic/edgePath";
export type { BuildEdgePathInput } from "./logic/edgePath";
export { DEFAULT_AUTO_PATH_OPTIONS, DEFAULT_ROUTE_COSTS, DEFAULT_ROUTE_OPTIONS, ROUTE_FALLBACK_ATTR, autoPath, createAStarRouter, createAutoPath, routeFallbackAttrs } from "./logic/route";
export type { AutoPathOptions } from "./logic/route";
export { nudgeParallel } from "./logic/nudge";
export type { NudgeEdge, NudgeRect } from "./logic/nudge";
export { buildRouteInput, handleEndpoint, routePreview } from "./logic/autoRoute";
export type { HandleBox, PreviewEdge, PreviewNode, RouteEdgeInput, RouteInput, RouteNodeGeometry } from "./logic/autoRoute";
export type { AStarRouter, EdgeRouter, RouteCosts, RouteEdgeRequest, RouteObstacle, RouteOptions, RoutedEdge, RouterStats } from "./logic/route";
export { inheritedEdgeShape } from "./logic/convert";
export {
  EDGE_LAYOUT_KEY_ORDER,
  LABEL_T_MAX,
  LABEL_T_MIN,
  LABEL_T_STEP,
  PATH_KEYS,
  RESET_LABEL_PATCH,
  RESET_PATH_PATCH,
  anchorsOf,
  applyEdgeLayoutPatch,
  changedLayoutKeys,
  cycleShape,
  distanceToSegment,
  insertIndexFor,
  insertWaypoint,
  isRedundantWaypoint,
  lockAxis,
  midpointHandles,
  moveWaypoint,
  nearestLabelT,
  nearestOnSegments,
  normalizeEdgeLayout,
  countResettableEdges,
  patchEdgeLayout,
  patchEdgesLayout,
  placeWaypoint,
  removeWaypoint,
  reorderWaypoint,
  setEdgeLayout,
  snapLabelT,
} from "./logic/edgeLayoutOps";
export type { EdgeLayoutPatch } from "./logic/edgeLayoutOps";
export { EdgeLayoutPanel } from "./components/EdgeLayoutPanel";
export type { EdgeLayoutPanelProps } from "./components/EdgeLayoutPanel";
export { MultiLayoutPanel } from "./components/MultiLayoutPanel";
export type { MultiLayoutPanelProps, MultiLayoutEdgesProps, MultiLayoutNodesProps } from "./components/MultiLayoutPanel";
export { EdgeContextMenu } from "./components/EdgeContextMenu";
export type { EdgeContextMenuProps } from "./components/EdgeContextMenu";
export { NodeLayoutPanel } from "./components/NodeLayoutPanel";
export type { NodeLayoutPanelProps, NodeLayoutPortRow } from "./components/NodeLayoutPanel";
export {
  NODE_LAYOUT_KEY_ORDER,
  applyNodeLayoutPatch,
  cycleDirection,
  graphUiLayoutOf,
  moveNodesWithWaypoints,
  nearestSide,
  normalizeNodeLayout,
  orphanPortKeys,
  patchGraphUiLayout,
  patchNodeLayout,
  patchNodesLayout,
  setNodeLayout,
  withPortSide,
} from "./logic/nodeLayoutOps";
export type { NodeLayoutPatch } from "./logic/nodeLayoutOps";
export { LAYOUT_HISTORY_LIMIT, LayoutHistory, sameGraphIgnoringUi } from "./logic/layoutHistory";
export { nodeLayoutModel } from "./logic/layoutPanels";
export type { NodeLayoutModel, NodeLayoutModelInput } from "./logic/layoutPanels";
// 자동 배치(정리): 엔진 계약·ELK 어댑터·팝오버·순수 계산
export { coerceOptionValues, defaultOptionValues } from "./layout/types";
export type { EdgeShapeOption, LayoutEdgeInput, LayoutEngineDescriptor, LayoutNodeInput, LayoutPortInput, LayoutRequest, LayoutResult, OptionDecl, OptionValues } from "./layout/types";
export { ELK_EDGE_SHAPE_OPTION, ELK_ENGINE_ID, ELK_OPTION_DECLS, backEdgesPointBack, createElkEngine, toElkGraph } from "./layout/elkEngine";
export type { ElkEngineOptions, ElkInstance, ToElkOptions } from "./layout/elkEngine";
export { TIDY_TIMEOUT_MS, TidyPopover, normalizeTidyValues } from "./components/TidyPopover";
export type { TidyEdgeKind, TidyPopoverProps, TidyValues } from "./components/TidyPopover";
export { EdgeTroubleChip } from "./components/EdgeTroubleChip";
export type { EdgeTroubleChipProps } from "./components/EdgeTroubleChip";
export { anchorPositions, applyTidy, buildLayoutRequest, countEdgePaths, flowSideOf, resetAllEdgePaths } from "./logic/tidy";
export type { ApplyTidyInput, BuildLayoutRequestInput, TidyNodeView } from "./logic/tidy";
export { detectEdgeTrouble } from "./logic/troubleDetect";
export type { DetectEdgeTroubleOptions, EdgeTrouble, TroubleEdge, TroubleNode, TroubleReason } from "./logic/troubleDetect";
export { defaultStorage, readJson, writeJson } from "./logic/storage";
export type { KeyValueStorage } from "./logic/storage";
export { COLLINEAR_TOLERANCE, DRAG_THRESHOLD, EdgeWaypointLayer, MIN_EDIT_ZOOM } from "./components/EdgeWaypointLayer";
export type { EdgeWaypointLayerProps } from "./components/EdgeWaypointLayer";
export { BUILTIN_EDGE_SHAPES, createEdgeShapeRegistry } from "./shapes/registry";
export type { EdgeShapeRegistry } from "./shapes/registry";
export type {
  EdgeEndpoint,
  EdgePathInput,
  EdgePathResult,
  EdgeSegment,
  EdgeShapeDescriptor,
  PathPointAt,
  Side,
} from "./shapes/types";

export type {
  BindSummary,
  NodeAvatar,
  ChangeMeta,
  ChangeReason,
  ChipView,
  EdgeBadge,
  NodeRunBadge,
  ConfigPanelContext,
  ConnectRejection,
  DefinitionItem,
  GraphEditorHandle,
  PaletteAddSpec,
  TeamSharedProps,
  GraphEditorProps,
  LayoutPanels,
  NodeStateView,
  PaletteStatus,
  PortHandleRenderer,
  PortView,
  Selection,
  ViewOverride,
} from "./types";
