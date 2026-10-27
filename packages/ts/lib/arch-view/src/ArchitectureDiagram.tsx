import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { ReactFlow } from "@xyflow/react";
import type { Node, NodeTypes } from "@xyflow/react";
import type { ArchitectureCellView, ArchitectureEdgeView, ArchitectureMembership, ArchitectureView } from "@agent-console/contracts/architecture";
import { ArchitectureCellList } from "./ArchitectureCellList";
import { ArchitectureInfoBar } from "./ArchitectureInfoBar";
import { ArchitectureLegend } from "./ArchitectureLegend";
import { DiagramContext } from "./context";
import type { DiagramContextValue } from "./context";
import { defaultEdgeStyles, defaultMetricKinds, defaultTones } from "./defaults";
import { EdgeLayer } from "./EdgeLayer";
import { useControllable, useElementSize } from "./hooks";
import {
  MAX_ZOOM, MIN_ZOOM, VIEW_MARGIN, canvasSize, ensureVisible, fitViewport, gridLayout, nearestInDirection, zoomAround,
} from "./layout";
import type { Direction, Size, Viewport } from "./layout";
import { formatMessage, resolveMessages } from "./messages";
import type { ArchViewMessages } from "./messages";
import { buildEdgeModels, cellBlockedReason, edgeBlockedReason, highlightSets, sameSelection } from "./model";
import { CellNode, ZoneNode } from "./Nodes";
import { Toolbar } from "./Toolbar";
import type { ToolbarParts } from "./Toolbar";
import type { ArchFitMode, ArchSelection, ArchViewMode, BlockedReason, CellRenderer, EdgeStyleSpec, MetricKindSpec, Rect } from "./types";

const nodeTypes: NodeTypes = { cell: CellNode, zone: ZoneNode };
const ARROWS: Record<string, Direction> = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };

export interface ArchitectureDiagramProps {
  /** 그릴 구조도. 없으면 불러오는 중 모양. */
  view?: ArchitectureView | null;
  /** 지금 이벤트 표를 걸러 둔 대상. */
  selection?: ArchSelection | null;
  /** 선택한 이벤트가 맞은 칸·연결·묶음(강조). */
  highlight?: ArchitectureMembership | null;
  /** 칸·연결·묶음·분류 안 됨을 눌렀을 때. 같은 대상을 다시 누르면 null. */
  onSelect?: (selection: ArchSelection | null) => void;
  /** 걸러낼 수 없는 대상(수집 안 됨 칸, 구조 연결)을 눌렀을 때. 이때 `onSelect`는 불리지 않는다. */
  onBlocked?: (target: ArchSelection, reason: BlockedReason) => void;
  /** 하위 구조도로 들어가기(`Shift+Enter`·더블클릭·정보 줄 단추). */
  onDrill?: (cellId: string, group?: string | null) => void;
  /** `Backspace`: 한 단계 위로. */
  onBack?: () => void;
  /** 건너뛰기 링크를 누르면(이벤트 표로 포커스 이동은 앱이 한다). 없으면 링크를 그리지 않는다. */
  onSkip?: () => void;

  /** 배율(제어). 없으면 맞춤 모드가 정한다. */
  scale?: number;
  onScaleChange?: (scale: number) => void;
  fitMode?: ArchFitMode;
  defaultFitMode?: ArchFitMode;
  onFitModeChange?: (mode: ArchFitMode) => void;
  /** 이 배율 미만이면 요약 표시(칸마다 숫자만). */
  fullScaleMin?: number;
  /** 컨테이너 크기를 레이아웃으로 알 수 없을 때의 값(테스트·고정 크기). */
  containerSize?: Size;

  viewMode?: ArchViewMode;
  defaultViewMode?: ArchViewMode;
  onViewModeChange?: (mode: ArchViewMode) => void;
  /** `layout`은 지표·상태 표기를 숨기고 배치만 그린다(설정 미리보기). */
  mode?: "live" | "layout";

  /** X24 확장: tone → 토큰 변수, 연결 style → 선 모양, 칸 `view` → 칸 안쪽 그리기, 지표 이름 → 표기 종류. */
  tones?: Readonly<Record<string, string>>;
  edgeStyles?: Readonly<Record<string, EdgeStyleSpec>>;
  cellRenderers?: Readonly<Record<string, CellRenderer>>;
  metricKinds?: Readonly<Record<string, MetricKindSpec>>;
  /** 범례 글자(연결 style 이름 → 글자). */
  edgeLegend?: Readonly<Record<string, string>>;
  messages?: Partial<ArchViewMessages>;

  /** 도구줄 구성. `false`면 도구줄이 없다. */
  toolbar?: boolean | ToolbarParts;
  /** 도구줄 오른쪽에 덧붙일 앱 컨트롤. */
  toolbarExtra?: ReactNode;
  /** 선택 정보 줄을 그림 아래에 둔다(기본 true). */
  infoBar?: boolean;
  className?: string;
}

const ALL_PARTS: Required<ToolbarParts> = { zoom: true, fit: true, view: true, legend: true };

/**
 * 관측 구조도 그림(docs/design/screen-architecture.md §4).
 * `ArchitectureView`(서버가 좌표·라벨·지표까지 채운 결과)만 받아 영역·칸·연결·칩을 그린다.
 * 칸 종류·연결 종류·색은 모른다: 모든 이름은 데이터이고 모르는 `tone`·`style`은 중립 모양이다.
 * 데이터 질의·필터 칩은 이 컴포넌트 밖(앱)에서 한다.
 */
export function ArchitectureDiagram(props: ArchitectureDiagramProps) {
  const {
    view, selection = null, highlight = null, onSelect, onBlocked, onDrill, onBack, onSkip,
    scale: scaleProp, onScaleChange, fullScaleMin = 0.6, containerSize,
    mode = "live", tones = defaultTones, edgeStyles = defaultEdgeStyles, cellRenderers, metricKinds = defaultMetricKinds,
    edgeLegend, toolbar = true, toolbarExtra, infoBar = true, className,
  } = props;
  const messages = useMemo(() => resolveMessages(props.messages), [props.messages]);
  const [fitMode, setFitMode] = useControllable<ArchFitMode>(props.fitMode, props.defaultFitMode ?? "width", props.onFitModeChange);
  const [viewMode, setViewMode] = useControllable<ArchViewMode>(props.viewMode, props.defaultViewMode ?? "diagram", props.onViewModeChange);
  const [userScale, setUserScale] = useState(1);
  const [pan, setPan] = useState<{ key: string; x: number; y: number } | null>(null);
  const [legendOpen, setLegendOpen] = useState(false);
  const [focusTarget, setFocusTarget] = useState<ArchSelection | null>(null);
  const lastFit = useRef<Exclude<ArchFitMode, "none">>("width");
  const canvasRef = useRef<HTMLDivElement>(null);
  const legendBtn = useRef<HTMLButtonElement>(null);
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const legendId = `ac-arch-legend-${uid}`;
  const descId = `ac-arch-desc-${uid}`;

  const cells = useMemo(() => view?.cells ?? [], [view]);
  const cellsById = useMemo(() => Object.fromEntries(cells.map((c) => [c.id, c])), [cells]);
  const edgesById = useMemo(() => Object.fromEntries((view?.edges ?? []).map((e) => [e.id, e])), [view]);
  const rects = useMemo(() => (view ? gridLayout(view) : {}), [view]);
  const size = useMemo(() => (view ? canvasSize(view, rects) : { width: 0, height: 0 }), [view, rects]);
  const container = useElementSize(canvasRef, containerSize);
  const models = useMemo(() => (view ? buildEdgeModels(view, rects, { edgeStyles, messages }) : []), [view, rects, edgeStyles, messages]);
  const hl = useMemo(() => highlightSets(highlight), [highlight]);
  if (fitMode !== "none") lastFit.current = fitMode;

  // ---- 배율·위치: 맞춤 모드가 정한 값 위에 사용자가 끈 위치를 얹는다. 맞춤 키가 바뀌면 위치는 버린다.
  const fitKey = fitMode === "none" ? "none" : `${fitMode}:${Math.round(container.width)}x${Math.round(container.height)}`;
  const fit = fitMode === "none" ? null : fitViewport(fitMode, size, container);
  const zoom = scaleProp ?? fit?.zoom ?? userScale;
  const userPan = pan && pan.key === fitKey ? pan : null;
  const vp: Viewport = { zoom, x: userPan?.x ?? fit?.x ?? VIEW_MARGIN, y: userPan?.y ?? fit?.y ?? VIEW_MARGIN };
  const level = zoom < fullScaleMin ? "summary" : "full";

  const applyViewport = useCallback(
    (next: Viewport, opts: { zoomed?: boolean } = {}) => {
      if (Math.abs(next.zoom - vp.zoom) > 1e-4 || opts.zoomed) {
        const z = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, next.zoom));
        if (fitMode !== "none") setFitMode("none");
        setUserScale(z);
        onScaleChange?.(z);
        setPan({ key: "none", x: next.x, y: next.y });
      } else if (Math.abs(next.x - vp.x) > 0.5 || Math.abs(next.y - vp.y) > 0.5) {
        setPan({ key: fitKey, x: next.x, y: next.y });
      }
    },
    [vp.zoom, vp.x, vp.y, fitMode, fitKey, setFitMode, onScaleChange],
  );
  const zoomBy = useCallback((factor: number) => applyViewport(zoomAround(vp, vp.zoom * factor, { x: container.width / 2, y: container.height / 2 }), { zoomed: true }), [applyViewport, vp, container.width, container.height]);
  const resetScale = useCallback(() => {
    setFitMode("none");
    setUserScale(1);
    onScaleChange?.(1);
    setPan({ key: "none", x: VIEW_MARGIN, y: VIEW_MARGIN });
  }, [setFitMode, onScaleChange]);

  const reveal = useCallback(
    (rect: Rect) => {
      const next = ensureVisible(rect, vp, container);
      if (next) setPan({ key: fitKey, x: next.x, y: next.y });
    },
    [vp, container, fitKey],
  );
  const rectOfTarget = useCallback(
    (t: ArchSelection): Rect | null => {
      if (t.kind === "cell" || t.kind === "group") return rects[t.id] ?? null;
      if (t.kind === "edge") {
        const m = models.find((x) => x.edge.id === t.id);
        return m ? { x: m.center[0] - m.cap / 2, y: m.center[1] - 10, w: m.cap, h: 20 } : null;
      }
      return null;
    },
    [rects, models],
  );
  // 선택이 바뀌면 그 대상이 보이도록 최소한만 옮긴다.
  const selKey = selection ? `${selection.kind}:${selection.id}:${selection.group ?? ""}` : "";
  const revealRef = useRef(reveal);
  revealRef.current = reveal;
  const targetRectRef = useRef(rectOfTarget);
  targetRectRef.current = rectOfTarget;
  useEffect(() => {
    if (!selKey) return;
    const sel = selection;
    const r = sel ? targetRectRef.current(sel) : null;
    if (r) revealRef.current(r);
  }, [selKey]);

  // ---- 눌림
  const activate = useCallback(
    (target: ArchSelection) => {
      const reason =
        target.kind === "cell"
          ? (cellsById[target.id] ? cellBlockedReason(cellsById[target.id] as ArchitectureCellView) : null)
          : target.kind === "edge"
            ? (edgesById[target.id] ? edgeBlockedReason(edgesById[target.id] as ArchitectureEdgeView) : null)
            : null;
      if (reason) {
        onBlocked?.(target, reason);
        return;
      }
      onSelect?.(sameSelection(selection, target) ? null : target);
    },
    [cellsById, edgesById, selection, onSelect, onBlocked],
  );
  const drill = useCallback((cellId: string, group?: string | null) => onDrill?.(cellId, group), [onDrill]);

  const ctx = useMemo<DiagramContextValue>(
    () => ({
      level, mode, messages, tones, metricKinds,
      cellRenderers: cellRenderers ?? {},
      cells: cellsById,
      edges: edgesById,
      cellLabels: Object.fromEntries(cells.map((c) => [c.id, c.label])),
      selection, highlight: hl, activate, drill,
    }),
    [level, mode, messages, tones, metricKinds, cellRenderers, cells, cellsById, edgesById, selection, hl, activate, drill],
  );

  // ---- 노드: 영역(넓은 것부터, 칸 뒤) → 칸(선언 순서 = Tab 순서)
  const nodes = useMemo<Node[]>(() => {
    const flags = { draggable: false, selectable: false, focusable: false, connectable: false, deletable: false } as const;
    const zones = [...(view?.zones ?? [])].sort((a, b) => b.w * b.h - a.w * a.h).map<Node>((z) => ({
      id: `zone:${z.id}`, type: "zone", position: { x: z.x, y: z.y }, width: z.w, height: z.h, style: { width: z.w, height: z.h, pointerEvents: "none" }, data: { zone: z }, ...flags,
    }));
    const cellNodes = cells.map<Node>((c) => {
      const r = rects[c.id] as Rect;
      return { id: `cell:${c.id}`, type: "cell", position: { x: r.x, y: r.y }, width: r.w, height: r.h, style: { width: r.w, height: r.h }, data: { cellId: c.id }, ...flags };
    });
    return [...zones, ...cellNodes];
  }, [view, cells, rects]);

  // ---- 키보드 (캔버스 안)
  const focusCell = (id: string) => {
    Array.from(canvasRef.current?.querySelectorAll<HTMLElement>("[data-cell-id]") ?? []).find((el) => el.dataset.cellId === id)?.focus();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const t = e.target as HTMLElement;
    if (e.key === "Escape") {
      if (legendOpen) {
        e.stopPropagation();
        setLegendOpen(false);
        legendBtn.current?.focus();
      } else if (selection && canvasRef.current?.contains(t)) {
        e.stopPropagation();
        onSelect?.(null);
      }
      return;
    }
    if (!canvasRef.current?.contains(t) || viewMode !== "diagram") return;
    const cellId = t.closest<HTMLElement>("[data-cell-id]")?.dataset.cellId;
    if (e.key === "Enter" && e.shiftKey && cellId) {
      e.preventDefault();
      if (cells.find((c) => c.id === cellId)?.drillable) onDrill?.(cellId);
    } else if (ARROWS[e.key] && cellId) {
      const next = nearestInDirection(rects, cellId, ARROWS[e.key] as Direction);
      if (next) {
        e.preventDefault();
        focusCell(next);
      }
    } else if (e.key === "Home" || e.key === "End") {
      const target = e.key === "Home" ? cells[0] : cells[cells.length - 1];
      if (target) {
        e.preventDefault();
        focusCell(target.id);
      }
    } else if (e.key === "+" || e.key === "=") zoomBy(1.25);
    else if (e.key === "-") zoomBy(1 / 1.25);
    else if (e.key === "0") setFitMode(lastFit.current);
    else if (e.key === "Backspace" && onBack) {
      e.preventDefault();
      onBack();
    }
  };

  const targetFromEvent = (t: HTMLElement): ArchSelection | null => {
    const c = t.closest<HTMLElement>("[data-cell-id]");
    if (c?.dataset.cellId) return { kind: "cell", id: c.dataset.cellId };
    const ed = t.closest<HTMLElement>("[data-edge-id]");
    return ed?.dataset.edgeId ? { kind: "edge", id: ed.dataset.edgeId } : null;
  };
  const onFocusCapture = (e: React.FocusEvent<HTMLDivElement>) => {
    if (!canvasRef.current?.contains(e.target)) return;
    const t = targetFromEvent(e.target);
    setFocusTarget(t);
    const r = t ? rectOfTarget(t) : null;
    if (r) reveal(r);
  };
  const onBlurCapture = (e: React.FocusEvent<HTMLDivElement>) => {
    if (!canvasRef.current?.contains(e.relatedTarget as globalThis.Node | null)) setFocusTarget(null);
  };

  if (!view) {
    return (
      <div className={["ac-arch-root", className].filter(Boolean).join(" ")} role="status" aria-busy="true" data-loading="">
        {messages.loading}
      </div>
    );
  }
  const parts = toolbar === false ? null : toolbar === true ? ALL_PARTS : { ...ALL_PARTS, ...toolbar };
  const infoTarget = focusTarget ?? selection;
  const zoneTitles = (view.zones ?? []).map((z) => z.label).filter(Boolean).join(", ");

  return (
    <div
      className={["ac-arch-root", className].filter(Boolean).join(" ")}
      role="group"
      aria-label={formatMessage(messages.ariaDiagram, { title: view.title || view.profile })}
      aria-describedby={descId}
      data-level={level}
      data-mode={mode}
      data-view={viewMode}
      style={{ ["--arch-inv" as string]: String(1 / zoom) }}
      onKeyDown={onKeyDown}
      onFocusCapture={onFocusCapture}
      onBlurCapture={onBlurCapture}
    >
      {onSkip ? (
        <button type="button" className="ac-arch-skip" onClick={onSkip}>{messages.ariaSkip}</button>
      ) : null}
      {parts ? (
        <div className="ac-arch-head">
          <Toolbar
            parts={parts} messages={messages} scale={zoom} fitMode={fitMode} viewMode={viewMode} legendOpen={legendOpen} legendId={legendId}
            onZoom={zoomBy} onResetScale={resetScale} onFitMode={setFitMode} onViewMode={setViewMode}
            onToggleLegend={() => setLegendOpen((o) => !o)} legendButtonRef={legendBtn} extra={toolbarExtra}
          />
          {legendOpen ? (
            <div id={legendId} className="ac-arch-popover" role="group" aria-label={messages.legend}>
              <ArchitectureLegend messages={messages} edgeStyles={edgeStyles} edgeLegend={edgeLegend} />
            </div>
          ) : null}
        </div>
      ) : null}
      {mode === "layout" ? <p className="ac-arch-note">{messages.layoutNote}</p> : null}
      {viewMode === "list" ? (
        <ArchitectureCellList view={view} selection={selection} highlight={highlight} onSelect={onSelect} onBlocked={onBlocked} tones={tones} metricKinds={metricKinds} messages={messages} />
      ) : (
        <div className="ac-arch-canvas" ref={canvasRef} data-arch-canvas="" data-fit={fitMode}>
          <DiagramContext.Provider value={ctx}>
            <ReactFlow
              nodes={nodes}
              edges={[]}
              nodeTypes={nodeTypes}
              viewport={vp}
              onViewportChange={applyViewport}
              minZoom={MIN_ZOOM}
              maxZoom={MAX_ZOOM}
              translateExtent={[[-VIEW_MARGIN * 4, -VIEW_MARGIN * 4], [size.width + VIEW_MARGIN * 4, size.height + VIEW_MARGIN * 4]]}
              nodesDraggable={false}
              nodesConnectable={false}
              nodesFocusable={false}
              edgesFocusable={false}
              elementsSelectable={false}
              selectNodesOnDrag={false}
              disableKeyboardA11y
              panOnDrag
              panOnScroll
              zoomOnScroll={false}
              zoomOnDoubleClick={false}
              zoomOnPinch
              preventScrolling
              proOptions={{ hideAttribution: true }}
            >
              <EdgeLayer models={models} width={size.width} height={size.height} />
            </ReactFlow>
          </DiagramContext.Provider>
        </div>
      )}
      <p id={descId} className="ac-arch-sr">{zoneTitles}</p>
      {infoBar && mode === "live" ? (
        <ArchitectureInfoBar
          view={view} target={infoTarget} preview={!!focusTarget && !sameSelection(focusTarget, selection)} selection={selection}
          messages={messages} metricKinds={metricKinds} onSelect={onSelect} onDrill={onDrill}
        />
      ) : null}
    </div>
  );
}
