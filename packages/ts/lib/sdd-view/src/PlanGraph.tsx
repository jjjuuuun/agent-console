import type { ParsedTask, TaskPlan } from "@agent-console/contracts/sdd";
import { Background, Controls, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, useReactFlow, useStore, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { statusTone, type StatusLike } from "./display";
import { formatMessage, resolveMessages } from "./messages";
import { applyPositions, createElkPlanLayout, planToFlow, PLAN_DEFAULTS, type PlanFlowOptions, type PlanLayoutEngine, type PlanNodeData } from "./plan";
import { ToneChip } from "@agent-console/markdown-doc";

const PLAN_PAD = 24;
type PlanNode = Node<PlanNodeData & { statusLabel: string; statusTone: string; ariaText: string; readyLabel: string; dim: boolean }, "sdd-plan-node">;
type PlanLayerHead = Node<{ label: string; badge: string }, "sdd-plan-layer">;

function PlanNodeView({ data, selected }: NodeProps<PlanNode>) {
  return (
    <div
      className="ac-sdd-plan-node"
      data-critical={data.critical || undefined}
      data-ready={data.ready || undefined}
      data-blocked={data.blocked || undefined}
      data-cycle={data.cycle || undefined}
      data-selected={selected || undefined}
      data-dim={data.dim || undefined}
      title={data.title}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <span className="ac-sdd-plan-node-top">
        <span className="ac-sdd-mono ac-sdd-plan-node-key">{data.key}</span>
        <ToneChip label={data.statusLabel} tone={data.statusTone} />
        {data.ready ? <ToneChip label={data.readyLabel} tone="info" /> : null}
      </span>
      <span className="ac-sdd-ellipsis">{data.title}</span>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}
/** 열 머리 라벨("묶음 n" + 병목 순번 배지). 노드 위 한 줄, 선택·포커스되지 않는다. */
function PlanLayerHeadView({ data }: NodeProps<PlanLayerHead>) {
  return (
    <div className="ac-sdd-plan-layer-head" aria-hidden="true">
      <span>{data.label}</span>
      {data.badge !== "" ? <span className="ac-sdd-plan-layer-badge">{data.badge}</span> : null}
    </div>
  );
}
const nodeTypes = { "sdd-plan-node": PlanNodeView, "sdd-plan-layer": PlanLayerHeadView };

export interface PlanGraphProps {
  plan: TaskPlan;
  tasks: readonly ParsedTask[];
  /** 작업 상태 정의(노드의 상태 칩). */
  statuses?: readonly StatusLike[];
  /** 배치 엔진. 기본은 elkjs 층 배치(처음 필요할 때 불러옴). 실패하면 층별 열 배치로 남는다. */
  engine?: PlanLayoutEngine;
  options?: PlanFlowOptions;
  selectedKey?: string | null;
  onSelect?: (taskKey: string) => void;
  height?: number | "fill";
  /** 첫 화면에서 허용하는 가장 작은 줌(글자가 읽히는 크기). 이보다 작아야 다 들어오는 그래프는 이 줌으로 시작 노드부터 보여 준다. 기본 1(노드 글자 12px) */
  readableZoom?: number;
  /** 사용자가 줄일 수 있는 가장 작은 줌의 기준. 그래프 전체가 이보다 작아야 들어오면 맞춤이 잘리지 않도록 더 낮춘다. 기본 0.4 */
  minZoom?: number;
  /** 병목이 아닌 노드·연결을 흐리게 한다(병목만 강조). 스위치는 앱이 도구줄에 둔다 */
  onlyCritical?: boolean;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

function InnerPlanGraph({ plan, tasks, statuses, engine, options, selectedKey, onSelect, height = "fill", readableZoom = 1, minZoom: minZoomBase = 0.4, onlyCritical = false, messages, className }: PlanGraphProps) {
  const text = resolveMessages(messages);
  const base = useMemo(() => planToFlow(plan, tasks, options), [plan, tasks, options]);
  const defaultEngine = useMemo(() => createElkPlanLayout(), []);
  const [placed, setPlaced] = useState<{ source: typeof base; positions: Record<string, { x: number; y: number }> } | null>(null);
  const [failed, setFailed] = useState<typeof base | null>(null);
  const layerGap = options?.layerGap ?? PLAN_DEFAULTS.layerGap;
  const nodeGap = options?.nodeGap ?? PLAN_DEFAULTS.nodeGap;

  useEffect(() => {
    if (base.nodes.length === 0) return;
    let cancelled = false;
    (engine ?? defaultEngine)({
      nodes: base.nodes.map((n) => ({ id: n.id, width: n.width, height: n.height })),
      edges: base.edges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
      layerGap,
      nodeGap,
    }).then(
      (positions) => {
        if (!cancelled) setPlaced({ source: base, positions });
      },
      () => {
        if (!cancelled) setFailed(base);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [base, engine, defaultEngine, layerGap, nodeGap]);

  const flow = placed && placed.source === base ? applyPositions(base, placed.positions) : base;
  const layouting = base.nodes.length > 0 && !(placed && placed.source === base) && failed !== base;
  const { fitView, getNodesBounds, getNodes, setViewport } = useReactFlow();
  const viewW = useStore((st) => st.width);
  const viewH = useStore((st) => st.height);
  const laidOut = !layouting && base.nodes.length > 0;
  // 사용자가 줌·이동·맞춤을 만졌으면 그 뒤 레이아웃·크기 변화로 자동 맞춤을 다시 하지 않는다(계획이 바뀌면 다시 자동).
  const touched = useRef(false);
  // 다시 불러와 같은 작업이 새 객체로 오는 것은 계획이 바뀐 것이 아니다 — 작업 키 목록이 바뀔 때만 다시 자동으로 맞춘다.
  const planSignature = useMemo(() => base.nodes.map((n) => n.id).join("\u0000"), [base]);
  useEffect(() => {
    touched.current = false;
  }, [planSignature]);
  const markTouched = () => {
    touched.current = true;
  };
  // 그래프 전체가 다 들어오는 줌이 기본 최소 줌보다 작으면 최소 줌을 낮춰 맞춤이 양 끝을 자르지 않게 한다.
  const minZoom = useMemo(() => {
    if (!laidOut || viewW <= 0 || viewH <= 0 || flow.nodes.length === 0) return minZoomBase;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of flow.nodes) {
      x0 = Math.min(x0, n.position.x);
      y0 = Math.min(y0, n.position.y - 28);
      x1 = Math.max(x1, n.position.x + (n.width ?? 0));
      y1 = Math.max(y1, n.position.y + (n.height ?? 0));
    }
    const fit = Math.min(Math.max(viewW - 2 * PLAN_PAD, 1) / Math.max(x1 - x0, 1), Math.max(viewH - 2 * PLAN_PAD, 1) / Math.max(y1 - y0, 1));
    return Math.max(0.02, Math.min(minZoomBase, fit * 0.8));
  }, [laidOut, flow, viewW, viewH, minZoomBase]);
  const flowLabels = useMemo(
    () => ({
      "controls.ariaLabel": text["plan.controls"],
      "controls.zoomIn.ariaLabel": text["plan.zoomIn"],
      "controls.zoomOut.ariaLabel": text["plan.zoomOut"],
      "controls.fitView.ariaLabel": text["plan.fitView"],
      "controls.interactive.ariaLabel": text["plan.interactive"],
      "node.a11yDescription.default": text["plan.nodeHint"],
      "node.a11yDescription.keyboardDisabled": text["plan.nodeHint"],
    }),
    [text],
  );
  // 첫 `fitView`는 배치 전(전부 원점) 좌표로 맞춰져 캔버스가 비어 보인다. 배치(또는 실패 대체 배치)가 끝난 뒤 다시 맞춘다.
  useEffect(() => {
    if (!laidOut || touched.current) return;
    const id = setTimeout(() => {
      if (touched.current) return;
      // 영역에 다 들어오면 전체를 맞추고, 그러면 글자가 안 읽히는 크기(readableZoom 미만)가 되는 큰 그래프는
      // 읽히는 줌으로 두고 시작 노드(왼쪽 위)부터 보여 준다. 나머지는 끌어서 이동·확대/축소로 본다(양 끝이 잘려 보이지 않게).
      void fitView({ duration: 0, minZoom: readableZoom, maxZoom: 1.5 }).then(() => {
        if (viewW <= 0 || viewH <= 0) return;
        const b = getNodesBounds(getNodes());
        const fits = b.width * readableZoom <= viewW - 2 * PLAN_PAD && b.height * readableZoom <= viewH - 2 * PLAN_PAD;
        if (fits) return;
        void setViewport({ x: PLAN_PAD - b.x * readableZoom, y: PLAN_PAD - b.y * readableZoom, zoom: readableZoom }, { duration: 0 });
      });
    }, 0);
    return () => clearTimeout(id);
  }, [laidOut, flow, fitView, getNodesBounds, getNodes, setViewport, viewW, viewH, readableZoom]);

  const planCritical = plan.critical_path;
  const nodes = useMemo<Array<PlanNode | PlanLayerHead>>(() => {
    const criticalPath = planCritical ?? [];
    const items: PlanNode[] = flow.nodes.map((n) => {
      const st = statusTone(n.data.status, statuses);
      const flags = [n.data.critical ? text["plan.critical"] : "", n.data.ready ? text["plan.ready"] : "", n.data.blocked ? text["plan.blocked"] : "", n.data.cycle ? text["plan.cycle"] : ""]
        .filter((s) => s !== "")
        .join(", ");
      return {
        id: n.id,
        type: "sdd-plan-node",
        position: n.position,
        width: n.width,
        height: n.height,
        selected: n.id === selectedKey,
        ariaLabel: formatMessage(text["plan.node"], { title: n.data.title, layer: n.data.layer + 1, flags: flags || st.label }),
        data: { ...n.data, statusLabel: st.label, statusTone: st.tone, ariaText: n.data.title, readyLabel: text["plan.ready"], dim: onlyCritical && !n.data.critical },
      };
    });
    // 열 머리: 같은 묶음(layer) 노드들의 왼쪽 위 좌표 위에 둔다
    const heads = new Map<number, { x: number; y: number; badge: string }>();
    for (const n of flow.nodes) {
      const h = heads.get(n.data.layer) ?? { x: n.position.x, y: n.position.y, badge: "" };
      h.x = Math.min(h.x, n.position.x);
      h.y = Math.min(h.y, n.position.y);
      const at = criticalPath.indexOf(n.id);
      if (at >= 0 && h.badge === "") h.badge = formatMessage(text["plan.criticalBadge"], { n: at + 1, total: criticalPath.length });
      heads.set(n.data.layer, h);
    }
    const headNodes: PlanLayerHead[] = [...heads.entries()].map(([layer, h]) => ({
      id: `ac-sdd-layer-${layer}`,
      type: "sdd-plan-layer",
      position: { x: h.x, y: h.y - 28 },
      selectable: false,
      draggable: false,
      focusable: false,
      connectable: false,
      data: { label: formatMessage(text["plan.layerHead"], { n: layer + 1 }), badge: h.badge },
    }));
    return [...headNodes, ...items];
  }, [flow, statuses, selectedKey, text, onlyCritical, planCritical]);
  const edges = useMemo<Edge[]>(
    () =>
      flow.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        className: e.critical ? "ac-sdd-plan-edge ac-sdd-plan-edge-critical" : "ac-sdd-plan-edge",
        // 화살촉은 선 색과 같은 색(fill=stroke). 색은 선 CSS와 같은 토큰을 쓴다
        markerEnd: { type: MarkerType.ArrowClosed, color: e.critical ? "var(--ac-accent)" : "var(--ac-border-strong)" },
        ...(onlyCritical && !e.critical ? { style: { opacity: 0.3 } } : {}),
        focusable: false,
      })),
    [flow, onlyCritical],
  );

  const root = `ac-sdd-root ac-sdd-plan${className ? ` ${className}` : ""}`;
  if (base.nodes.length === 0) {
    return (
      <div className={`${root} ac-sdd-empty`} role="status">
        <p className="ac-sdd-empty-title">{text["plan.empty"]}</p>
      </div>
    );
  }
  return (
    <div className={root} style={{ height: height === "fill" ? "100%" : height }} role="group" aria-label={text["plan.graph"]} aria-busy={layouting || undefined}>
      {failed === base ? (
        <p className="ac-sdd-banner" data-tone="info" role="status">
          {text["plan.layoutFailed"]}
        </p>
      ) : null}
      {flow.truncated ? <p className="ac-sdd-banner" data-tone="info">{formatMessage(text["plan.truncated"], { n: base.nodes.length })}</p> : null}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        edgesFocusable={false}
        elementsSelectable
        nodesFocusable
        fitView
        minZoom={minZoom} maxZoom={1.5}
        ariaLabelConfig={flowLabels}
        onMoveStart={(e) => { if (e) markTouched(); }}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_e, node) => onSelect?.(node.id)}
        aria-label={text["plan.graph"]}
      >
        <Background />
        <Controls showInteractive={false} onZoomIn={markTouched} onZoomOut={markTouched} onFitView={markTouched} />
      </ReactFlow>
    </div>
  );
}

/**
 * 계획 그래프(읽기 전용). @xyflow/react로 그리고 elkjs 층 배치로 놓는다. 병목(가장 긴 의존 사슬)·준비됨·막힘·순환을
 * 노드 표시(`data-*`)로 구분하고 색 말고 글자(접근성 이름)로도 알린다. 노드·연결은 편집할 수 없다.
 * 같은 내용을 글로 보는 `PlanBundles`를 옆에 두면 그래프를 못 보는 사용자도 같은 정보를 얻는다.
 */
export function PlanGraph(props: PlanGraphProps) {
  return (
    <ReactFlowProvider>
      <InnerPlanGraph {...props} />
    </ReactFlowProvider>
  );
}
