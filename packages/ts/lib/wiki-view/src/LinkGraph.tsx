import type { WikiGraph } from "@agent-console/contracts/wiki";
import {
  Background, BaseEdge, Controls, EdgeLabelRenderer, Handle, Position, ReactFlow, ReactFlowProvider, useInternalNode, useNodesInitialized, useReactFlow,
  type Edge, type EdgeProps, type Node, type NodeProps,
} from "@xyflow/react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  createElkGraphLayout, edgeGeometry, graphToFlow, gridPositions, GRAPH_DEFAULTS, nearestNode, type ArrowDirection, type GraphEdgeData, type GraphFlowOptions, type GraphLayoutEngine,
  type GraphNodeData,
} from "./graph";
import { isComposingEvent, useDomId } from "./hooks";
import { formatMessage, resolveMessages } from "./messages";

type GraphNode = Node<GraphNodeData & { domId: string; focused: boolean }, "wiki-node">;
type GraphEdge = Edge<GraphEdgeData, "wiki-edge">;

/**
 * 배치가 끝나거나 노드가 새로 측정되면 화면에 맞춘다(첫 fitView는 배치 전 좌표로 끝나 노드를 잘라 보이게 한다). ReactFlow 자식으로 둔다.
 * 다 맞추면 `readableZoom`보다 작아지는 큰 그래프는 그 배율로 `focusId` 노드(중심 또는 첫 노드)를 화면 가운데에 두고 시작한다(글자가 읽히는 쪽 우선).
 */
function RefitOnLayout({ token, maxZoom, readableZoom, focusId }: { token: unknown; maxZoom: number; readableZoom: number; focusId: string | null }) {
  const rf = useReactFlow();
  const ready = useNodesInitialized();
  useEffect(() => {
    // 새 노드 좌표가 React Flow 저장소에 반영된 다음 프레임에 맞춘다
    const timer = setTimeout(() => {
      void rf.fitView({ maxZoom, duration: 0 }).then(() => {
        if (rf.getZoom() >= readableZoom - 1e-6) return;
        const n = focusId === null ? undefined : rf.getInternalNode(focusId);
        if (!n) return;
        const w = n.measured.width ?? 0;
        const h = n.measured.height ?? 0;
        void rf.setCenter(n.internals.positionAbsolute.x + w / 2, n.internals.positionAbsolute.y + h / 2, { zoom: readableZoom, duration: 0 });
      });
    }, 50);
    return () => clearTimeout(timer);
  }, [rf, ready, token, maxZoom, readableZoom, focusId]);
  return null;
}

function WikiNodeView({ data, selected }: NodeProps<GraphNode>) {
  const kind = data.broken ? "broken" : data.scheme ? "scheme" : data.orphan ? "orphan" : "page";
  const icon = data.broken ? "link-broken" : data.scheme ? "external-link" : data.orphan ? "page-orphan" : data.home ? "home" : "page";
  return (
    <div
      id={data.domId}
      className="ac-wk-gnode"
      data-kind={kind}
      data-center={data.center || undefined}
      data-home={data.home || undefined}
      data-focused={data.focused || undefined}
      data-selected={selected || undefined}
      title={`${data.title}\n${data.path}`}
      aria-label={data.ariaLabel}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} className="ac-wk-handle" />
      <span className="ac-wk-icon" data-icon={icon} aria-hidden="true" />
      <span className="ac-wk-ellipsis">{data.title}</span>
      <Handle type="source" position={Position.Right} isConnectable={false} className="ac-wk-handle" />
    </div>
  );
}

/** 노드 경계 사이를 잇는 선(핸들 위치가 아니라 노드 사각형 기준) + `×n` 라벨. 화살촉은 선과 같은 색(`currentColor`). */
function WikiEdgeView({ id, source, target, data }: EdgeProps<GraphEdge>) {
  const a = useInternalNode(source);
  const b = useInternalNode(target);
  if (!a || !b || !data) return null;
  const box = (n: typeof a) => ({ x: n.internals.positionAbsolute.x, y: n.internals.positionAbsolute.y, width: n.measured.width ?? n.width ?? GRAPH_DEFAULTS.nodeWidth, height: n.measured.height ?? n.height ?? GRAPH_DEFAULTS.nodeHeight });
  const g = edgeGeometry(box(a), box(b), data.bend);
  const markerId = `${id.replace(/[^a-zA-Z0-9_-]/g, "_")}-arrow`;
  return (
    <>
      <defs>
        <marker id={markerId} viewBox="0 0 10 10" refX="10" refY="5" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" orient="auto">
          <path className="ac-wk-garrow" data-center={data.touchesCenter || undefined} d="M 0 0 L 10 5 L 0 10 z" />
        </marker>
      </defs>
      <g className="ac-wk-gedge" data-center={data.touchesCenter || undefined}>
        <BaseEdge id={id} path={g.path} markerEnd={`url(#${markerId})`} />
      </g>
      {data.count >= 2 ? (
        <EdgeLabelRenderer>
          <span className="ac-wk-gcount" style={{ transform: `translate(-50%, -50%) translate(${g.mid.x}px, ${g.mid.y}px)` }}>×{data.count}</span>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

const nodeTypes = { "wiki-node": WikiNodeView };
const edgeTypes = { "wiki-edge": WikiEdgeView };

export interface LinkGraphProps {
  graph: WikiGraph;
  /** 중심 페이지 경로(없으면 전체 보기) */
  centerPath?: string | null;
  /** 선택(제어형) 노드 경로. 연결 목록과 서로 강조할 때 쓴다. */
  selectedPath?: string | null;
  onSelect?: (path: string) => void;
  /** 더블클릭·Enter: 그 노드를 연다(페이지/끊긴 대상/스킴 대상 구분은 호출자가 노드 값으로 한다) */
  onOpen?: (node: GraphNodeData) => void;
  /** Shift+Enter·C: 그 노드를 중심으로 삼는다 */
  onCenter?: (path: string) => void;
  /** 배치 엔진(기본 elkjs stress, 처음 필요할 때 불러옴). 실패하면 격자 배치로 남는다. */
  engine?: GraphLayoutEngine;
  /** 노드 크기·간격(px). 앱 토큰 값을 넘긴다. */
  nodeWidth?: number;
  nodeHeight?: number;
  gap?: number;
  /** 노드 이름(접근성) 만들기: 제목·경로 외에 상태 글을 붙인다 */
  ariaLabelOf?: NonNullable<GraphFlowOptions["ariaLabelOf"]>;
  height?: number | "fill";
  /** 처음 맞춤의 최대 배율(기본 1: 노드가 명세 크기보다 커 보이지 않게) */
  maxZoom?: number;
  /** 전체를 맞추면 이 배율보다 작아지는 큰 그래프는 이 배율로 중심 노드부터 보인다(기본 0.8). */
  readableZoom?: number;
  /** true면 `truncated` 안내 띠를 그리지 않는다(호출자가 도구줄·목록에서 한 번만 안내할 때) */
  hideTruncatedNotice?: boolean;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

const ARROWS: Readonly<Record<string, ArrowDirection>> = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };

function Inner({ graph, centerPath = null, selectedPath = null, onSelect, onOpen, onCenter, engine, nodeWidth, nodeHeight, gap, ariaLabelOf, height = "fill", maxZoom = 1, readableZoom = 0.8, hideTruncatedNotice = false, messages, className }: LinkGraphProps) {
  const t = resolveMessages(messages);
  const base = useDomId();
  const w = nodeWidth ?? GRAPH_DEFAULTS.nodeWidth;
  const h = nodeHeight ?? GRAPH_DEFAULTS.nodeHeight;
  const g = gap ?? GRAPH_DEFAULTS.gap;
  const flow = useMemo(
    () => graphToFlow(graph, { centerPath, nodeWidth: w, nodeHeight: h, ...(ariaLabelOf ? { ariaLabelOf } : {}) }),
    [graph, centerPath, w, h, ariaLabelOf],
  );
  const defaultEngine = useMemo(() => createElkGraphLayout(), []);
  const [placed, setPlaced] = useState<{ source: typeof flow; positions: Record<string, { x: number; y: number }> } | null>(null);
  const [failed, setFailed] = useState<typeof flow | null>(null);
  useEffect(() => {
    if (flow.nodes.length === 0) return;
    let cancelled = false;
    (engine ?? defaultEngine)({
      nodes: flow.nodes.map((n) => ({ id: n.id, width: n.width, height: n.height })),
      edges: flow.edges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
      gap: g,
    }).then(
      (positions) => {
        if (!cancelled) setPlaced({ source: flow, positions });
      },
      () => {
        if (!cancelled) setFailed(flow);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [flow, engine, defaultEngine, g]);

  const positions = useMemo(
    () => (placed && placed.source === flow ? placed.positions : gridPositions(flow.nodes, g)),
    [placed, flow, g],
  );
  const layouting = flow.nodes.length > 0 && !(placed && placed.source === flow) && failed !== flow;
  const order = useMemo(() => flow.nodes.map((n) => n.id), [flow]);
  const [focusId, setFocusId] = useState<string | null>(null);
  const firstId = centerPath && order.includes(centerPath) ? centerPath : (order[0] ?? null);
  const focused = focusId && order.includes(focusId) ? focusId : null;
  const domIdOf = (id: string) => `${base}-n${order.indexOf(id)}`;

  const nodes = useMemo<GraphNode[]>(
    () =>
      flow.nodes.map((n) => ({
        id: n.id,
        type: "wiki-node",
        position: positions[n.id] ?? { x: 0, y: 0 },
        width: n.width,
        height: n.height,
        selected: n.id === selectedPath,
        draggable: false,
        connectable: false,
        focusable: false,
        data: { ...n.data, domId: `${base}-n${order.indexOf(n.id)}`, focused: n.id === focused },
      })),
    [flow, positions, selectedPath, focused, base, order],
  );
  const edges = useMemo<GraphEdge[]>(
    () => flow.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, type: "wiki-edge", data: e.data, focusable: false, selectable: false })),
    [flow],
  );
  const rootRef = useRef<HTMLDivElement>(null);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (flow.nodes.length === 0 || isComposingEvent(e) || e.altKey || e.ctrlKey || e.metaKey) return;
    const cur = focused ?? firstId;
    if (cur === null) return;
    const dir = ARROWS[e.key];
    if (dir) {
      e.preventDefault();
      const centers = flow.nodes.map((n) => ({ id: n.id, x: (positions[n.id]?.x ?? 0) + n.width / 2, y: (positions[n.id]?.y ?? 0) + n.height / 2 }));
      const next = nearestNode(centers, cur, dir);
      if (next) {
        setFocusId(next);
        onSelect?.(next);
      }
      return;
    }
    if (e.key === "Home") {
      e.preventDefault();
      if (firstId) {
        setFocusId(firstId);
        onSelect?.(firstId);
      }
      return;
    }
    const node = flow.nodes.find((n) => n.id === cur);
    if (!node) return;
    if (e.key === "Enter" && e.shiftKey) {
      e.preventDefault();
      onCenter?.(cur);
    } else if (e.key === "Enter") {
      e.preventDefault();
      onOpen?.(node.data);
    } else if ((e.key === "c" || e.key === "C") && !e.shiftKey) {
      e.preventDefault();
      onCenter?.(cur);
    }
  };

  const root = `ac-wk-root ac-wk-graph${className ? ` ${className}` : ""}`;
  if (flow.nodes.length === 0) {
    return (
      <div className={`${root} ac-wk-state-block`} role="status">
        <p className="ac-wk-state-title">{t["graph.empty"]}</p>
      </div>
    );
  }
  return (
    <div
      ref={rootRef}
      className={root}
      style={{ height: height === "fill" ? "100%" : height }}
      role="group"
      tabIndex={0}
      aria-label={formatMessage(t["graph.label"], { n: flow.nodes.length })}
      aria-activedescendant={focused ? domIdOf(focused) : undefined}
      aria-busy={layouting || undefined}
      onKeyDown={onKeyDown}
      onFocus={(e) => {
        if (e.target === e.currentTarget && focusId === null && firstId) setFocusId(firstId);
      }}
    >
      {failed === flow ? <p className="ac-wk-banner" data-tone="info" role="status">{t["graph.layoutFailed"]}</p> : null}
      {graph.truncated && !hideTruncatedNotice ? (
        <p className="ac-wk-banner" data-tone="info" role="status">
          {graph.total !== null && graph.total !== undefined ? formatMessage(t["graph.truncated.total"], { total: graph.total, n: flow.nodes.length }) : t["graph.truncated"]}
        </p>
      ) : null}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        elementsSelectable
        zoomOnDoubleClick={false}
        fitView
        fitViewOptions={{ maxZoom }}
        minZoom={0.1}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_e, node) => onSelect?.(node.id)}
        onNodeDoubleClick={(_e, node) => {
          const found = flow.nodes.find((n) => n.id === node.id);
          if (found) onOpen?.(found.data);
        }}
      >
        <RefitOnLayout token={placed?.source === flow ? placed : failed} maxZoom={maxZoom} readableZoom={readableZoom} focusId={firstId} />
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

/**
 * 링크 그래프(읽기 전용). @xyflow/react로 그리고 elkjs `stress`로 놓는다(같은 입력 = 같은 배치). 캔버스는 탭 정지 하나이고
 * 방향키로 이웃 칸 이동, Enter 열기, Shift+Enter·C 중심 삼기, Home 중심으로. 노드 종류(끊긴·고아·스킴·첫 페이지·중심)는 모양·아이콘으로 구분한다.
 * 같은 정보를 `LinkList`가 글로 보인다.
 */
export function LinkGraph(props: LinkGraphProps) {
  return (
    <ReactFlowProvider>
      <Inner {...props} />
    </ReactFlowProvider>
  );
}
