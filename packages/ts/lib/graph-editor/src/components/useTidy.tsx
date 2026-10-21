/**
 * [정리 ▾] 연결 훅: 편집기 상태(그래프·화면 모델·선택)를 `TidyPopover`와 배치 엔진에 이어 준다(graph-edges §4.1).
 * 팝오버는 표현만 하고, 이 훅이 요청을 만들고 결과를 그래프로 바꾸며 미리보기 겹침·기억 저장소를 맡는다.
 * 적용은 `emit(next, "auto-layout")` 한 번이다.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ViewportPortal } from "@xyflow/react";
import type { EdgeTypeDescriptor, Graph } from "@agent-console/contracts";
import { defaultOptionValues } from "../layout/types";
import type { LayoutEngineDescriptor } from "../layout/types";
import { resolveDirection } from "../logic/layout";
import type { DirectionSides } from "../logic/layout";
import { graphUiLayoutOf } from "../logic/nodeLayoutOps";
import { edgesOf } from "../logic/ops";
import type { Point } from "../logic/ops";
import { readJson, writeJson } from "../logic/storage";
import type { KeyValueStorage } from "../logic/storage";
import { anchorPositions, applyTidy, buildLayoutRequest, countEdgePaths, flowSideOf, resetAllEdgePaths } from "../logic/tidy";
import type { TidyNodeView } from "../logic/tidy";
import { routePreview } from "../logic/autoRoute";
import type { PreviewNode } from "../logic/autoRoute";
import type { EdgeRouter } from "../logic/route";
import type { GraphEditorMessages } from "../messages";
import type { EdgeShapeDescriptor, Side } from "../shapes/types";
import type { FlowNode } from "./flow";
import { TidyPopover, normalizeTidyValues } from "./TidyPopover";
import type { TidyValues } from "./TidyPopover";

/** 계산 결과: 새 좌표(격자·좌상단 맞춤 완료)와 미리보기에 쓸 크기, 범위. */
export interface TidyOutcome {
  positions: ReadonlyMap<string, Point>;
  sizes: ReadonlyMap<string, { width: number; height: number }>;
  scope: ReadonlySet<string> | null;
}

export interface UseTidyArgs {
  graph: Graph;
  engines: readonly LayoutEngineDescriptor[] | undefined;
  /** 화면 모델의 노드(포트 면이 정해진 값) */
  flowNodes: readonly FlowNode[];
  edgeTypes: readonly EdgeTypeDescriptor[];
  shapes: readonly EdgeShapeDescriptor[];
  directions: DirectionSides;
  layoutDefaults: { direction?: string | null; edgeShape?: string | null } | undefined;
  selectedNodeIds: readonly string[];
  grid: number | false;
  readOnly: boolean;
  storage: KeyValueStorage | null;
  storagePrefix: string;
  messages: GraphEditorMessages;
  /** 편집기의 단일 출구 */
  emit: (next: Graph, reason: "auto-layout" | "layout") => void;
  announce: (text: string) => void;
  /** 토스트 [되돌리기]가 가리킬 이전 그래프와 결과 */
  toastUndo: (text: string, previous: Graph, after: Graph) => void;
  /** 적용 뒤 화면에 맞추기 */
  requestFit: () => void;
  /** 미리보기 연결 중심선을 라우터 경로로 그리게 하는 편집기의 라우터(같은 인스턴스를 재사용). 없으면 노드 중심을 잇는 직선 */
  getRouter?: () => EdgeRouter;
}

export interface TidyParts {
  /** 정리를 쓸 수 있는가(엔진이 있고 편집 모드) */
  available: boolean;
  open: boolean;
  setOpen: (open: boolean) => void;
  /** 캔버스 안 툴바에 놓을 [정리 ▾] 버튼과 팝오버 */
  control: ReactNode;
  /** React Flow 자식으로 놓을 미리보기 겹침 */
  ghost: ReactNode;
  /** 계산이 120ms 넘게 걸릴 때 true(캔버스 상단 진행 바) */
  showBar: boolean;
}

const STORE_KEY = "tidy";
export const BAR_DELAY_MS = 120;

export function useTidy(a: UseTidyArgs): TidyParts {
  const { graph, engines, flowNodes, edgeTypes, shapes, directions, selectedNodeIds, messages: m } = a;
  const available = !a.readOnly && engines !== undefined && engines.length > 0;
  const [open, setOpen] = useState(false);
  const [ghostOutcome, setGhostOutcome] = useState<TidyOutcome | null>(null);
  const [running, setRunning] = useState(false);
  const [showBar, setShowBar] = useState(false);
  const latest = useRef(a);
  useEffect(() => {
    latest.current = a;
  });

  useEffect(() => {
    if (!running) return;
    const h = setTimeout(() => setShowBar(true), BAR_DELAY_MS);
    return () => {
      clearTimeout(h);
      setShowBar(false);
    };
  }, [running]);

  const close = useCallback(() => {
    setOpen(false);
    setGhostOutcome(null);
  }, []);
  // 팝오버가 열려 있는 동안 그래프가 바뀌면(되돌리기 등) 낡은 미리보기는 버린다
  const seen = useRef(graph);
  useEffect(() => {
    if (seen.current !== graph) {
      seen.current = graph;
      setGhostOutcome(null);
    }
  }, [graph]);

  const edgeKinds = useMemo(() => edgeTypes.map((t) => ({ id: t.id, title: t.title })), [edgeTypes]);
  const initial = useMemo<TidyValues | null>(() => {
    if (!open || engines === undefined || engines.length === 0) return null;
    const ui = graphUiLayoutOf(graph);
    const dir = resolveDirection({ node: null, graph: ui, settings: a.layoutDefaults?.direction ?? null, hint: null, directions }).value;
    const base: TidyValues = {
      engineId: (engines[0] as LayoutEngineDescriptor).id,
      optionsByEngine: Object.fromEntries(engines.map((e) => [e.id, defaultOptionValues(e.options)])),
      direction: Object.hasOwn(directions, dir) ? dir : (Object.keys(directions)[0] ?? dir),
      scope: selectedNodeIds.length >= 2 ? "selected" : "all",
      edgeShape: typeof ui?.edge_shape === "string" ? ui.edge_shape : "",
      shapeByKind: ui?.edge_shape_by_kind !== null && typeof ui?.edge_shape_by_kind === "object" ? { ...ui.edge_shape_by_kind } : {},
      resetRoutes: true,
      alignNodes: true,
      kinds: {},
    };
    const stored = readJson(a.storage, a.storagePrefix + STORE_KEY) as Partial<TidyValues> | undefined;
    // 범위·방향·모양은 그래프와 선택이 정하므로 기억한 값으로 덮지 않는다
    const merged = normalizeTidyValues(stored, base, engines);
    // 엔진이 권장 모양을 선언했으면 기억한 선택(없으면 선언의 기본값)에 따라 기본 모양을 그 모양으로 시작한다
    const option = engines.find((e) => e.id === merged.engineId)?.edgeShapeOption;
    const remembered = (stored as { autoShape?: Record<string, unknown> } | undefined)?.autoShape?.[merged.engineId];
    const wantsShape = option !== undefined && shapes.some((s) => s.id === option.shapeId) && (typeof remembered === "boolean" ? remembered : option.default);
    return { ...merged, scope: base.scope, direction: base.direction, edgeShape: wantsShape ? option.shapeId : base.edgeShape, shapeByKind: base.shapeByKind };
    // 열 때 한 번만 계산한다(열려 있는 동안 선택·그래프가 바뀌어도 사용자가 만진 값을 덮지 않는다)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const compute = useCallback(
    async (values: TidyValues, signal: AbortSignal): Promise<TidyOutcome> => {
      const cur = latest.current;
      const engine = (cur.engines ?? []).find((e) => e.id === values.engineId) ?? cur.engines?.[0];
      if (engine === undefined) throw new Error("no engine");
      const flow = flowSideOf(cur.directions, values.direction);
      if (flow === null) throw new Error(values.direction);
      const views: TidyNodeView[] = cur.flowNodes.map((n) => ({
        id: n.id,
        x: n.position.x,
        y: n.position.y,
        width: n.measured?.width ?? n.initialWidth ?? 0,
        height: n.measured?.height ?? n.initialHeight ?? 0,
        inputs: n.data.inputs,
        outputs: n.data.outputs,
      }));
      const scope = values.scope === "selected" ? new Set(cur.selectedNodeIds) : null;
      const request = buildLayoutRequest({
        nodes: views,
        edges: edgesOf(cur.graph),
        scope,
        excludedKinds: new Set(Object.entries(values.kinds).filter(([, on]) => !on).map(([k]) => k)),
        backKinds: new Set(cur.edgeTypes.filter((t) => t.cycle !== null && t.cycle !== undefined).map((t) => t.id)),
        flow,
        options: values.optionsByEngine[engine.id] ?? {},
      });
      const result = await engine.run(request, signal);
      const before = views.filter((v) => scope === null || scope.has(v.id));
      return {
        positions: anchorPositions(result, before, cur.grid),
        sizes: new Map(views.map((v) => [v.id, { width: v.width, height: v.height }])),
        scope,
      };
    },
    [],
  );

  const onApply = useCallback((outcome: TidyOutcome, values: TidyValues): void => {
    const cur = latest.current;
    const shapeByKind: Record<string, string | null> = {};
    for (const k of cur.edgeTypes) shapeByKind[k.id] = (values.shapeByKind[k.id] ?? "") === "" ? null : (values.shapeByKind[k.id] as string);
    const next = applyTidy(cur.graph, {
      positions: outcome.positions,
      direction: values.direction,
      edgeShape: values.edgeShape === "" ? null : values.edgeShape,
      edgeShapeByKind: shapeByKind,
      resetRoutes: values.resetRoutes,
      alignNodeDirection: values.alignNodes,
      scope: outcome.scope,
    });
    cur.emit(next, "auto-layout");
    close();
    cur.announce(cur.messages.tidyDone);
    cur.toastUndo(cur.messages.tidyDone, cur.graph, next);
    cur.requestFit();
  }, [close]);

  const onResetAll = useCallback((): void => {
    const cur = latest.current;
    const next = resetAllEdgePaths(cur.graph);
    if (next !== cur.graph) cur.emit(next, "layout");
    close();
    cur.announce(cur.messages.routeResetDone);
  }, [close]);

  const onValuesChange = useCallback((v: TidyValues): void => {
    const cur = latest.current;
    const prev = readJson(cur.storage, cur.storagePrefix + STORE_KEY) as { autoShape?: Record<string, boolean> } | undefined;
    const option = (cur.engines ?? []).find((e) => e.id === v.engineId)?.edgeShapeOption;
    const autoShape = { ...(prev?.autoShape ?? {}), ...(option !== undefined ? { [v.engineId]: v.edgeShape === option.shapeId } : {}) };
    writeJson(cur.storage, cur.storagePrefix + STORE_KEY, { engineId: v.engineId, optionsByEngine: v.optionsByEngine, resetRoutes: v.resetRoutes, alignNodes: v.alignNodes, kinds: v.kinds, autoShape });
  }, []);

  const control: ReactNode = !available ? null : (
    <span className="ac-ge-tidy-anchor">
      <button type="button" className="ac-ge-btn" aria-haspopup="dialog" aria-expanded={open} aria-keyshortcuts="L" onClick={() => (open ? close() : setOpen(true))}>
        {m.tidyOpen} <span aria-hidden="true">▾</span>
      </button>
      {open && initial !== null && engines !== undefined && (
        <TidyPopover<TidyOutcome>
          engines={engines}
          directions={directions}
          shapes={shapes}
          edgeKinds={edgeKinds}
          initial={initial}
          nodeCount={flowNodes.length}
          selectedCount={selectedNodeIds.length}
          pathCount={countEdgePaths(graph)}
          compute={compute}
          onPreview={setGhostOutcome}
          onApply={onApply}
          onResetAllRoutes={onResetAll}
          onClose={close}
          onValuesChange={onValuesChange}
          onRunningChange={setRunning}
          messages={m}
        />
      )}
    </span>
  );

  const ghost: ReactNode = ghostOutcome === null ? null : <GhostLayer outcome={ghostOutcome} graph={graph} flowNodes={flowNodes} getRouter={a.getRouter} label={(id) => graph.nodes?.find((n) => n.id === id)?.label ?? id} />;
  return { available, open, setOpen, control, ghost, showBar };
}

/** 포트 id → 면 표 */
const sidesOf = (ports: readonly { id: string; side?: Side }[], fallback: Side): ReadonlyMap<string, Side> => new Map(ports.map((p) => [p.id, p.side ?? fallback]));

/**
 * 미리보기: 새 위치의 반투명 노드 윤곽과 연결 중심선(원본은 그대로). 흐름 좌표계 위에 그려 줌·이동을 따른다.
 * 라우터가 있으면 중심선은 라우터가 계산한 직각 경로(적용 뒤 자동 경로로 그려질 모습), 없으면 노드 중심 직선이다.
 */
function GhostLayer({ outcome, graph, flowNodes, getRouter, label }: { outcome: TidyOutcome; graph: Graph; flowNodes: readonly FlowNode[]; getRouter: (() => EdgeRouter) | undefined; label: (id: string) => string }): ReactNode {
  const lines = edgesOf(graph).filter((e) => outcome.positions.has(e.source.node) && outcome.positions.has(e.target.node));
  const center = (id: string): Point => {
    const p = outcome.positions.get(id) as Point;
    const s = outcome.sizes.get(id);
    return { x: p.x + (s?.width ?? 0) / 2, y: p.y + (s?.height ?? 0) / 2 };
  };
  const routed = useMemo(() => {
    if (getRouter === undefined) return null;
    const nodes: PreviewNode[] = flowNodes.map((n) => {
      const p = outcome.positions.get(n.id) ?? n.position;
      const s = outcome.sizes.get(n.id);
      return { id: n.id, x: p.x, y: p.y, width: s?.width ?? 0, height: s?.height ?? 0, inputSides: sidesOf(n.data.inputs, "left"), outputSides: sidesOf(n.data.outputs, "right") };
    });
    return routePreview(getRouter(), nodes, lines);
    // lines는 outcome·graph에서 파생된다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outcome, graph, flowNodes, getRouter]);
  return (
    <ViewportPortal>
      <div className="ac-ge-ghost-layer" data-testid="tidy-ghost" aria-hidden="true">
        <svg className="ac-ge-ghost-lines" width="1" height="1">
          {lines.map((e) => {
            const r = routed?.get(e.id);
            if (r !== undefined) return <path key={e.id} className="ac-ge-ghost-line" d={r.path.d} data-ghost-route="true" />;
            const s = center(e.source.node);
            const t = center(e.target.node);
            return <line key={e.id} className="ac-ge-ghost-line" x1={s.x} y1={s.y} x2={t.x} y2={t.y} />;
          })}
        </svg>
        {[...outcome.positions].map(([id, p]) => {
          const s = outcome.sizes.get(id);
          return (
            <div key={id} className="ac-ge-ghost ac-ellipsis" data-ghost-for={id} style={{ left: p.x, top: p.y, width: s?.width ?? 0, height: s?.height ?? 0 }}>
              {label(id)}
            </div>
          );
        })}
      </div>
    </ViewportPortal>
  );
}
