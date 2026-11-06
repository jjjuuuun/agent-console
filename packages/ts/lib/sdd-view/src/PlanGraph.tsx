import type { ParsedTask, TaskPlan } from "@agent-console/contracts/sdd";
import { Background, Controls, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import { statusTone, type StatusLike } from "./display";
import { formatMessage, resolveMessages } from "./messages";
import { applyPositions, createElkPlanLayout, planToFlow, PLAN_DEFAULTS, type PlanFlowOptions, type PlanLayoutEngine, type PlanNodeData } from "./plan";
import { ToneChip } from "@agent-console/markdown-doc";

type PlanNode = Node<PlanNodeData & { statusLabel: string; statusTone: string; ariaText: string }, "sdd-plan-node">;

function PlanNodeView({ data, selected }: NodeProps<PlanNode>) {
  return (
    <div
      className="ac-sdd-plan-node"
      data-critical={data.critical || undefined}
      data-ready={data.ready || undefined}
      data-blocked={data.blocked || undefined}
      data-cycle={data.cycle || undefined}
      data-selected={selected || undefined}
      title={data.title}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <span className="ac-sdd-ellipsis">{data.title}</span>
      <ToneChip label={data.statusLabel} tone={data.statusTone} />
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}
const nodeTypes = { "sdd-plan-node": PlanNodeView };

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
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

function InnerPlanGraph({ plan, tasks, statuses, engine, options, selectedKey, onSelect, height = "fill", messages, className }: PlanGraphProps) {
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

  const nodes = useMemo<PlanNode[]>(
    () =>
      flow.nodes.map((n) => {
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
          data: { ...n.data, statusLabel: st.label, statusTone: st.tone, ariaText: n.data.title },
        };
      }),
    [flow, statuses, selectedKey, text],
  );
  const edges = useMemo<Edge[]>(
    () =>
      flow.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        className: e.critical ? "ac-sdd-plan-edge ac-sdd-plan-edge-critical" : "ac-sdd-plan-edge",
        markerEnd: { type: MarkerType.ArrowClosed },
        focusable: false,
      })),
    [flow],
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
        minZoom={0.1}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_e, node) => onSelect?.(node.id)}
        aria-label={text["plan.graph"]}
      >
        <Background />
        <Controls showInteractive={false} />
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
