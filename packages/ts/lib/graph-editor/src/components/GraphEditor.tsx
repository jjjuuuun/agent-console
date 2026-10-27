import { useCallback, useEffect, useId, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { DragEvent, KeyboardEvent } from "react";
import {
  Background,
  BackgroundVariant,
  ConnectionMode,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
  useStore,
  useStoreApi,
} from "@xyflow/react";
import type { Ref } from "react";
import type { Connection as FlowConnection, EdgeChange, FinalConnectionState, NodeChange, OnConnectStartParams } from "@xyflow/react";
import type { EdgeLayout, NodeLayout, EdgeTypeDescriptor, Graph, Issue, IssueSuggestion, NodeSpec, EdgeSpec } from "@agent-console/contracts";
import { format, mergeMessages } from "../messages";
import { createEdgeShapeRegistry } from "../shapes/registry";
import { buildFlowModel, inheritedEdgeShape, pickDescriptor } from "../logic/convert";
import { RESET_PATH_PATCH, countResettableEdges, cycleShape, patchEdgeLayout, patchEdgesLayout, setEdgeLayout } from "../logic/edgeLayoutOps";
import { AUTO_DIRECTION, BUILTIN_DIRECTIONS, DEFAULT_EDGE_SHAPE, hasManualRoute, portLayoutKey, resolveDirection } from "../logic/layout";
import { LayoutHistory } from "../logic/layoutHistory";
import { nodeLayoutModel } from "../logic/layoutPanels";
import { cycleDirection, graphUiLayoutOf, moveNodesWithWaypoints, patchGraphUiLayout, patchNodeLayout, patchNodesLayout, setNodeLayout, withPortSide } from "../logic/nodeLayoutOps";
import type { EdgeLayoutPatch } from "../logic/edgeLayoutOps";
import {
  applyGraphPatch,
  applyRoleToggle,
  candidateEdgeKinds,
  canHaveResources,
  endpointRoles,
  getRoleToggleInfo,
} from "../logic/team";
import type { RoleToggle, ToggleContext, ToggleInfo, ToggleOptions } from "../logic/team";
import { toggleChoices } from "../logic/team";
import type { ResolvedPortsInfo } from "../logic/convert";
import {
  addEdge,
  addNode,
  centerFreePosition,
  checkConnection,
  defaultIdFactory,
  duplicateNodes,
  edgesOf,
  nodesOf,
  patchEdge,
  patchNode,
  removeSelection,
  snap,
} from "../logic/ops";
import type { Connection, Point } from "../logic/ops";
import { parseHandleId } from "../logic/ports";
import { summarizeIssues } from "../logic/issues";
import { closesFlowLoop, loopRegion } from "../logic/loops";
import { planConnection } from "../logic/connectPlan";
import { inferKindPorts, resolveEnds } from "../logic/inferPorts";
import type { ConnectEnd } from "../logic/inferPorts";
import { planAutoConnect, withoutEdges } from "../logic/autoConnect";
import { PortResolver } from "../logic/portResolver";
import type { ChangeReason, GraphEditorHandle, GraphEditorProps, LayoutPanels, Selection } from "../types";
import { EdgeKindDialog } from "./EdgeKindDialog";
import type { EdgeKindCandidateInfo } from "./EdgeKindDialog";
import { EdgeContextMenu } from "./EdgeContextMenu";
import type { MultiLayoutPanelProps } from "./MultiLayoutPanel";
import { EdgeEditContext } from "./edgeEdit";
import { useLatestCallback } from "./useLatestCallback";
import type { EdgeEditApi } from "./edgeEdit";
import { PortEditContext } from "./portEdit";
import type { PortEditApi } from "./portEdit";
import { AcEdge, AcNode, BAND_HANDLE_PREFIX } from "./flow";
import { PALETTE_DEFINITION_MIME, PALETTE_DRAG_MIME } from "./NodePalette";
import { TeamPalette } from "./TeamPalette";
import { TeamSharedBar } from "./TeamSharedBar";
import { EdgeTroubleChip } from "./EdgeTroubleChip";
import { useEdgeTrouble } from "./useEdgeTrouble";
import { useAutoRoutes } from "./useAutoRoutes";
import { EdgeRouteContext } from "./routeContext";
import { overrideEdgeShape } from "./viewOverride";
import { createAStarRouter } from "../logic/route";
import type { EdgeRouter } from "../logic/route";
import type { ViewOverride } from "../types";
import { useTidy } from "./useTidy";
import { pushWaypointsOut } from "../logic/waypointClearance";
import { defaultStorage, readJson, writeJson } from "../logic/storage";

const FLOW_NODE_TYPES = { "ac-node": AcNode };
const FLOW_EDGE_TYPES = { "ac-edge": AcEdge };
const EMPTY_STATES: Record<string, never> = {};
const NO_SELECTION: Selection = { nodeIds: [], edgeIds: [] };
const ROLE_TOGGLES: readonly RoleToggle[] = ["entry", "exit", "interaction"];
/** 레이아웃 되돌리기 스택에 쌓는 변경 이유(graph-edges §2.4). 노드 추가·삭제 등은 토스트 [되돌리기]가 맡는다 */
const LAYOUT_REASONS: ReadonlySet<ChangeReason> = new Set<ChangeReason>(["layout", "auto-layout", "move"]);
/** 가장자리 띠(가상 포트)에서 시작한 연결의 핸들 id인가. */
const isBandHandle = (id: string | null | undefined): boolean => id !== null && id !== undefined && id.startsWith(BAND_HANDLE_PREFIX);

/**
 * 연결을 놓을 때 가장 가까운 핸들에 붙는 반경(px, React Flow 기본 20). 노드 몸체에 놓아 포트를 추론할 수 있으므로
 * 작게 둔다: 핸들 근처를 대충 겨냥했다가 엉뚱한 포트에 붙는 오연결을 줄이고, 핸들 위에 정확히 놓을 때만 그 포트를 쓴다.
 */
const CONNECTION_RADIUS = 8;

const failingResolve = (): Promise<never> => Promise.reject(new Error("resolvePorts 미지정"));

interface PendingConnection {
  c: Connection;
  candidates: EdgeTypeDescriptor[];
  preselected: string;
  /** 후보별 추가 정보(순환을 닫을 때 비활성 사유·기본 선택) */
  info: Record<string, EdgeKindCandidateInfo>;
  /** 노드 몸체에 놓아 연결한 경우: 종류별로 추론한 포트(선택한 종류의 연결을 만든다) */
  byKind?: ReadonlyMap<string, Connection>;
}

/** 연결을 놓은 점 아래의 노드 id(React Flow 노드 요소의 `data-id`). 없으면 `undefined`. */
function nodeIdAtPoint(x: number, y: number): string | undefined {
  for (const el of document.elementsFromPoint?.(x, y) ?? []) {
    const host = el.closest(".react-flow__node");
    const id = host?.getAttribute("data-id");
    if (id !== null && id !== undefined) return id;
  }
  return undefined;
}

/** 연결 놓기 이벤트의 화면 좌표(마우스·터치). */
function pointOf(ev: MouseEvent | TouchEvent): { x: number; y: number } | undefined {
  if ("changedTouches" in ev) {
    const t = ev.changedTouches[0];
    return t === undefined ? undefined : { x: t.clientX, y: t.clientY };
  }
  return { x: ev.clientX, y: ev.clientY };
}

interface Toast {
  text: string;
  /** 되돌리기: 삭제 직전 그래프와, 삭제 결과 그래프(그 사이 다른 편집이 있었는지 판단) */
  undo?: { previous: Graph; after: Graph; /** 레이아웃 되돌리기 스택으로 되돌린다(정리 적용) */ viaHistory?: boolean };
}

const sameGraph = (a: Graph, b: Graph): boolean => a === b || JSON.stringify(a) === JSON.stringify(b);

function isTextField(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/**
 * 디스크립터 기반 그래프 편집기. 노드 렌더러는 하나뿐이며 노드 타입 id 분기가 없다.
 * `readOnly`면 팔레트·편집 UI 없이 선택·패닝·줌·패널 슬롯만 동작한다(실행 보기).
 * 공개 API에는 @xyflow/react 타입이 나오지 않는다.
 */
/** 자동 첫 맞춤 재시도 간격(ms). 노드 측정이 끝나면(`useNodesInitialized`) 효과가 다시 돌아 한 번 더 맞춘다. */
const FIRST_FIT_RETRY_MS = [0, 120, 400, 1000] as const;
/**
 * 화면 맞춤 옵션. 작은 그래프는 확대하지 않고(최대 1.0) 가운데에 두며, 큰 그래프도 노드 글자가 읽히는 줌(0.45) 아래로는 줄이지 않는다
 * (넘치는 부분은 끌어서 보고, 전체는 미니맵으로 본다). 실제 캔버스 크기(옆 패널·팔레트가 자리 잡은 뒤)로 계산한다.
 */
export const FIT_VIEW_OPTIONS = { padding: 0.08, maxZoom: 1, minZoom: 0.45 } as const;
/** 입구(가장 왼쪽) 노드 기준 맞춤에서 입구 노드를 캔버스 왼쪽에서 띄우는 거리(px) */
const ENTRY_FIT_MARGIN = 24;

/** 가장자리에 걸친 것으로 치지 않는 오차(px) */
const OFFSCREEN_TOLERANCE = 2;

/** 화면 밖에 있거나 가장자리에 걸쳐 잘린 노드 수를 알리는 단서. 눌러서 전체가 보이게 줄인다(큰 그래프에서 입구 기준 첫 맞춤 뒤 이동 단서). */
function OffscreenCue({ label, hint, onShowAll }: { label: (n: number) => string; hint: string; onShowAll: () => void }) {
  const count = useStore((st) => {
    const [tx, ty, z] = st.transform;
    if (st.width <= 0 || st.height <= 0) return 0;
    let n = 0;
    for (const node of st.nodeLookup.values()) {
      if (node.hidden) continue;
      const w = node.measured.width ?? 0;
      const h = node.measured.height ?? 0;
      if (w === 0 || h === 0) continue;
      const x = node.internals.positionAbsolute.x * z + tx;
      const y = node.internals.positionAbsolute.y * z + ty;
      // 완전히 나간 노드뿐 아니라 가장자리에 걸쳐 잘린 노드도 센다(패널 옆에서 반쯤 잘린 노드를 놓치지 않게)
      if (x < -OFFSCREEN_TOLERANCE || y < -OFFSCREEN_TOLERANCE || x + w * z > st.width + OFFSCREEN_TOLERANCE || y + h * z > st.height + OFFSCREEN_TOLERANCE) n += 1;
    }
    return n;
  });
  if (count === 0) return null;
  return (
    <Panel position="top-right" className="ac-ge-offscreen">
      <button type="button" className="ac-ge-btn" title={hint} aria-label={`${label(count)}. ${hint}`} onClick={onShowAll}>
        {label(count)}
      </button>
    </Panel>
  );
}

/**
 * 첫 맞춤. 그래프 전체가 최소 읽기 줌(`FIT_VIEW_OPTIONS.minZoom`) 이상에서 들어가면 전체를 맞추고,
 * 그렇지 않으면 입구(가장 왼쪽) 노드를 캔버스 왼쪽에 두고 그 줌으로 시작한다(글자가 읽히는 크기 우선, 나머지는 끌어서 본다).
 */
async function fitReadable(flow: ReturnType<typeof useReactFlow>, size: { width: number; height: number }, duration: number, bottomInset = 0): Promise<void> {
  // 캔버스 아래 가운데의 보기 도구줄이 노드를 덮지 않도록 그 높이만큼 아래 여백을 더 둔다
  const px = (ratio: number, of: number): `${number}px` => `${Math.round(ratio * of)}px`;
  const padding = bottomInset > 0 && size.width > 0 && size.height > 0
    ? { top: px(FIT_VIEW_OPTIONS.padding, size.height), left: px(FIT_VIEW_OPTIONS.padding, size.width), right: px(FIT_VIEW_OPTIONS.padding, size.width), bottom: px(Math.max(bottomInset / size.height, FIT_VIEW_OPTIONS.padding), size.height) }
    : FIT_VIEW_OPTIONS.padding;
  await flow.fitView({ ...FIT_VIEW_OPTIONS, padding, duration });
  const v = flow.getViewport();
  if (v.zoom > FIT_VIEW_OPTIONS.minZoom + 0.001) return;
  const nodes = flow.getNodes().filter((n) => !n.hidden);
  if (nodes.length === 0 || size.width <= 0) return;
  const b = flow.getNodesBounds(nodes);
  const zoom = FIT_VIEW_OPTIONS.minZoom;
  await flow.setViewport({ x: ENTRY_FIT_MARGIN - b.x * zoom, y: (size.height - bottomInset) / 2 - (b.y + b.height / 2) * zoom, zoom }, { duration });
}

/** 보기 도구줄(아래 가운데)이 차지하는 높이(px). 첫 맞춤이 이만큼 아래를 비워 둔다. */
const VIEW_TOOLBAR_INSET = 44;

/** 첫 맞춤 뒤 캔버스 크기가 바뀌어도(옆 패널이 자리 잡는 동안) 다시 맞추는 시간(ms). 이후 크기 변화는 사용자 시점을 건드리지 않는다. */
const REFIT_WINDOW_MS = 3000;

/** 줌이 이 값보다 낮으면 연결 칩은 아이콘만 보인다(글자는 연결의 접근성 이름에 남는다). */
const LOW_ZOOM = 0.6;
/** 이 줌 미만이면 노드 제목을 화면 12px 상당으로 키운다(한 줄 말줄임, 전체 이름은 title 툴팁). 14px 기준 12/14 */
const TITLE_BOOST_ZOOM = 0.85;
/** 노드 카드 대략 크기의 절반: 보이는 영역 중앙에 놓을 때 카드 중심을 맞추는 값 */
const CARD_HALF_W = 110;
const CARD_HALF_H = 40;
/** 미니맵은 캔버스를 덮지 않게 작게 그린다 */
const MINIMAP_STYLE = { width: 168, height: 112 } as const;

export function GraphEditor({ ref, ...props }: GraphEditorProps) {
  return (
    <ReactFlowProvider>
      <GraphEditorInner {...props} handleRef={ref} />
    </ReactFlowProvider>
  );
}

function GraphEditorInner(props: Omit<GraphEditorProps, "ref"> & { handleRef: Ref<GraphEditorHandle> | undefined }) {
  const { graph, nodeTypes, edgeTypes, onChange } = props;
  const readOnly = props.readOnly === true || props.mode === "readonly-run";
  const grid = props.snapToGrid === undefined ? 8 : props.snapToGrid;
  const idFactory = props.idFactory ?? defaultIdFactory;
  const m = useMemo(() => mergeMessages(props.messages), [props.messages]);
  const nodeStates = props.nodeStates ?? EMPTY_STATES;
  const edgeStates = props.edgeStates ?? EMPTY_STATES;
  const uid = useId().replace(/[^A-Za-z0-9_-]/g, "");
  const markerId = `ac-ge-arrow-${uid}`;
  const flow = useReactFlow();
  const rootRef = useRef<HTMLDivElement>(null);
  // 낮은 줌: 경계를 넘을 때만 다시 그린다(연결마다 구독하지 않는다)
  const lowZoom = useStore((st) => st.transform[2] < LOW_ZOOM);
  const titleBoost = useStore((st) => st.transform[2] < TITLE_BOOST_ZOOM);
  // 줌을 CSS 변수로 내보낸다(가장자리 띠가 줌아웃에서도 화면에서 일정한 굵기를 갖게). 노드를 다시 그리지 않고 루트 요소에만 쓴다.
  const flowStore = useStoreApi();
  // 연결을 끄는 동안 노드 위에 보이는 "여기에 연결" 라벨(CSS `content`가 읽는다)
  const dropLabel = m.dropHere;
  useEffect(() => {
    rootRef.current?.style.setProperty("--ac-ge-drop-label", JSON.stringify(dropLabel));
  }, [dropLabel]);
  useEffect(() => {
    const write = (zoom: number) => rootRef.current?.style.setProperty("--ac-ge-zoom", String(zoom));
    write(flowStore.getState().transform[2]);
    return flowStore.subscribe((st) => write(st.transform[2]));
  }, [flowStore]);

  // ---- 리소스 보기(제어형 또는 내부 상태) / 경과 시계 ----
  const [innerShowResources, setInnerShowResources] = useState(props.mode !== "readonly-run");
  const showResources = props.showResources ?? innerShowResources;
  const hasResourceTypes = nodeTypes.some((t) => t.executable === false && t.ui_hints?.hidden !== true);
  const { onShowResourcesChange } = props;
  const setShowResources = useCallback(
    (v: boolean) => {
      setInnerShowResources(v);
      onShowResourcesChange?.(v);
    },
    [onShowResourcesChange],
  );
  const hasWaiting = Object.keys(props.waitingNodes ?? {}).length > 0;
  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => {
    if (!hasWaiting || props.nowMs !== undefined) return;
    const h = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(h);
  }, [hasWaiting, props.nowMs]);
  const nowMs = props.nowMs ?? clock;
  const [lastKind, setLastKind] = useState<string | undefined>(undefined);

  // ---- 동적 포트 계산 ----
  const [resolver] = useState(() => new PortResolver({ resolve: failingResolve }));
  useEffect(() => {
    resolver.setResolve(props.resolvePorts ?? failingResolve);
  }, [resolver, props.resolvePorts]);
  const resolverVersion = useSyncExternalStore(resolver.subscribe, resolver.getVersion);
  const gNodes = nodesOf(graph);
  useEffect(() => {
    const ids = new Set<string>();
    for (const n of nodesOf(graph)) {
      ids.add(n.id);
      const d = pickDescriptor(n, nodeTypes);
      if (d?.dynamic_ports === true) resolver.request(n.id, d.id, n.config ?? {});
    }
    resolver.retain(ids);
  }, [graph, nodeTypes, resolver]);
  const resolved = useMemo(() => {
    const map = new Map<string, ResolvedPortsInfo>();
    for (const n of gNodes) {
      const e = resolver.get(n.id);
      map.set(n.id, { spec: e.ports, loading: e.loading, failed: e.failed });
    }
    return map;
    // resolverVersion: 계산 결과가 바뀔 때 재계산
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gNodes, resolver, resolverVersion]);

  // ---- 로컬 UI 상태 ----
  const [selection, setSelection] = useState<Selection>(NO_SELECTION);
  const [overrides, setOverrides] = useState<ReadonlyMap<string, Point>>(new Map());
  const [seenGraph, setSeenGraph] = useState(graph);
  if (seenGraph !== graph) {
    setSeenGraph(graph);
    if (overrides.size > 0) setOverrides(new Map());
  }
  const [toast, setToast] = useState<Toast | null>(null);
  const [pending, setPending] = useState<PendingConnection | null>(null);
  /** `T` 키: 선택한 연결의 종류를 바꾸는 선택 UI(새 연결 만들기와 같은 `EdgeKindDialog`) */
  const [kindChange, setKindChange] = useState<{ edgeId: string; candidates: EdgeTypeDescriptor[]; preselected: string; info: Record<string, EdgeKindCandidateInfo> } | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [choiceFor, setChoiceFor] = useState<{ nodeId: string; toggle: RoleToggle } | null>(null);
  const onChoiceMenuKeyDown = useCallback((e: KeyboardEvent<HTMLElement>) => {
    const menu = e.currentTarget;
    const items = Array.from(menu.querySelectorAll<HTMLElement>('[role="menuitem"]'));
    const at = items.indexOf(document.activeElement as HTMLElement);
    let to: number;
    if (e.key === "ArrowDown") to = (at + 1) % items.length;
    else if (e.key === "ArrowUp") to = (at - 1 + items.length) % items.length;
    else if (e.key === "Home") to = 0;
    else if (e.key === "End") to = items.length - 1;
    else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      const toggle = menu.parentElement?.querySelector<HTMLElement>('[aria-haspopup="menu"]');
      setChoiceFor(null);
      toggle?.focus();
      return;
    } else return;
    e.preventDefault();
    items[to]?.focus();
  }, []);
  const [fitRequest, setFitRequest] = useState<{ ids: string[]; token: number } | null>(null);
  const [announce, setAnnounce] = useState("");
  const [pathEditId, setPathEditId] = useState<string | null>(null);
  const [menu, setMenu] = useState<{ at: { x: number; y: number }; edgeIds: string[] } | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const zoomHinted = useRef(false);

  const existingIds = useMemo(() => new Set(gNodes.map((n) => n.id)), [gNodes]);
  const eff: Selection = useMemo(
    () => ({
      nodeIds: selection.nodeIds.filter((id) => existingIds.has(id)),
      edgeIds: selection.edgeIds.filter((id) => edgesOf(graph).some((e) => e.id === id)),
    }),
    [selection, existingIds, graph],
  );

  const { onSelectionChange } = props;
  // 같은 이벤트에서 노드 변경과 연결선 변경이 연이어 들어올 때(연결선이 선택된 채 노드를 클릭 등),
  // 뒤 콜백이 아직 갱신되지 않은 `eff`를 읽어 앞 선택을 덮어쓰지 않도록 방금 낸 선택을 렌더 전까지 기억한다.
  const pendingSelection = useRef<Selection | null>(null);
  useEffect(() => {
    pendingSelection.current = null;
  });
  const select = useCallback(
    (next: Selection) => {
      pendingSelection.current = next;
      setSelection(next);
      onSelectionChange?.(next);
    },
    [onSelectionChange],
  );

  const showToast = useCallback((t: Toast) => setToast(t), []);
  const undoWindow = props.undoWindowMs ?? 5000;
  useEffect(() => {
    if (toast === null) return;
    const h = setTimeout(() => setToast(null), undoWindow);
    return () => clearTimeout(h);
  }, [toast, undoWindow]);

  const [history] = useState(() => new LayoutHistory());
  // onChange가 렌더마다 새 함수여도 emit(과 그에 기대는 패널 값)이 흔들리지 않게 최신 값만 ref로 읽는다
  const callOnChange = useLatestCallback(onChange);
  const emit = useCallback(
    (next: Graph, reason: ChangeReason) => {
      if (LAYOUT_REASONS.has(reason)) history.record(graph, next);
      callOnChange(next, { reason, previous: graph });
    },
    [graph, history, callOnChange],
  );
  // 사용자 설정 층의 기본값. 앱이 객체를 새로 만들어 넘겨도 값이 같으면 같은 참조로 쓴다
  const ldDirection = props.layoutDefaults?.direction;
  const ldEdgeShape = props.layoutDefaults?.edgeShape;
  const layoutDefaults = useMemo(
    () => (ldDirection === undefined && ldEdgeShape === undefined ? undefined : { ...(ldDirection !== undefined ? { direction: ldDirection } : {}), ...(ldEdgeShape !== undefined ? { edgeShape: ldEdgeShape } : {}) }),
    [ldDirection, ldEdgeShape],
  );
  const directionTable = props.directions ?? BUILTIN_DIRECTIONS;
  const directionIds = useMemo(() => [...Object.keys(directionTable), AUTO_DIRECTION], [directionTable]);
  const portEditApi: PortEditApi = useMemo(
    () => ({
      editable: !readOnly,
      messages: m,
      setPortSide: (nodeId, io, portId, _label, side) => {
        const node = nodesOf(graph).find((n) => n.id === nodeId);
        if (node === undefined) return;
        emit(setNodeLayout(graph, nodeId, withPortSide(node.layout, portLayoutKey(io, portId), side)), "layout");
      },
      announce: setAnnounce,
    }),
    [readOnly, m, graph, emit],
  );

  // ---- 연결선 모양·경로 편집(graph-edges §2) ----
  const onlyEdgeId = eff.edgeIds.length === 1 && eff.nodeIds.length === 0 ? (eff.edgeIds[0] as string) : null;
  const onlyNodeId = eff.nodeIds.length === 1 && eff.edgeIds.length === 0 ? (eff.nodeIds[0] as string) : null;
  const pathEdit = pathEditId !== null && pathEditId === onlyEdgeId ? pathEditId : null;
  const commitLayout = useCallback(
    (edgeId: string, patch: EdgeLayoutPatch) => {
      emit(patchEdgeLayout(graph, edgeId, patch), "layout");
    },
    [emit, graph],
  );
  const exitPathEdit = useCallback(
    (edgeId: string) => {
      setPathEditId(null);
      setAnnounce(m.pathEditEnded);
      canvasRef.current?.querySelector<HTMLElement>(`.react-flow__edge[data-id="${CSS.escape(edgeId)}"]`)?.focus();
    },
    [m],
  );
  const editApi: EdgeEditApi = useMemo(
    () => ({
      editable: !readOnly,
      pathEditEdgeId: pathEdit,
      messages: m,
      snapGrid: grid,
      screenToFlow: (p) => flow.screenToFlowPosition(p),
      commit: commitLayout,
      announce: setAnnounce,
      notify: (text) => {
        setToast({ text });
        setAnnounce(text);
      },
      zoomHint: () => {
        if (zoomHinted.current) return;
        zoomHinted.current = true;
        setToast({ text: m.waypointZoomHint });
      },
      exitPathEdit,
    }),
    [readOnly, pathEdit, m, grid, flow, commitLayout, exitPathEdit],
  );

  // ---- 반복 영역: 사이클 연결 하나를 선택하는 동안 그 영역의 노드에 윤곽을 그리고 이름을 읽어 준다 ----
  const regionIds = useMemo(() => (onlyEdgeId === null ? [] : loopRegion(graph, edgeTypes, onlyEdgeId)), [graph, edgeTypes, onlyEdgeId]);
  const regionKey = regionIds.join("\u0000");
  const regionNodes = useMemo(() => (regionIds.length === 0 ? null : new Set(regionIds)), [regionKey]); // eslint-disable-line react-hooks/exhaustive-deps
  // 선택이 바뀌어 영역이 달라질 때만 안내한다(렌더 중 "본 키" 비교, 위 `seenGraph`와 같은 방식)
  const [seenRegion, setSeenRegion] = useState("");
  if (seenRegion !== regionKey) {
    setSeenRegion(regionKey);
    if (regionNodes !== null) {
      const names = regionIds.map((id) => gNodes.find((n) => n.id === id)?.label ?? id);
      const more = names.length > 5 ? ` ${format(m.loopRegionMore, { n: names.length - 5 })}` : "";
      setAnnounce(format(m.loopRegionAnnounce, { count: names.length, names: names.slice(0, 5).join(", ") + more }));
    }
  }

  // ---- 모델 ----
  const edgeShapes = useMemo(() => createEdgeShapeRegistry(props.edgeShapes), [props.edgeShapes]);
  const issueSummary = useMemo(() => summarizeIssues(props.issues), [props.issues]);
  const model = useMemo(
    () =>
      buildFlowModel({
        graph,
        nodeTypes,
        edgeTypes,
        resolved,
        nodeStates,
        edgeStates,
        selectedNodes: new Set(eff.nodeIds),
        selectedEdges: new Set(eff.edgeIds),
        positionOverrides: overrides,
        readOnly,
        messages: m,
        markerId,
        issues: issueSummary,
        showResources,
        portLabels: props.portLabels ?? "auto",
        nowMs,
        edgeShapes,
        ...(layoutDefaults !== undefined ? { layoutDefaults: layoutDefaults } : {}),
        ...(props.directions !== undefined ? { directions: props.directions } : {}),
        ...(props.waitingNodes !== undefined ? { waitingNodes: props.waitingNodes } : {}),
        ...(props.edgeOrder !== undefined ? { edgeOrder: props.edgeOrder } : {}),
        ...(props.edgeCounts !== undefined ? { edgeCounts: props.edgeCounts } : {}),
        ...(props.nodeBadgesOverride !== undefined ? { nodeBadgesOverride: props.nodeBadgesOverride } : {}),
        ...(props.onOpenResources !== undefined ? { onResourceChipsClick: props.onOpenResources } : {}),
        ...(props.nodeRunBadges !== undefined ? { nodeRunBadges: props.nodeRunBadges } : {}),
        ...(props.edgeBadges !== undefined ? { edgeBadges: props.edgeBadges } : {}),
        ...(props.edgeExtraChips !== undefined ? { edgeExtraChips: props.edgeExtraChips } : {}),
        ...(props.bindSummaries !== undefined ? { bindSummaries: props.bindSummaries } : {}),
        ...(props.nodeAvatars !== undefined ? { nodeAvatars: props.nodeAvatars } : {}),
        ...(props.delegationStrategies !== undefined ? { delegationStrategies: props.delegationStrategies } : {}),
        ...(props.edgeStrategyIds !== undefined ? { edgeStrategyIds: props.edgeStrategyIds } : {}),
        ...(props.renderIcon !== undefined ? { renderIcon: props.renderIcon } : {}),
        ...(regionNodes !== null ? { loopRegionNodes: regionNodes } : {}),
      }),
    [graph, nodeTypes, edgeTypes, resolved, nodeStates, edgeStates, eff, overrides, readOnly, m, markerId, issueSummary, showResources, props.portLabels, nowMs, props.waitingNodes, props.edgeOrder, props.edgeCounts, props.nodeBadgesOverride, props.onOpenResources, edgeShapes, layoutDefaults, props.directions, props.nodeRunBadges, props.edgeBadges, props.edgeExtraChips, props.bindSummaries, props.nodeAvatars, props.delegationStrategies, props.edgeStrategyIds, props.renderIcon, regionNodes],
  );

  // React Flow는 노드 크기 측정 결과를 노드 객체에 요구한다(제어형이므로 직접 보관).
  const [measured, setMeasured] = useState<ReadonlyMap<string, { width: number; height: number }>>(new Map());
  const flowNodes = useMemo(
    () =>
      model.nodes.map((n) => {
        const dim = measured.get(n.id);
        return dim === undefined ? n : { ...n, measured: dim };
      }),
    [model.nodes, measured],
  );

  /** 노드 방향 순환(lr → tb → rl → bt → 상속). `R` 키와 툴바 버튼이 쓴다 */
  const rotateDirection = useCallback(
    (nodeId: string, step: 1 | -1 = 1) => {
      if (readOnly) return;
      const node = nodesOf(graph).find((n) => n.id === nodeId);
      if (node === undefined) return;
      const next = cycleDirection(directionIds, node.layout?.direction, step);
      emit(patchNodeLayout(graph, nodeId, { direction: next }), "layout");
      const value =
        next ??
        resolveDirection({
          node: null,
          graph: graphUiLayoutOf(graph),
          settings: layoutDefaults?.direction ?? null,
          hint: (() => {
            const h = pickDescriptor(node, nodeTypes)?.ui_hints?.["direction"];
            return typeof h === "string" ? h : null;
          })(),
          directions: directionTable,
        }).value;
      const title = m.directionLabels[value] ?? value;
      setAnnounce(format(m.directionChanged, { title: next === null ? format(m.nodeLayoutInheritedNow, { source: m.nodeLayoutInherit, direction: title }) : title }));
    },
    [readOnly, graph, directionIds, emit, layoutDefaults, nodeTypes, directionTable, m],
  );

  // ---- 정리([정리 ▾])·엉킨 연결 힌트 ----
  const storage = useMemo(() => (props.storage === undefined ? defaultStorage() : props.storage), [props.storage]);
  const storagePrefix = props.storageKeyPrefix ?? "agent-console.graph-editor.";
  const pendingFit = useRef<Graph | null>(null);
  // 라우터는 편집기 인스턴스당 하나(작업 메모리가 크다). 자동 경로 엣지나 정리 미리보기가 처음 필요할 때 만든다
  const routerRef = useRef<EdgeRouter | null>(null);
  const { edgeRouter } = props;
  const getRouter = useCallback((): EdgeRouter => edgeRouter ?? (routerRef.current ??= createAStarRouter()), [edgeRouter]);
  // 실행 상세의 보기 전용 덮어쓰기(브라우저 로컬 상태, 데이터를 쓰지 않는다)
  const viewOptions = useMemo<readonly ViewOverride[]>(() => {
    const list = props.viewOverrides ?? [
      { shapeId: "auto", label: m.viewAuto, short: m.viewAutoShort },
      { shapeId: "bezier", label: m.viewCurve, short: m.viewCurveShort },
    ];
    return list.filter((o) => edgeShapes.has(o.shapeId));
  }, [props.viewOverrides, m, edgeShapes]);
  const viewable = props.mode === "readonly-run" && viewOptions.length > 0;
  const [viewShapeId, setViewShapeId] = useState<string | null>(null);
  const activeView = viewable ? (viewOptions.find((o) => o.shapeId === viewShapeId) ?? null) : null;
  const overriddenEdges = useMemo(() => overrideEdgeShape(model.edges, activeView === null ? undefined : edgeShapes.get(activeView.shapeId)), [model.edges, activeView, edgeShapes]);
  // 읽기 전용 보기: 실제 카드가 편집기보다 커서 사용자 경유점이 카드 안에 들어가면 렌더 때만 카드 밖으로 민다(저장 데이터 불변)
  const viewEdges = useMemo(() => {
    if (!readOnly || !overriddenEdges.some((e) => (e.data?.waypoints?.length ?? 0) > 0)) return overriddenEdges;
    const rects = flowNodes.map((n) => ({ x: n.position.x, y: n.position.y, width: n.measured?.width ?? n.initialWidth ?? 0, height: n.measured?.height ?? n.initialHeight ?? 0 }));
    return overriddenEdges.map((e) => {
      const wps = e.data?.waypoints;
      if (e.data === undefined || wps === undefined || wps === null) return e;
      const pushed = pushWaypointsOut(wps, rects);
      return pushed === wps ? e : { ...e, data: { ...e.data, waypoints: [...pushed] } };
    });
  }, [overriddenEdges, readOnly, flowNodes]);
  const routes = useAutoRoutes({ edges: viewEdges, getRouter });
  const tidy = useTidy({
    getRouter,
    graph,
    engines: props.layoutEngines,
    flowNodes,
    edgeTypes,
    shapes: edgeShapes.list,
    directions: directionTable,
    layoutDefaults,
    selectedNodeIds: eff.nodeIds,
    grid,
    readOnly,
    storage,
    storagePrefix,
    messages: m,
    emit,
    announce: setAnnounce,
    toastUndo: (text, previous, after) => setToast({ text, undo: { previous, after, viaHistory: true } }),
    requestFit: () => {
      pendingFit.current = graph;
    },
  });
  const insetRef = useRef(0);
  const toolbarInset = hasResourceTypes || tidy.available || viewable ? VIEW_TOOLBAR_INSET : 0;
  // 렌더 중에는 ref를 쓰지 않는다. 맞춤 효과(아래)보다 먼저 도는 레이아웃 효과에서 갱신한다.
  useLayoutEffect(() => {
    insetRef.current = toolbarInset;
  }, [toolbarInset]);
  useEffect(() => {
    // 정리를 적용한 새 그래프가 들어온 뒤 화면에 맞춘다(움직임 줄이기 설정이면 애니메이션 없음)
    if (pendingFit.current === null || pendingFit.current === graph) return;
    pendingFit.current = null;
    const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
    const h = requestAnimationFrame(() => void fitReadable(flow, flowStore.getState(), reduce ? 0 : 250, insetRef.current));
    return () => cancelAnimationFrame(h);
  }, [graph, flow, flowStore]);
  const troubleOn = !readOnly && props.troubleHint !== false;
  const troubleIds = useEdgeTrouble({ enabled: troubleOn, ready: model.nodes.length > 1, nodes: model.nodes, edges: viewEdges, size: measured, routes });
  const [troubleHidden, setTroubleHidden] = useState<ReadonlySet<string>>(new Set());
  const troubleKey = `${storagePrefix}trouble-dismissed.${graph.id}`;
  const troubleDismissedBefore = useMemo(() => readJson(storage, troubleKey) === true, [storage, troubleKey]);
  const hideTrouble = (persist: boolean): void => {
    setTroubleHidden((cur) => new Set(cur).add(graph.id));
    if (persist) writeJson(storage, troubleKey, true);
  };
  const showTrouble = troubleIds.length > 0 && !troubleDismissedBefore && !troubleHidden.has(graph.id);
  /**
   * [자동 경로로]: 노드를 지나는 연결선을 자동 경로로 돌린다(한 번의 `onChange`).
   * 상속하면 자동 경로가 되는 엣지는 `layout.shape`만 지우고, 그렇지 않은 엣지(직접 고친 선·상위 층이 다른 모양)는 `auto`를 직접 적는다(경유점은 보존).
   */
  const autoRouteTrouble = (): void => {
    if (readOnly || !edgeShapes.has(DEFAULT_EDGE_SHAPE)) return;
    const toClear: string[] = [];
    const toSet: string[] = [];
    for (const e of edgesOf(graph)) {
      if (!troubleIds.includes(e.id)) continue;
      const inherited = inheritedEdgeShape(e, edgeTypes.find((t) => t.id === e.kind), { graph, ...(layoutDefaults !== undefined ? { layoutDefaults: layoutDefaults } : {}) }, edgeShapes);
      (!hasManualRoute(e.layout) && inherited.route !== undefined ? toClear : toSet).push(e.id);
    }
    const next = patchEdgesLayout(patchEdgesLayout(graph, toClear, { shape: null }), toSet, { shape: DEFAULT_EDGE_SHAPE });
    if (next === graph) return;
    emit(next, "layout");
    hideTrouble(false);
  };

  // ---- 편집 연산 ----
  const { autoConnectIo, onAutoConnect, defaultEdgeKind } = props;
  const [reveal, setReveal] = useState<{ id: string; label: string; token: number } | null>(null);
  const addByType = useCallback(
    (typeId: string, position?: Point, definition?: { id: string; name: string }): string | undefined => {
      if (readOnly) return undefined;
      const candidates = nodeTypes.filter((t) => t.id === typeId);
      const descriptor = candidates.reduce<(typeof nodeTypes)[number] | undefined>(
        (a, b) => (a === undefined || (b.version ?? 0) >= (a.version ?? 0) ? b : a),
        undefined,
      );
      if (descriptor === undefined) return undefined;
      const { graph: next, nodeId } = addNode(graph, {
        descriptor,
        idFactory,
        grid,
        ...(definition !== undefined ? { definition } : {}),
        ...(eff.nodeIds.length > 0 ? { anchorId: eff.nodeIds[eff.nodeIds.length - 1] as string } : {}),
        ...(position !== undefined ? { position: snap(position, grid) } : {}),
      });
      // 입구·답변 자동 연결: 조건을 만족하면 노드 추가와 두 연결을 한 번의 onChange(reason `auto-connect`)로 낸다
      const auto =
        autoConnectIo === true
          ? planAutoConnect({ graph: next, nodeId, nodeTypes, edgeTypes, idFactory, portsOf: (id) => model.specs.get(id), preferredKind: lastKind ?? defaultEdgeKind })
          : null;
      if (auto !== null) {
        emit(auto.graph, "auto-connect");
        if (onAutoConnect !== undefined) onAutoConnect({ addedEdgeIds: auto.addedEdgeIds, graph: auto.graph, previous: next });
        else showToast({ text: m.autoConnected, undo: { previous: withoutEdges(auto.graph, auto.addedEdgeIds), after: auto.graph } });
      } else emit(next, "add-node");
      select({ nodeIds: [nodeId], edgeIds: [] });
      setAnnounce(format(m.added, { label: definition?.name ?? descriptor.title }));
      // 위치를 정하지 않은 추가(팔레트 [추가]·Enter·더블클릭)는 새 노드가 화면 밖일 수 있어 보이게 옮긴다
      if (position === undefined) setReveal((r) => ({ id: nodeId, label: definition?.name ?? descriptor.title, token: (r?.token ?? 0) + 1 }));
      return nodeId;
    },
    [readOnly, nodeTypes, edgeTypes, graph, idFactory, grid, emit, select, m, eff.nodeIds, autoConnectIo, onAutoConnect, defaultEdgeKind, lastKind, model.specs, showToast],
  );
  useEffect(() => {
    if (reveal === null) return;
    const attempt = (): boolean => {
      const node = flow.getNode(reveal.id);
      const box = canvasRef.current?.querySelector<HTMLElement>(".react-flow")?.getBoundingClientRect();
      if (node === undefined || box === undefined || box.width === 0 || box.height === 0) return false;
      const v = flow.getViewport();
      const w = node.measured?.width ?? node.initialWidth ?? 0;
      const h = node.measured?.height ?? node.initialHeight ?? 0;
      const left = node.position.x * v.zoom + v.x;
      const top = node.position.y * v.zoom + v.y;
      const inside = left >= 0 && top >= 0 && left + w * v.zoom <= box.width && top + h * v.zoom <= box.height;
      if (inside) return true;
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
      // 카드가 현재 줌에서 화면보다 크면 줌을 낮춰 통째로 보이게 맞춘다
      if (w * v.zoom > box.width * 0.6 || h * v.zoom > box.height * 0.6) {
        void flow.fitView({ nodes: [{ id: reveal.id }], maxZoom: 1, padding: 0.3, duration: reduce ? 0 : 200 });
        setAnnounce(format(m.addedRevealed, { label: reveal.label }));
        return true;
      }
      void flow.setCenter(node.position.x + w / 2, node.position.y + h / 2, { zoom: v.zoom, duration: reduce ? 0 : 200 });
      setAnnounce(format(m.addedRevealed, { label: reveal.label }));
      return true;
    };
    // 새 노드는 다음 렌더 뒤에야 캔버스에 들어온다
    let settled = false;
    const timers = [0, 60, 200, 600, 1500].map((ms) =>
      setTimeout(() => {
        if (!settled && attempt()) settled = true;
      }, ms),
    );
    return () => timers.forEach(clearTimeout);
    // 요청(token)이 바뀔 때만 실행
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reveal?.token]);

  const removeSelected = useCallback(() => {
    if (readOnly || (eff.nodeIds.length === 0 && eff.edgeIds.length === 0)) return;
    const next = removeSelection(graph, eff);
    const count = eff.nodeIds.length + eff.edgeIds.length;
    emit(next, "remove");
    select(NO_SELECTION);
    const text = format(m.removed, { count });
    setAnnounce(text);
    showToast({ text, undo: { previous: graph, after: next } });
  }, [readOnly, eff, graph, emit, select, showToast, m]);

  const duplicateSelected = useCallback(() => {
    if (readOnly || eff.nodeIds.length === 0) return;
    const { graph: next, newNodeIds } = duplicateNodes(graph, eff.nodeIds, idFactory);
    emit(next, "duplicate");
    select({ nodeIds: newNodeIds, edgeIds: [] });
    setAnnounce(format(m.duplicated, { count: newNodeIds.length }));
  }, [readOnly, eff.nodeIds, graph, idFactory, emit, select, m]);

  const portsLookup = useCallback(
    (id: string) => {
      const spec = model.specs.get(id);
      return spec === undefined ? undefined : { inputs: (spec.inputs ?? []).map((p) => p.name), outputs: (spec.outputs ?? []).map((p) => p.name) };
    },
    [model.specs],
  );

  /** 포트의 화면 이름(`PortDef.label`, 없으면 포트 이름). */
  const portLabelOf = useCallback(
    (nodeId: string, io: "in" | "out", port: string): string => {
      const spec = model.specs.get(nodeId);
      const def = (io === "in" ? spec?.inputs : spec?.outputs)?.find((p) => p.name === port);
      return def?.label ?? port;
    },
    [model.specs],
  );

  const reject = useCallback(
    (reason: "no-kind" | "cycle" | "self" | "duplicate" | "port", c: Connection) => {
      const sType = nodesOf(graph).find((n) => n.id === c.source.node)?.type;
      const tType = nodesOf(graph).find((n) => n.id === c.target.node)?.type;
      const roles = endpointRoles(sType, tType, nodeTypes);
      if (props.onConnectRejected !== undefined) {
        props.onConnectRejected({ reason, ...roles });
        return;
      }
      const text =
        reason === "cycle"
          ? m.cycleRejected
          : reason === "port"
            ? m.portRejected
            : reason === "self"
              ? m.selfRejected
              : reason === "duplicate"
                ? m.duplicateEdge
                : roles.sourceRole !== undefined && roles.targetRole !== undefined
                  ? format(m.noKindRejectedRoles, { source: roles.sourceRole, target: roles.targetRole })
                  : m.noKindRejected;
      showToast({ text });
    },
    [graph, nodeTypes, props, m, showToast],
  );

  /** 종류가 정해진 뒤의 연결: 포트·중복·흐름 순환을 디스크립터로 검사하고 엣지를 만든다. */
  const finishConnection = useCallback(
    (c: Connection, kind: string, inferred = false) => {
      const verdict = checkConnection(graph, c, portsLookup, { edgeTypes, kind });
      if (!verdict.ok) {
        if (verdict.reason === "duplicate") {
          select({ nodeIds: [], edgeIds: [verdict.existingEdgeId] });
          setAnnounce(m.duplicateEdge);
        } else reject(verdict.reason, c);
        return;
      }
      setLastKind(kind);
      const { graph: next, edgeId } = addEdge(graph, c, kind, idFactory);
      emit(next, "connect");
      select({ nodeIds: [], edgeIds: [edgeId] });
      if (inferred) {
        // 포트를 자동으로 정했으므로 어느 포트에 붙었는지 알리고, 틀리면 바로 되돌릴 수 있게 한다
        const text = format(m.connectedInferred, { source: portLabelOf(c.source.node, "out", c.source.port), target: portLabelOf(c.target.node, "in", c.target.port) });
        setAnnounce(text);
        showToast({ text, undo: { previous: graph, after: next } });
      } else setAnnounce(m.connected);
    },
    [graph, portsLookup, portLabelOf, edgeTypes, idFactory, emit, select, reject, showToast, m],
  );

  /**
   * 노드 어디서나 연결(UX-P11): 시작/끝이 포트 핸들이 아니라 노드(가장자리 띠·몸체)일 때, 포트와 종류를 추론해 연결한다.
   * 시작 쪽이 출발이고(핸들 방향이 있으면 그것을 따른다), 포트는 `default_ports` -> 첫 호환 포트 순으로 정한다.
   * 후보 종류가 둘 이상이면 기존 선택 UI에 포트 열을 더해 한 번에 고른다.
   */
  const connectInferred = useCallback(
    (start: ConnectEnd, end: ConnectEnd) => {
      if (readOnly) return;
      const ends = resolveEnds(start, end);
      if (ends === undefined || ends.source.node === ends.target.node) return;
      const sType = nodesOf(graph).find((n) => n.id === ends.source.node)?.type ?? "";
      const tType = nodesOf(graph).find((n) => n.id === ends.target.node)?.type ?? "";
      const blank: Connection = { source: { node: ends.source.node, port: ends.source.port ?? "" }, target: { node: ends.target.node, port: ends.target.port ?? "" } };
      const candidates = candidateEdgeKinds(sType, tType, edgeTypes, nodeTypes);
      if (candidates.length === 0) return reject("no-kind", blank);
      const inferred = inferKindPorts(graph, ends, candidates, edgeTypes, portsLookup);
      if (inferred.items.length === 0) {
        if (inferred.duplicateEdgeId !== undefined) {
          select({ nodeIds: [], edgeIds: [inferred.duplicateEdgeId] });
          setAnnounce(m.duplicateEdge);
          return;
        }
        return reject("port", blank);
      }
      const byKind = new Map(inferred.items.map((i) => [i.kind, i.connection] as const));
      const usable = candidates.filter((k) => byKind.has(k.id));
      const first = byKind.get((usable[0] as EdgeTypeDescriptor).id) as Connection;
      const plan = planConnection({
        graph,
        connection: first,
        candidates: usable,
        edgeTypes,
        preferredKind: lastKind !== undefined && usable.some((t) => t.id === lastKind) ? lastKind : props.defaultEdgeKind,
        ...endpointRoles(sType, tType, nodeTypes),
        cycleNeededText: m.connectCycleNeeded,
      });
      if (plan.mode === "none") return reject("no-kind", blank);
      if (plan.mode === "cycle-rejected") return reject("cycle", blank);
      if (plan.mode === "auto") return finishConnection(byKind.get(plan.kind) as Connection, plan.kind, true);
      const info: Record<string, EdgeKindCandidateInfo> = {};
      for (const k of plan.candidates) {
        const c = byKind.get(k.id);
        const portsText = c === undefined ? undefined : format(m.edgeKindPorts, { source: portLabelOf(c.source.node, "out", c.source.port), target: portLabelOf(c.target.node, "in", c.target.port) });
        info[k.id] = { ...plan.info[k.id], ...(portsText !== undefined ? { portsText } : {}) };
      }
      setPending({ c: first, candidates: plan.candidates, preselected: plan.preselected, info, byKind });
    },
    [readOnly, graph, edgeTypes, nodeTypes, props.defaultEdgeKind, lastKind, portsLookup, portLabelOf, finishConnection, reject, select, m],
  );

  /** 연결 시작점(끝에서 포트 핸들이 아닌 곳에 놓였을 때 몸체 드롭을 처리하려고 기억한다). */
  const connectFrom = useRef<ConnectEnd | null>(null);
  const onConnectStart = useCallback((_ev: unknown, p: OnConnectStartParams) => {
    setConnecting(true);
    connectFrom.current = p.nodeId === null ? null : { node: p.nodeId, ...(parseHandleId(p.handleId) !== undefined ? { port: parseHandleId(p.handleId) as { side: "in" | "out"; port: string } } : {}) };
  }, []);
  const onConnectEnd = useCallback(
    (ev: MouseEvent | TouchEvent, state: FinalConnectionState) => {
      setConnecting(false);
      const start = connectFrom.current;
      connectFrom.current = null;
      // 핸들에 놓였으면 onConnect가 처리했다. 빈 곳은 무시, 다른 노드의 몸체에 놓였을 때만 추론한다
      if (start === null || state.isValid === true) return;
      const pt = pointOf(ev);
      const target = pt === undefined ? undefined : nodeIdAtPoint(pt.x, pt.y);
      if (target !== undefined && target !== start.node) connectInferred(start, { node: target });
    },
    [connectInferred],
  );

  const onConnect = useCallback(
    (conn: FlowConnection) => {
      if (readOnly) return;
      const a = parseHandleId(conn.sourceHandle);
      const b = parseHandleId(conn.targetHandle);
      // 가장자리 띠에서 시작해 포트 핸들에 놓았다: 띠 쪽 포트는 추론한다
      if (isBandHandle(conn.sourceHandle) || isBandHandle(conn.targetHandle)) {
        connectInferred({ node: conn.source, ...(a !== undefined ? { port: a } : {}) }, { node: conn.target, ...(b !== undefined ? { port: b } : {}) });
        return;
      }
      if (a === undefined || b === undefined || a.side === b.side) return;
      // 입력→출력 방향으로 시작해도 허용하고 소스/타깃을 정규화한다.
      const c: Connection =
        a.side === "out"
          ? { source: { node: conn.source, port: a.port }, target: { node: conn.target, port: b.port } }
          : { source: { node: conn.target, port: b.port }, target: { node: conn.source, port: a.port } };
      if (c.source.node === c.target.node) return reject("self", c);
      const sType = nodesOf(graph).find((n) => n.id === c.source.node)?.type ?? "";
      const tType = nodesOf(graph).find((n) => n.id === c.target.node)?.type ?? "";
      const candidates = candidateEdgeKinds(sType, tType, edgeTypes, nodeTypes);
      if (candidates.length === 0) return reject("no-kind", c);
      // 포트 존재·방향은 종류와 무관하므로 선택 UI를 띄우기 전에 걸러낸다
      const early = checkConnection(graph, c, portsLookup, { edgeTypes, kind: (candidates[0] as EdgeTypeDescriptor).id });
      if (!early.ok && early.reason === "port") return reject("port", c);
      // 흐름 순환을 닫는 연결은 디스크립터 `cycle`이 있는 종류만 고를 수 있다(나머지 흐름 종류는 비활성 행)
      const plan = planConnection({
        graph,
        connection: c,
        candidates,
        edgeTypes,
        preferredKind: lastKind !== undefined && candidates.some((t) => t.id === lastKind) ? lastKind : props.defaultEdgeKind,
        ...endpointRoles(sType, tType, nodeTypes),
        cycleNeededText: m.connectCycleNeeded,
      });
      if (plan.mode === "none") return reject("no-kind", c);
      if (plan.mode === "cycle-rejected") return reject("cycle", c);
      if (plan.mode === "auto") finishConnection(c, plan.kind);
      else setPending({ c, candidates: plan.candidates, preselected: plan.preselected, info: plan.info });
    },
    [readOnly, graph, edgeTypes, nodeTypes, props.defaultEdgeKind, lastKind, portsLookup, finishConnection, connectInferred, reject, m],
  );

  const isValidConnection = useCallback((c: { source: string; target: string; sourceHandle?: string | null; targetHandle?: string | null }) => {
    const a = parseHandleId(c.sourceHandle);
    const b = parseHandleId(c.targetHandle);
    if (c.source === c.target) return false;
    // 가장자리 띠는 시작점일 뿐이다: 상대가 포트 핸들이면 방향은 추론 단계에서 정한다
    if (isBandHandle(c.sourceHandle) || isBandHandle(c.targetHandle)) return a !== undefined || b !== undefined;
    return a !== undefined && b !== undefined && a.side !== b.side;
  }, []);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      let selNodes: Set<string> | null = null;
      let nextOverrides: Map<string, Point> | null = null;
      let nextMeasured: Map<string, { width: number; height: number }> | null = null;
      const commit = new Set<string>();
      for (const c of changes) {
        if (c.type === "select") {
          selNodes ??= new Set((pendingSelection.current ?? eff).nodeIds);
          if (c.selected) selNodes.add(c.id);
          else selNodes.delete(c.id);
        } else if (c.type === "dimensions" && c.dimensions !== undefined) {
          const cur = measured.get(c.id);
          if (cur?.width !== c.dimensions.width || cur?.height !== c.dimensions.height) {
            nextMeasured ??= new Map(measured);
            nextMeasured.set(c.id, { width: c.dimensions.width, height: c.dimensions.height });
          }
        } else if (c.type === "position" && !readOnly) {
          if (c.position !== undefined) {
            nextOverrides ??= new Map(overrides);
            nextOverrides.set(c.id, c.position);
          }
          if (c.dragging !== true) commit.add(c.id);
        }
      }
      if (nextMeasured !== null) setMeasured(nextMeasured);
      if (selNodes !== null) select({ nodeIds: [...selNodes], edgeIds: selNodes.size > 0 ? [] : (pendingSelection.current ?? eff).edgeIds });
      if (nextOverrides !== null) {
        setOverrides(nextOverrides);
        if (commit.size > 0) {
          const positions = new Map<string, Point>();
          for (const id of commit) {
            const p = nextOverrides.get(id);
            if (p !== undefined) positions.set(id, p);
          }
          if (positions.size > 0) emit(moveNodesWithWaypoints(graph, positions), "move");
        }
      }
    },
    [eff, measured, overrides, readOnly, select, emit, graph],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      let sel: Set<string> | null = null;
      for (const c of changes) {
        if (c.type !== "select") continue;
        sel ??= new Set((pendingSelection.current ?? eff).edgeIds);
        if (c.selected) sel.add(c.id);
        else sel.delete(c.id);
      }
      if (sel !== null) select({ nodeIds: sel.size > 0 ? [] : (pendingSelection.current ?? eff).nodeIds, edgeIds: [...sel] });
    },
    [eff, select],
  );

  // ---- 첫 맞춤: 컨테이너 크기가 정해지고 노드 측정이 끝날 때까지 다시 시도 ----
  // React Flow의 첫 fitView는 컨테이너 크기가 0이거나 노드가 아직 측정되기 전에 끝날 수 있다. onlyRenderVisibleElements 때문에
  // 그러면 보이는 영역 밖 노드가 그려지지(=측정되지) 않은 채 멈춘다. 크기가 확정된 뒤 짧은 간격으로 몇 번 다시 맞추되,
  // 뷰가 "처음 상태"이거나 "우리가 마지막으로 맞춘 그대로"(= 사용자가 움직이지 않음)일 때만, 그리고 노드가 모두 측정되면 멈춘다.
  const sized = useStore((st) => st.width > 0 && st.height > 0);
  // 캔버스 크기(10px 단위). 옆 패널·팔레트가 열리거나 닫혀 크기가 바뀌면 처음 몇 초 동안은 다시 맞춘다.
  const canvasSize = useStore((st) => `${Math.round(st.width / 10)}x${Math.round(st.height / 10)}`);
  const mountedAt = useRef<number | null>(null);
  const firstSize = useRef<string | null>(null);
  const nodesMeasured = useNodesInitialized();
  const lastFit = useRef<{ x: number; y: number; zoom: number } | null>(null);
  const lastFitSize = useRef<string | null>(null);
  const hasNodes = gNodes.length > 0;
  useEffect(() => {
    if (!sized || !hasNodes) return;
    mountedAt.current ??= Date.now();
    firstSize.current ??= canvasSize;
    // 첫 몇 초가 지난 뒤에는 캔버스 크기가 바뀐 경우(옆 패널 열고 닫기)만 다시 맞춘다. 사용자가 움직였으면 attempt가 건드리지 않는다.
    if (lastFit.current !== null && Date.now() - mountedAt.current > REFIT_WINDOW_MS && lastFitSize.current === canvasSize) return;
    const same = (a: { x: number; y: number; zoom: number }, b: { x: number; y: number; zoom: number }) => a.x === b.x && a.y === b.y && a.zoom === b.zoom;
    const attempt = () => {
      const v = flow.getViewport();
      // React Flow 자체 첫 맞춤은 옆 패널이 자리 잡기 전의 작은 캔버스로 끝날 수 있다. 처음 크기에서 바뀌었고 우리가 아직 맞추지 않았다면 처음 3초 안에는 다시 맞춘다.
      const resized = firstSize.current !== canvasSize;
      const untouched = (v.x === 0 && v.y === 0 && v.zoom === 1) || (lastFit.current !== null ? same(v, lastFit.current) : resized);
      if (!untouched) return;
      void fitReadable(flow, flowStore.getState(), 0, insetRef.current).then(() => {
        lastFit.current = flow.getViewport();
        lastFitSize.current = canvasSize;
      });
    };
    const timers = FIRST_FIT_RETRY_MS.map((ms) => setTimeout(attempt, ms));
    return () => timers.forEach(clearTimeout);
    // 크기가 처음 확정되는 때(sized)와 노드가 처음 생기는 때, 측정이 끝나는 때, 캔버스 크기가 바뀔 때만
  }, [sized, hasNodes, nodesMeasured, canvasSize, flow, flowStore]);

  // ---- 외부 포커스 요청(이슈 행 클릭 등) ----
  const focusReq = props.focusRequest;
  const focusKey = focusReq === undefined ? undefined : `${typeof focusReq.token}:${focusReq.token}\u0000${focusReq.nodeId}\u0000${focusReq.edgeId ?? ""}`;
  const [seenFocus, setSeenFocus] = useState<string | undefined>(undefined);
  // 연결 요청: `edgeId`가 있고 그 연결이 있으면 노드가 아니라 그 연결을 선택하고 양 끝 노드를 화면에 맞춘다
  const focusEdge = focusReq?.edgeId === undefined ? undefined : edgesOf(graph).find((x) => x.id === focusReq.edgeId);
  if (seenFocus !== focusKey) {
    setSeenFocus(focusKey);
    if (focusReq !== undefined && focusEdge !== undefined) setSelection({ nodeIds: [], edgeIds: [focusEdge.id] });
    else if (focusReq !== undefined && existingIds.has(focusReq.nodeId)) setSelection({ nodeIds: [focusReq.nodeId], edgeIds: [] });
  }
  useEffect(() => {
    if (focusKey === undefined || focusReq === undefined) return;
    if (focusEdge !== undefined) {
      onSelectionChange?.({ nodeIds: [], edgeIds: [focusEdge.id] });
      void flow.fitView({ nodes: [{ id: focusEdge.source.node }, { id: focusEdge.target.node }], duration: 0, maxZoom: 1.25, padding: 0.5 });
      return;
    }
    if (!existingIds.has(focusReq.nodeId)) return;
    onSelectionChange?.({ nodeIds: [focusReq.nodeId], edgeIds: [] });
    void flow.fitView({ nodes: [{ id: focusReq.nodeId }], duration: 0, maxZoom: 1.25, padding: 0.5 });
    // 요청(token)이 바뀔 때만 실행
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusKey]);

  // ---- 연결 종류 바꾸기(`T`) ----
  const openKindChange = (edge: EdgeSpec): void => {
    const sType = nodesOf(graph).find((n) => n.id === edge.source.node)?.type ?? "";
    const tType = nodesOf(graph).find((n) => n.id === edge.target.node)?.type ?? "";
    const candidates = candidateEdgeKinds(sType, tType, edgeTypes, nodeTypes);
    const current = edgeTypes.filter((t) => t.id === edge.kind).reduce<EdgeTypeDescriptor | undefined>((a, b) => (a === undefined || (b.version ?? 0) >= (a.version ?? 0) ? b : a), undefined);
    if (current !== undefined && !candidates.some((t) => t.id === current.id)) candidates.unshift(current);
    if (candidates.length < 2) {
      setAnnounce(m.kindChangeNone);
      return;
    }
    // 이 연결을 뺀 그래프에서 새 종류가 흐름 순환을 닫는가: 반복 종류만 허용
    const without: Graph = { ...graph, edges: edgesOf(graph).filter((x) => x.id !== edge.id) };
    const info: Record<string, EdgeKindCandidateInfo> = {};
    for (const t of candidates) {
      if (!closesFlowLoop(without, { kind: t.id, source: edge.source, target: edge.target }, edgeTypes)) continue;
      info[t.id] = t.cycle !== null && t.cycle !== undefined ? {} : { disabledReason: m.connectCycleNeeded };
    }
    setKindChange({ edgeId: edge.id, candidates, preselected: edge.kind, info });
  };

  // ---- 키보드·드롭 ----
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (isTextField(e.target)) return;
    if ((e.key === "v" || e.key === "V") && !e.ctrlKey && !e.metaKey && !e.altKey && hasResourceTypes) {
      e.preventDefault();
      setShowResources(!showResources);
      return;
    }
    // 정의 바인딩 노드의 [열기]: 노드가 포커스·선택이면 Alt+Enter(읽기 전용에서도 동작)
    if (e.altKey && !e.ctrlKey && !e.metaKey && e.key === "Enter") {
      const focused = e.target instanceof Element ? (e.target.closest(".react-flow__node")?.getAttribute("data-id") ?? null) : null;
      const id = focused ?? onlyNodeId;
      const open = id === null ? undefined : props.bindSummaries?.[id]?.open;
      if (id !== null && open !== undefined && open.disabledReason === undefined) {
        e.preventDefault();
        open.onOpen();
        setAnnounce(format(m.bindOpenAnnounce, { label: gNodes.find((n) => n.id === id)?.label ?? id }));
        return;
      }
    }
    if (readOnly) return;
    if ((e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey)) && !e.ctrlKey && !e.metaKey && !e.altKey) {
      if (openEdgeMenuFromKeyboard(e.target)) e.preventDefault();
      return;
    }
    if ((e.key === "l" || e.key === "L") && !e.ctrlKey && !e.metaKey && !e.altKey && tidy.available) {
      e.preventDefault();
      tidy.setOpen(true);
      return;
    }
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "z") {
      const next = e.shiftKey ? history.redo(graph) : history.undo(graph);
      if (next !== null) {
        e.preventDefault();
        onChange?.(next, { reason: "undo", previous: graph });
        setAnnounce(e.shiftKey ? m.layoutRedone : m.layoutUndone);
      }
      return;
    }
    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "y") {
      const next = history.redo(graph);
      if (next !== null) {
        e.preventDefault();
        onChange?.(next, { reason: "undo", previous: graph });
        setAnnounce(m.layoutRedone);
      }
      return;
    }
    if (onlyNodeId !== null && !e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "r" || e.key === "R")) {
      e.preventDefault();
      rotateDirection(onlyNodeId, e.shiftKey ? -1 : 1);
      return;
    }
    if (onlyEdgeId !== null && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const edge = edgesOf(graph).find((x) => x.id === onlyEdgeId);
      if (edge !== undefined) {
        if (e.key === "s" || e.key === "S") {
          e.preventDefault();
          const next = cycleShape(edgeShapes.list.map((s) => s.id), edge.layout?.shape, e.shiftKey ? -1 : 1);
          emit(patchEdgeLayout(graph, edge.id, { shape: next }), "layout");
          const title = next === null ? format(m.shapeInherited, { title: inheritedEdgeShape(edge, edgeTypes.find((t) => t.id === edge.kind), { graph, ...(layoutDefaults !== undefined ? { layoutDefaults: layoutDefaults } : {}) }, edgeShapes).title }) : (edgeShapes.get(next)?.title ?? next);
          setAnnounce(format(m.shapeChanged, { title }));
          return;
        }
        if (e.key === "t" || e.key === "T") {
          e.preventDefault();
          openKindChange(edge);
          return;
        }
        if (e.key === "x" || e.key === "X") {
          e.preventDefault();
          emit(patchEdgeLayout(graph, edge.id, RESET_PATH_PATCH), "layout");
          setAnnounce(m.pathReset);
          return;
        }
        if (e.key === "Enter" && e.target instanceof Element && e.target.closest(".react-flow__edge") !== null) {
          e.preventDefault();
          setPathEditId(edge.id);
          setAnnounce(m.pathEditStarted);
          return;
        }
      }
    }
    if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      removeSelected();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "d") {
      e.preventDefault();
      duplicateSelected();
    }
  };
  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    if (!readOnly && e.dataTransfer.types.includes(PALETTE_DRAG_MIME)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  };
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    const typeId = e.dataTransfer.getData(PALETTE_DRAG_MIME);
    if (readOnly || typeId === "") return;
    e.preventDefault();
    let definition: { id: string; name: string } | undefined;
    const raw = e.dataTransfer.getData(PALETTE_DEFINITION_MIME);
    if (raw !== "") {
      try {
        const parsed = JSON.parse(raw) as { id?: unknown; name?: unknown };
        if (typeof parsed.id === "string" && typeof parsed.name === "string") definition = { id: parsed.id, name: parsed.name };
      } catch {
        definition = undefined;
      }
    }
    addByType(typeId, flow.screenToFlowPosition({ x: e.clientX, y: e.clientY }), definition);
  };

  // ---- 입구/답변/묻기 단축 조작 · 이슈 제안 ----
  const toggleCtx: ToggleContext = useMemo(
    () => ({ nodeTypes, edgeTypes, idFactory, portsOf: (id: string) => model.specs.get(id) }),
    [nodeTypes, edgeTypes, idFactory, model.specs],
  );
  const toggleInfos = useCallback(
    (nodeId: string): Record<RoleToggle, ToggleInfo> => ({
      entry: getRoleToggleInfo(nodeId, "entry", graph, toggleCtx),
      exit: getRoleToggleInfo(nodeId, "exit", graph, toggleCtx),
      interaction: getRoleToggleInfo(nodeId, "interaction", graph, toggleCtx),
    }),
    [graph, toggleCtx],
  );
  const { onRoleToggle, onApplySuggestion } = props;
  const toggleRole = useCallback(
    (nodeId: string, toggle: RoleToggle, on: boolean, options?: ToggleOptions): boolean => {
      if (readOnly) return false;
      const res = applyRoleToggle(graph, nodeId, toggle, on, toggleCtx, options);
      if (!res.changed) return false;
      emit(res.graph, "role-toggle");
      setAnnounce(on ? m.roleToggleAdded : m.roleToggleRemoved);
      onRoleToggle?.(nodeId, toggle, on, options);
      return true;
    },
    [readOnly, graph, toggleCtx, emit, m, onRoleToggle],
  );
  const applySuggestion = useCallback(
    (issue: Issue, suggestion: IssueSuggestion): boolean => {
      if (readOnly) return false;
      const res = applyGraphPatch(graph, suggestion.patch);
      if (res.addedNodeIds.length + res.addedEdgeIds.length + res.removedEdgeIds.length === 0) return false;
      emit(res.graph, "apply-suggestion");
      onApplySuggestion?.(issue, suggestion); // 실제로 적용된 뒤에만 알린다
      const newEdge = res.graph.edges?.find((e) => e.id === res.addedEdgeIds[0]);
      if (newEdge !== undefined) {
        select({ nodeIds: [], edgeIds: [newEdge.id] });
        setFitRequest({ ids: [newEdge.source.node, newEdge.target.node], token: (fitRequest?.token ?? 0) + 1 });
      } else if (res.addedNodeIds.length > 0) {
        select({ nodeIds: res.addedNodeIds, edgeIds: [] });
        setFitRequest({ ids: res.addedNodeIds, token: (fitRequest?.token ?? 0) + 1 });
      }
      setAnnounce(m.suggestionApplied);
      return true;
    },
    [readOnly, graph, emit, select, m, onApplySuggestion, fitRequest],
  );
  useEffect(() => {
    if (fitRequest === null) return;
    void flow.fitView({ nodes: fitRequest.ids.map((id) => ({ id })), duration: 0, maxZoom: 1.25, padding: 0.5 });
    // 요청(token)이 바뀔 때만 실행
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitRequest?.token]);
  useImperativeHandle(
    props.handleRef,
    () => ({
      getRoleToggleInfo: toggleInfos,
      toggleRole,
      applySuggestion,
      canHaveResources: (nodeId: string) => {
        const n = nodesOf(graph).find((x) => x.id === nodeId);
        return n !== undefined && canHaveResources(n, nodeTypes, edgeTypes);
      },
      addNodeAtCenter: (typeId: string, definition?: { id: string; name: string }) => {
        const box = canvasRef.current?.querySelector<HTMLElement>(".react-flow")?.getBoundingClientRect();
        let position: Point | undefined;
        if (box !== undefined && box.width > 0 && box.height > 0) {
          const c = flow.screenToFlowPosition({ x: box.left + box.width / 2, y: box.top + box.height / 2 });
          // 노드 카드 크기의 절반만큼 왼쪽 위로 옮겨 카드 중심이 화면 중앙에 오게 한다
          position = centerFreePosition(graph, { x: c.x - CARD_HALF_W, y: c.y - CARD_HALF_H }, grid);
        }
        const nodeId = addByType(typeId, position, definition);
        // 중앙에 놓았어도 큰 줌에서는 카드가 잘릴 수 있다: 측정된 뒤 화면 안에 안 들어오면 맞춘다
        if (nodeId !== undefined) setReveal((r) => ({ id: nodeId, label: definition?.name ?? typeId, token: (r?.token ?? 0) + 1 }));
        return nodeId;
      },
    }),
    [toggleInfos, toggleRole, applySuggestion, graph, nodeTypes, edgeTypes, flow, grid, addByType],
  );

  // ---- 연결선 우클릭 메뉴 · 다중 선택 배치(graph-edges §1.4·§2.4·§3.4) ----
  const shapeValueOf = (ids: readonly string[]): string | null => {
    const set = new Set(edgesOf(graph).filter((e) => ids.includes(e.id)).map((e) => e.layout?.shape ?? ""));
    return set.size === 1 ? ([...set][0] as string) : null;
  };
  const applyShapeTo = (ids: readonly string[], shapeId: string | null): void => {
    if (readOnly || ids.length === 0) return;
    const next = patchEdgesLayout(graph, ids, { shape: shapeId });
    if (next === graph) return;
    emit(next, "layout");
    const first = edgesOf(graph).find((e) => e.id === ids[0]);
    const title =
      shapeId === null
        ? format(m.shapeInherited, { title: first === undefined ? "" : inheritedEdgeShape(first, edgeTypes.find((t) => t.id === first.kind), { graph, ...(layoutDefaults !== undefined ? { layoutDefaults: layoutDefaults } : {}) }, edgeShapes).title })
        : (edgeShapes.get(shapeId)?.title ?? shapeId);
    setAnnounce(format(m.shapeChanged, { title }));
  };
  const resetPathsOf = (ids: readonly string[]): void => {
    if (readOnly || ids.length === 0) return;
    if (countResettableEdges(graph, ids) === 0) {
      setAnnounce(m.routeResetNothing);
      return;
    }
    emit(patchEdgesLayout(graph, ids, RESET_PATH_PATCH), "layout");
    setAnnounce(m.pathReset);
  };
  const applyDirectionTo = (ids: readonly string[], directionId: string | null): void => {
    if (readOnly || ids.length === 0) return;
    const next = patchNodesLayout(graph, ids, { direction: directionId });
    if (next === graph) return;
    emit(next, "layout");
    setAnnounce(format(m.directionChanged, { title: directionId === null ? m.nodeLayoutInherit : (m.directionLabels[directionId] ?? directionId) }));
  };
  const focusEdgeElement = (edgeId: string): void => {
    const el = canvasRef.current?.querySelector<HTMLElement>(`.react-flow__edge[data-id="${CSS.escape(edgeId)}"]`);
    (el ?? canvasRef.current?.querySelector<HTMLElement>(".react-flow__renderer, .react-flow"))?.focus();
  };
  const openEdgeMenu = (clientX: number, clientY: number, edgeId: string): void => {
    if (readOnly) return;
    const ids = eff.edgeIds.includes(edgeId) && eff.edgeIds.length > 1 && eff.nodeIds.length === 0 ? eff.edgeIds : [edgeId];
    if (ids.length === 1 && !(eff.edgeIds.length === 1 && eff.edgeIds[0] === edgeId)) select({ nodeIds: [], edgeIds: [edgeId] });
    const rect = canvasRef.current?.getBoundingClientRect();
    setMenu({ at: { x: Math.max(0, clientX - (rect?.left ?? 0)), y: Math.max(0, clientY - (rect?.top ?? 0)) }, edgeIds: [...ids] });
  };
  /** 키보드(`Shift+F10`·ContextMenu 키): 선택한 연결선의 가운데(없으면 캔버스 가운데)에 연다 */
  const openEdgeMenuFromKeyboard = (target: EventTarget | null): boolean => {
    if (readOnly || eff.edgeIds.length === 0 || eff.nodeIds.length > 0) return false;
    const first = eff.edgeIds[0] as string;
    const el = target instanceof Element ? target.closest<HTMLElement>(".react-flow__edge") : null;
    const anchor = el ?? canvasRef.current?.querySelector<HTMLElement>(`.react-flow__edge[data-id="${CSS.escape(first)}"]`) ?? null;
    const r = anchor?.getBoundingClientRect();
    const c = canvasRef.current?.getBoundingClientRect();
    const x = r !== undefined && r.width > 0 ? r.left + r.width / 2 : (c?.left ?? 0) + (c?.width ?? 0) / 2;
    const y = r !== undefined && r.height > 0 ? r.top + r.height / 2 : (c?.top ?? 0) + (c?.height ?? 0) / 2;
    openEdgeMenu(x, y, (el?.getAttribute("data-id") && eff.edgeIds.includes(el.getAttribute("data-id") as string) ? (el.getAttribute("data-id") as string) : first));
    return true;
  };
  const menuIds = menu === null ? [] : menu.edgeIds.filter((id) => edgesOf(graph).some((e) => e.id === id));
  const closeMenu = (): void => {
    const id = menu?.edgeIds[0];
    setMenu(null);
    if (id !== undefined) focusEdgeElement(id);
  };
  const multiLayout: MultiLayoutPanelProps | undefined = useMemo(() => {
    if (eff.edgeIds.length > 1 && eff.nodeIds.length === 0) {
      return {
        edges: {
          count: eff.edgeIds.length,
          shapes: edgeShapes.list,
          shape: shapeValueOf(eff.edgeIds),
          resettable: countResettableEdges(graph, eff.edgeIds),
          onShape: (id: string | null) => applyShapeTo(eff.edgeIds, id),
          onResetPaths: () => resetPathsOf(eff.edgeIds),
        },
        readOnly,
        messages: m,
      };
    }
    if (eff.nodeIds.length > 1 && eff.edgeIds.length === 0) {
      const set = new Set(nodesOf(graph).filter((n) => eff.nodeIds.includes(n.id)).map((n) => n.layout?.direction ?? ""));
      return {
        nodes: {
          count: eff.nodeIds.length,
          directions: directionTable,
          direction: set.size === 1 ? ([...set][0] as string) : null,
          onDirection: (id: string | null) => applyDirectionTo(eff.nodeIds, id),
        },
        readOnly,
        messages: m,
      };
    }
    return undefined;
    // 콜백은 graph·eff·emit이 바뀔 때만 의미가 달라진다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eff, graph, edgeShapes, directionTable, readOnly, m, emit]);

  // ---- 설정 패널 슬롯 ----
  const multi = eff.nodeIds.length + eff.edgeIds.length;
  const selNode: NodeSpec | undefined = eff.nodeIds.length === 1 && multi === 1 ? gNodes.find((n) => n.id === eff.nodeIds[0]) : undefined;
  if (choiceFor !== null && choiceFor.nodeId !== selNode?.id) setChoiceFor(null); // 선택 노드가 바뀌면 후보 메뉴를 닫는다
  const selEdge: EdgeSpec | undefined = eff.edgeIds.length === 1 && multi === 1 ? edgesOf(graph).find((e) => e.id === eff.edgeIds[0]) : undefined;
  /** [+ 추가]가 만들 경유점 기본 위치: 두 끝 노드 중심의 가운데(격자에 맞춤) */
  const midpointOfNodes = (e: EdgeSpec): Point => {
    const centerOf = (id: string): Point => {
      const n = flow.getNode(id);
      const spec = gNodes.find((x) => x.id === id);
      const pos = n?.position ?? { x: spec?.position?.x ?? 0, y: spec?.position?.y ?? 0 };
      return { x: pos.x + (n?.measured?.width ?? n?.width ?? 0) / 2, y: pos.y + (n?.measured?.height ?? n?.height ?? 0) / 2 };
    };
    const a = centerOf(e.source.node);
    const b = centerOf(e.target.node);
    return snap({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, grid);
  };
  const edgeLayoutProps = useMemo(
    () =>
      selEdge === undefined
        ? undefined
        : {
            layout: selEdge.layout ?? null,
            shapes: edgeShapes.list,
            inheritedShape: inheritedEdgeShape(selEdge, edgeTypes.find((t) => t.id === selEdge.kind), { graph, ...(layoutDefaults !== undefined ? { layoutDefaults: layoutDefaults } : {}) }, edgeShapes),
            newWaypoint: midpointOfNodes(selEdge),
            readOnly,
            messages: m,
            onChange: (next: EdgeLayout | null) => {
              if (readOnly) return;
              emit(setEdgeLayout(graph, selEdge.id, next), "layout");
            },
          },
    // midpointOfNodes는 렌더마다 새로 만들어지지만 값은 graph·measured가 정한다
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selEdge, edgeShapes, edgeTypes, graph, layoutDefaults, readOnly, m, emit, measured],
  );
  // 포트 목록은 노드를 끄는 동안에도 모델과 함께 다시 만들어진다. 내용이 같으면 같은 참조를 써서 패널 값이 흔들리지 않게 한다
  const rawSelPorts = selNode === undefined ? undefined : model.ports.get(selNode.id);
  const selPortsKey = rawSelPorts === undefined ? "" : JSON.stringify([rawSelPorts.inputs.map((p) => [p.id, p.label]), rawSelPorts.outputs.map((p) => [p.id, p.label])]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const selPorts = useMemo(() => rawSelPorts, [selPortsKey]);
  const nodeLayoutProps = useMemo(
    () =>
      selNode === undefined
        ? undefined
        : {
            ...nodeLayoutModel({
              graph,
              node: selNode,
              descriptor: pickDescriptor(selNode, nodeTypes),
              ports: selPorts,
              layoutDefaults: layoutDefaults,
              directions: props.directions,
            }),
            readOnly,
            messages: m,
            onChange: (next: NodeLayout | null) => {
              if (readOnly) return;
              emit(setNodeLayout(graph, selNode.id, next), "layout");
            },
            onMakeGraphDefault: (directionId: string) => {
              if (readOnly) return;
              emit(patchGraphUiLayout(graph, { direction: directionId }), "layout");
            },
          },
    [selNode, graph, nodeTypes, selPorts, layoutDefaults, props.directions, readOnly, m, emit],
  );
  const layoutPanels: LayoutPanels | null = useMemo(
    () =>
      nodeLayoutProps !== undefined && selNode !== undefined
        ? { node: { nodeId: selNode.id, props: nodeLayoutProps } }
        : edgeLayoutProps !== undefined && selEdge !== undefined
          ? { edge: { edgeId: selEdge.id, props: edgeLayoutProps } }
          : multiLayout !== undefined
            ? { multi: { edgeIds: [...eff.edgeIds], nodeIds: [...eff.nodeIds], props: multiLayout } }
            : null,
    [nodeLayoutProps, edgeLayoutProps, selNode, selEdge, multiLayout, eff],
  );
  const { onLayoutPanelsChange } = props;
  useEffect(() => {
    onLayoutPanelsChange?.(layoutPanels);
  }, [layoutPanels, onLayoutPanelsChange]);
  const panel =
    props.renderConfigPanel !== undefined && multi > 0
      ? props.renderConfigPanel({
          ...(selNode !== undefined
            ? {
                roleToggles: toggleInfos(selNode.id),
                onToggleRole: (toggle: RoleToggle, on: boolean, options?: ToggleOptions) => {
                  toggleRole(selNode.id, toggle, on, options);
                },
                canHaveResources: canHaveResources(selNode, nodeTypes, edgeTypes),
              }
            : {}),
          ...(selNode !== undefined ? { node: selNode } : {}),
          ...(selEdge !== undefined ? { edge: selEdge } : {}),
          ...(selNode !== undefined
            ? {
                descriptor: pickDescriptor(selNode, nodeTypes),
                ports: model.specs.get(selNode.id),
              }
            : {}),
          multi,
          onChangeNode: (patch) => {
            if (readOnly || selNode === undefined) return;
            emit(patchNode(graph, selNode.id, patch), Object.keys(patch).every((k) => k === "label") ? "edit-label" : "edit-config");
          },
          ...(edgeLayoutProps !== undefined ? { edgeLayout: edgeLayoutProps } : {}),
          ...(nodeLayoutProps !== undefined ? { nodeLayout: nodeLayoutProps } : {}),
          ...(multiLayout !== undefined ? { multiLayout } : {}),
          onChangeEdge: (patch) => {
            if (readOnly || selEdge === undefined) return;
            emit(patchEdge(graph, selEdge.id, patch), "edit-edge");
          },
          close: () => select(NO_SELECTION),
        })
      : null;

  const paletteOverlay = props.paletteOverlay === true;
  const showPalette = (props.showPalette ?? true) && !readOnly && (!paletteOverlay || props.paletteOpen === true);
  const showMinimap = props.showMinimap ?? true;
  const onShowMinimapChange = props.onShowMinimapChange;
  // 오버레이 팔레트가 열리면 검색 입력으로 포커스를 옮긴다(키보드로 이어서 쓰고 Esc로 닫는다)
  const overlayOpen = paletteOverlay && props.paletteOpen === true;
  useEffect(() => {
    if (!overlayOpen) return;
    const el = rootRef.current?.querySelector<HTMLElement>('.ac-ge-palette-wrap[data-overlay="true"] input, .ac-ge-palette-wrap[data-overlay="true"] button');
    el?.focus();
  }, [overlayOpen]);
  const undoAvailable = toast?.undo !== undefined && sameGraph(graph, toast.undo.after);

  return (
    <div ref={rootRef} className={["ac-ge-root", props.className].filter(Boolean).join(" ")} style={props.style} data-readonly={readOnly ? "true" : undefined} data-connecting={connecting ? "true" : undefined} data-zoom-lod={lowZoom ? "icon" : undefined} data-zoom-title={titleBoost ? "boost" : undefined}>
      {showPalette && (
        <aside
          className="ac-ge-palette-wrap"
          data-overlay={paletteOverlay ? "true" : undefined}
          onKeyDown={(e) => {
            if (paletteOverlay && e.key === "Escape") {
              e.stopPropagation();
              props.onPaletteClose?.();
            }
          }}
        >
          <TeamPalette
            nodeTypes={nodeTypes}
            {...(props.definitionLists !== undefined ? { definitionLists: props.definitionLists } : {})}
            {...(props.definitionKindTitles !== undefined ? { definitionKindTitles: props.definitionKindTitles } : {})}
            onAdd={(spec) => addByType(spec.typeId, undefined, spec.definition)}
            messages={m}
            {...(props.palette ?? {})}
          />
        </aside>
      )}
      <div
        ref={canvasRef}
        className="ac-ge-canvas"
        role="application"
        aria-label={m.canvasLabel}
        onKeyDown={onKeyDown}
        onDragOver={onDragOver}
        onDrop={onDrop}
      >
        <svg className="ac-ge-defs" width="0" height="0" aria-hidden="true" focusable="false">
          <defs>
            <marker id={markerId} viewBox="0 0 12 12" markerWidth="12" markerHeight="12" refX="11" refY="6" orient="auto" markerUnits="userSpaceOnUse">
              <path d="M1 1 L11 6 L1 11 Z" fill="context-stroke" stroke="context-stroke" strokeLinejoin="round" />
            </marker>
          </defs>
        </svg>
        {tidy.showBar && <div className="ac-ge-tidy-bar" role="progressbar" aria-label={m.tidyRunning} />}
        {props.teamShared !== undefined && <TeamSharedBar {...props.teamShared} readOnly={readOnly} messages={m} />}
        <EdgeEditContext.Provider value={editApi}>
        <PortEditContext.Provider value={portEditApi}>
        <EdgeRouteContext.Provider value={routes}>
        <div className="ac-ge-flow">
          {activeView !== null && (
            <div className="ac-ge-view-chip" role="status">
              <span>{format(m.viewTemp, { title: activeView.short })}</span>
              <button type="button" className="ac-ge-btn" aria-label={m.viewTempClear} onClick={() => setViewShapeId(null)}>
                <span aria-hidden="true">×</span>
              </button>
            </div>
          )}
          {showTrouble && (
            <EdgeTroubleChip
              messages={m}
              count={troubleIds.length}
              {...(edgeShapes.has(DEFAULT_EDGE_SHAPE) ? { onAutoRoute: autoRouteTrouble } : {})}
              onDismiss={() => hideTrouble(true)}
            />
          )}
        <ReactFlow
          nodes={flowNodes}
          edges={viewEdges}
          nodeTypes={FLOW_NODE_TYPES}
          edgeTypes={FLOW_EDGE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onEdgeContextMenu={(ev, edge) => {
            if (readOnly) return;
            ev.preventDefault();
            openEdgeMenu(ev.clientX, ev.clientY, edge.id);
          }}
          onPaneClick={() => setMenu(null)}
          onConnectStart={onConnectStart}
          onConnectEnd={onConnectEnd}
          connectionRadius={CONNECTION_RADIUS}
          isValidConnection={isValidConnection}
          connectionMode={ConnectionMode.Loose}
          nodesDraggable={!readOnly}
          nodesConnectable={!readOnly}
          elementsSelectable
          deleteKeyCode={null}
          snapToGrid={grid !== false}
          snapGrid={[grid === false ? 1 : grid, grid === false ? 1 : grid]}
          multiSelectionKeyCode={["Shift", "Control", "Meta"]}
          onlyRenderVisibleElements
          minZoom={0.25}
          maxZoom={2}
          fitView
          fitViewOptions={FIT_VIEW_OPTIONS}
          proOptions={{ hideAttribution: true }}
          ariaLabelConfig={m.flowLabels}
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="var(--ac-canvas-dot)" />
          <Controls showInteractive={false} />
          {showMinimap && <MiniMap pannable zoomable style={MINIMAP_STYLE} className={onShowMinimapChange !== undefined ? "ac-ge-minimap--lifted" : undefined} />}
          {onShowMinimapChange !== undefined && (
            <Panel position="bottom-right" className="ac-ge-minimap-toggle-wrap">
              <button
                type="button"
                className="ac-ge-btn ac-ge-minimap-toggle"
                aria-pressed={showMinimap}
                aria-label={showMinimap ? m.minimapHide : m.minimapShow}
                title={showMinimap ? m.minimapHide : m.minimapShow}
                onClick={() => onShowMinimapChange(!showMinimap)}
              >
                <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
                  <rect x="1.5" y="2.5" width="13" height="11" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
                  <rect x="8" y="7" width="5" height="4.5" rx="0.8" fill="currentColor" />
                </svg>
              </button>
            </Panel>
          )}
          <OffscreenCue
            label={(n) => format(m.offscreenNodes, { count: n })}
            hint={m.offscreenHint}
            onShowAll={() => void flow.fitView({ padding: FIT_VIEW_OPTIONS.padding, maxZoom: 1, minZoom: 0.25, duration: 200 })}
          />
          {tidy.ghost}
          {(hasResourceTypes || tidy.available || viewable) && (
            <Panel position="bottom-center" className="ac-ge-view-toolbar">
              {hasResourceTypes && (
                <label className="ac-ge-check">
                  <input type="checkbox" checked={showResources} onChange={(e) => setShowResources(e.target.checked)} aria-keyshortcuts="V" />
                  <span>{m.showResources}</span>
                </label>
              )}
              {tidy.control}
              {viewable && (
                <label className="ac-ge-view-select">
                  <span>{m.viewEdges}</span>
                  <select value={activeView?.shapeId ?? ""} onChange={(e) => setViewShapeId(e.target.value === "" ? null : e.target.value)}>
                    <option value="">{m.viewStored}</option>
                    {viewOptions.map((o) => (
                      <option key={o.shapeId} value={o.shapeId}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </Panel>
          )}
          {!readOnly && props.canvasActions !== undefined && (
            <Panel position="top-left" className="ac-ge-actions">
              {props.canvasActions}
            </Panel>
          )}
          {!readOnly && multi > 0 && (
            <Panel position="top-left" className="ac-ge-toolbar">
              {selNode !== undefined &&
                ROLE_TOGGLES.map((t) => {
                  const info = toggleInfos(selNode.id)[t];
                  if (!info.available) return null;
                  const choices = toggleChoices(info);
                  const needsChoice = !info.on && choices.length > 1;
                  const menuOpen = needsChoice && choiceFor?.nodeId === selNode.id && choiceFor.toggle === t;
                  return (
                    <span key={t} className="ac-ge-toggle-wrap">
                      <button
                        type="button"
                        className="ac-ge-btn"
                        aria-pressed={info.on}
                        aria-haspopup={needsChoice ? "menu" : undefined}
                        aria-expanded={needsChoice ? menuOpen : undefined}
                        title={m.toolbarLabel.replace("{label}", selNode.label ?? selNode.id)}
                        onClick={() => {
                          if (needsChoice) setChoiceFor(menuOpen ? null : { nodeId: selNode.id, toggle: t });
                          else toggleRole(selNode.id, t, !info.on);
                        }}
                      >
                        {m.toggleLabels[t] ?? t}
                      </button>
                      {menuOpen && (
                        <span className="ac-ge-choice-menu" role="menu" aria-label={m.toggleChoose} onKeyDown={onChoiceMenuKeyDown}>
                          {choices.map((c, i) => (
                            <button
                              key={`${c.kindId}:${c.userNodeId}`}
                              type="button"
                              role="menuitem"
                              className="ac-ge-btn"
                              autoFocus={i === 0}
                              onClick={() => {
                                setChoiceFor(null);
                                toggleRole(selNode.id, t, true, { kindId: c.kindId, userNodeId: c.userNodeId });
                              }}
                            >
                              {info.kinds.length > 1 ? `${c.kindTitle} · ${c.userLabel}` : c.userLabel}
                            </button>
                          ))}
                        </span>
                      )}
                    </span>
                  );
                })}
              {selNode !== undefined && (
                <button type="button" className="ac-ge-btn" aria-keyshortcuts="R" title={m.rotateDirection} onClick={() => rotateDirection(selNode.id)}>
                  <span aria-hidden="true">⟳</span> {m.rotateDirection}
                </button>
              )}
              {eff.nodeIds.length + eff.edgeIds.length > 1 && <span className="ac-ge-toolbar-count">{format(m.selectedCount, { count: multi })}</span>}
              {eff.nodeIds.length > 0 && (
                <button type="button" className="ac-ge-btn" onClick={duplicateSelected}>
                  {m.duplicate}
                </button>
              )}
              <button type="button" className="ac-ge-btn ac-ge-btn--danger" onClick={removeSelected}>
                {m.remove}
              </button>
            </Panel>
          )}
        </ReactFlow>
        </div>
        </EdgeRouteContext.Provider>
        </PortEditContext.Provider>
        </EdgeEditContext.Provider>
        <div className="ac-ge-sr-only" role="status" aria-live="polite">
          {announce}
        </div>
        {menu !== null && menuIds.length > 0 && (
          <EdgeContextMenu
            at={menu.at}
            count={menuIds.length}
            shapes={edgeShapes.list}
            shape={shapeValueOf(menuIds)}
            resettable={countResettableEdges(graph, menuIds)}
            canEditPath={menuIds.length === 1 && model.edges.find((x) => x.id === menuIds[0])?.data?.shape.supportsWaypoints === true}
            readOnly={readOnly}
            messages={m}
            onShape={(id) => applyShapeTo(menuIds, id)}
            onResetPaths={() => resetPathsOf(menuIds)}
            onEditPath={() => {
              setPathEditId(menuIds[0] as string);
              setAnnounce(m.pathEditStarted);
            }}
            onDelete={() => {
              const next = removeSelection(graph, { nodeIds: [], edgeIds: menuIds });
              emit(next, "remove");
              select(NO_SELECTION);
              const text = format(m.removed, { count: menuIds.length });
              setAnnounce(text);
              showToast({ text, undo: { previous: graph, after: next } });
            }}
            onClose={closeMenu}
          />
        )}
        {toast !== null && (
          <div className="ac-ge-toast" role="status">
            <span className="ac-ge-toast-text ac-ellipsis">{toast.text}</span>
            {undoAvailable && toast.undo !== undefined && (
              <button
                type="button"
                className="ac-ge-btn ac-ge-btn--primary"
                onClick={() => {
                  if (toast.undo === undefined) return;
                  const restored = toast.undo.viaHistory === true ? history.undo(graph) : null;
                  onChange?.(restored ?? toast.undo.previous, { reason: "undo", previous: graph });
                  setToast(null);
                }}
              >
                {m.undo}
              </button>
            )}
          </div>
        )}
      </div>
      {panel !== null && <aside className="ac-ge-panel">{panel}</aside>}
      {kindChange !== null && (
        <EdgeKindDialog
          edgeTypes={kindChange.candidates}
          preselected={kindChange.preselected}
          info={kindChange.info}
          {...(props.delegationStrategies !== undefined ? { delegationStrategies: props.delegationStrategies } : {})}
          {...(props.renderIcon !== undefined ? { renderIcon: props.renderIcon } : {})}
          messages={m}
          onCancel={() => {
            setKindChange(null);
            focusEdgeElement(kindChange.edgeId);
          }}
          onConfirm={(kind) => {
            const change = kindChange;
            setKindChange(null);
            const edge = edgesOf(graph).find((x) => x.id === change.edgeId);
            if (edge !== undefined && kind !== edge.kind) {
              // 종류가 달라지면 이전 종류의 설정(config)은 새 종류의 스키마와 맞지 않으므로 비운다(생략 = 기본/상속)
              const changed: EdgeSpec = { ...edge, kind };
              delete changed.config;
              emit({ ...graph, edges: edgesOf(graph).map((x) => (x.id === edge.id ? changed : x)) }, "edit-edge");
              setAnnounce(format(m.kindChanged, { title: edgeTypes.find((t) => t.id === kind)?.title ?? kind }));
            }
            focusEdgeElement(change.edgeId);
          }}
        />
      )}
      {pending !== null && (
        <EdgeKindDialog
          edgeTypes={pending.candidates}
          preselected={pending.preselected}
          info={pending.info}
          {...(props.delegationStrategies !== undefined ? { delegationStrategies: props.delegationStrategies } : {})}
          {...(props.renderIcon !== undefined ? { renderIcon: props.renderIcon } : {})}
          messages={m}
          onCancel={() => setPending(null)}
          onConfirm={(kind) => {
            finishConnection(pending.byKind?.get(kind) ?? pending.c, kind, pending.byKind !== undefined);
            setPending(null);
          }}
        />
      )}
    </div>
  );
}
