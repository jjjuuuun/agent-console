/** React Flow 어댑터(이 파일과 GraphEditor.tsx만 @xyflow/react를 import한다). */
import { ARROW_GAP, buildEdgePath } from "../logic/edgePath";
import { Fragment, memo, useCallback, useContext, useEffect, useRef, useState } from "react";
import { BaseEdge, EdgeLabelRenderer, Handle, Position, useStore, useUpdateNodeInternals } from "@xyflow/react";
import type { Edge, EdgeProps, Node, NodeProps } from "@xyflow/react";
import type { CSSProperties, KeyboardEvent, MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, ReactNode } from "react";
import type { ChipView, EdgeBadge } from "../types";
import { FALLBACK_EDGE_SHAPE } from "../logic/layout";
import { BUILTIN_EDGE_SHAPES } from "../shapes/registry";
import { MAX_WAYPOINTS } from "../logic/edgePath";
import { RESET_LABEL_PATCH, insertIndexFor, insertWaypoint, nearestLabelT, nearestOnSegments, snapLabelT } from "../logic/edgeLayoutOps";
import { format } from "../messages";
import { EdgeEditContext } from "./edgeEdit";
import { EdgeRouteContext } from "./routeContext";
import { routeFallbackAttrs } from "../logic/route";
import { PortEditContext } from "./portEdit";
import { usePortMove } from "./usePortMove";
import { DRAG_THRESHOLD, EdgeWaypointLayer } from "./EdgeWaypointLayer";
import type { EdgeWaypointLayerProps } from "./EdgeWaypointLayer";
import { NodeCard } from "./NodeCard";
import type { NodeCardProps } from "./NodeCard";
import { inHandleId, outHandleId } from "../logic/ports";
import type { PortView } from "../logic/ports";
import type { Point } from "../logic/ops";
import type { EdgeShapeDescriptor, Side } from "../shapes/types";

export type FlowNodeData = NodeCardProps & Record<string, unknown>;
export type FlowNode = Node<FlowNodeData, "ac-node">;

export interface FlowEdgeData extends Record<string, unknown> {
  label: string;
  color?: string;
  dashed: boolean;
  invalid: boolean;
  invalidText: string;
  state?: string;
  markerId: string;
  /** 결정된 연결선 모양(레지스트리 항목). 경로는 이 모양의 `build`가 만든다 */
  shape: EdgeShapeDescriptor;
  /** 엣지 `layout` 값(없으면 생략 = 모양의 기본값) */
  waypoints?: Point[];
  radius?: number;
  bend?: number;
  /** 라벨 위치 0~1(생략 = 0.5)과 경로에서 뗀 어긋남(px) */
  labelT?: number;
  labelOffset?: Point;
  /** 지나간 순번(1부터)과 접근성 문구 */
  /** 선언형 배지·칩 문구(디스크립터 `ui_hints`) */
  hintChips?: string[];
  orderBadge?: number;
  orderText?: string;
  /** 호출 횟수와 접근성 문구 */
  countBadge?: number;
  countText?: string;
  /** 종류 속성 기반 선 패턴(`stroke-dasharray` 값, 토큰 참조)과 선 끝 */
  dash?: string;
  linecap?: "round";
  /** 칩 앞 아이콘: 이름과 그리지 못할 때 쓸 글자, 종류 속성에서 온 아이콘인지(속성 아이콘이면 칩을 항상 보인다) */
  iconName?: string;
  iconFallback?: string;
  iconFromProperty?: boolean;
  renderIcon?: (name: string) => ReactNode;
  /** 앱이 계산한 추가 칩과 실행 상세 연결 배지 */
  extraChips?: ChipView[];
  runBadges?: EdgeBadge[];
  /** 종류 이름(칩 줄 접근성 이름용) */
  kindTitle?: string;
}
export type FlowEdge = Edge<FlowEdgeData, "ac-edge">;

/** React Flow `Position` 값은 면 이름과 같은 문자열이다. 표로 짝을 지어 분기를 두지 않는다. */
const POSITION_OF: Readonly<Record<Side, Position>> = {
  left: Position.Left,
  right: Position.Right,
  top: Position.Top,
  bottom: Position.Bottom,
};

/** 포트 핸들 하나. 롱프레스/`Alt`+드래그로 다른 면으로 옮길 수 있다(편집 모드 한정, §3.4). */
function PortHandle({ nodeId, port, io }: { nodeId: string; port: PortView; io: "in" | "out" }) {
  const api = useContext(PortEditContext);
  const side: Side = port.side ?? (io === "in" ? "left" : "right");
  const editable = api !== null && api.editable;
  const handlers = usePortMove({
    enabled: editable,
    currentSide: side,
    onCommit: (next) => {
      if (api === null) return;
      api.setPortSide(nodeId, io, port.id, port.label, next);
      api.announce(format(api.messages.portMoved, { label: port.label, side: api.messages.sideLabels[next] ?? next }));
    },
    onCancel: () => api?.announce(api.messages.portMoveCancelled),
  });
  return (
    <Handle
      id={io === "in" ? inHandleId(port.id) : outHandleId(port.id)}
      type={io === "in" ? "target" : "source"}
      position={POSITION_OF[side]}
      className="ac-ge-handle"
      {...(editable ? { ...handlers, title: api.messages.portMoveHint } : {})}
    />
  );
}

/** 노드 가장자리 띠의 핸들 id 접두어(가상 포트: 포트가 아니라 "여기서 연결을 시작"). 포트 id와 섞이지 않게 `in:`/`out:`과 다른 접두어. */
export const BAND_HANDLE_PREFIX = "edge:";
const BAND_SIDES: readonly Side[] = ["left", "right", "top", "bottom"];

/** 선택된 노드의 가장자리 띠 4개(UX-P11). 끌면 연결이 시작되고, 끝점은 몸체 드롭에서 포트를 추론한다. 끝점으로는 쓰이지 않는다. */
function EdgeBands() {
  return (
    <>
      {BAND_SIDES.map((side) => (
        <Handle
          key={side}
          id={`${BAND_HANDLE_PREFIX}${side}`}
          type="source"
          position={POSITION_OF[side]}
          isConnectableEnd={false}
          className={`ac-ge-band ac-ge-band--${side}`}
          aria-hidden="true"
        />
      ))}
    </>
  );
}

/** 핸들 배치가 바뀌었는지 알아보는 서명(면·위치 목록). */
export const portLayoutSignature = (inputs: readonly PortView[], outputs: readonly PortView[]): string =>
  [...inputs.map((p) => `i:${p.id}:${p.side ?? ""}:${p.offset ?? ""}`), ...outputs.map((p) => `o:${p.id}:${p.side ?? ""}:${p.offset ?? ""}`)].join("|");

/** 단 하나의 노드 렌더러. 타입별 분기 없음. */
export const AcNode = memo(function AcNode({ id, data }: NodeProps<FlowNode>) {
  const updateNodeInternals = useUpdateNodeInternals();
  const signature = portLayoutSignature(data.inputs, data.outputs);
  const last = useRef(signature);
  useEffect(() => {
    // 핸들 면·위치가 바뀌면 React Flow가 핸들 위치를 다시 측정해야 선이 새 자리에 붙는다(첫 그리기는 자동 측정).
    if (last.current === signature) return;
    last.current = signature;
    updateNodeInternals(id);
  }, [id, signature, updateNodeInternals]);
  const renderPortHandle = useCallback((port: PortView, io: "in" | "out") => <PortHandle nodeId={id} port={port} io={io} />, [id]);
  const portEdit = useContext(PortEditContext);
  const bands = data.selected === true && portEdit !== null && portEdit.editable;
  const lastBands = useRef(bands);
  useEffect(() => {
    // 띠 핸들은 선택하는 순간에 생기므로 React Flow가 핸들 위치를 다시 측정해야 거기서 연결을 시작할 수 있다.
    if (lastBands.current === bands) return;
    lastBands.current = bands;
    updateNodeInternals(id);
  }, [id, bands, updateNodeInternals]);
  return <NodeCard {...data} renderPortHandle={renderPortHandle} {...(bands ? { edgeBands: <EdgeBands /> } : {})} />;
});

/** 선은 소스 경계에서, 화살촉 끝은 대상 노드 경계에서 이만큼 바깥(면의 법선 방향)에서 시작/멈춘다(tokens 4.4). */
export { ARROW_GAP };

const SIDE_OF: Readonly<Record<Position, Side>> = {
  [Position.Left]: "left",
  [Position.Right]: "right",
  [Position.Top]: "top",
  [Position.Bottom]: "bottom",
};

const FALLBACK_SHAPE = BUILTIN_EDGE_SHAPES.find((d) => d.id === FALLBACK_EDGE_SHAPE) as EdgeShapeDescriptor;
/**
 * 노드 회피 라우터가 그리는 모양(`route`)의 임시 모양: 라우터 결과가 오기 전과 경유점을 끄는 동안 쓴다.
 * 모양의 `build`(단독 A*)를 엣지마다 부르면 라우터 작업 메모리를 엣지 수만큼 만들기 때문에 쓰지 않는다.
 */
const ROUTE_PLACEHOLDER_SHAPE = BUILTIN_EDGE_SHAPES.find((d) => d.id === "smoothstep") ?? FALLBACK_SHAPE;
export { ROUTE_PLACEHOLDER_SHAPE };

/** 줌은 React Flow 저장소에서 읽는다(표현 컴포넌트는 줌을 props로만 받는다). */
function ConnectedWaypointLayer(props: Omit<EdgeWaypointLayerProps, "zoom">) {
  const zoom = useStore((s) => s.transform[2]);
  return <EdgeWaypointLayer {...props} zoom={zoom} />;
}

/** 드래그 중 미리보기 값. 손을 떼면 `onChange` 1회로 확정하고 버린다. */
interface EdgeDraft {
  waypoints?: Point[];
  labelT?: number;
  labelOffset?: Point;
}

interface ChipDrag {
  pointerId: number;
  startX: number;
  startY: number;
  started: boolean;
  t: number;
  offset: Point;
  last: EdgeDraft | null;
}

const MAX_VISIBLE_CHIPS = 4;

/** 칩 하나. `onActivate`가 있으면 단추(클릭·Enter·Space)이고, 연결 드래그로 번지지 않게 포인터 이벤트를 막는다. */
function ChipShell({ chip, full, children }: { chip: ChipView; full: string; children: ReactNode }) {
  const common = { className: "ac-ge-hint-chip", "data-tone": chip.tone ?? "neutral", "data-dashed": chip.dashed ? "true" : undefined, title: full };
  if (chip.onActivate === undefined) return <span {...common}>{children}</span>;
  return (
    <button
      type="button"
      {...common}
      aria-label={full}
      className="ac-ge-hint-chip nodrag nopan"
      onPointerDown={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation();
        chip.onActivate?.();
      }}
    >
      {children}
    </button>
  );
}

interface ChipEntry {
  key: string;
  node: ReactNode;
  text: string;
}

/** 연결 칩 줄: 선언형 칩 문구 + 앱이 준 추가 칩을 한 덩어리로, 4개째까지 보이고 나머지는 `+N`(툴팁에 전체). */
function buildChipEntries(data: FlowEdgeData | undefined): { shown: ChipEntry[]; hidden: ChipEntry[] } {
  const all: ChipEntry[] = [];
  for (const c of data?.hintChips ?? []) {
    all.push({ key: `h:${c}`, text: c, node: <span className="ac-ge-hint-chip">{c}</span> });
  }
  for (const c of data?.extraChips ?? []) {
    const full = c.fullTitle ?? c.title;
    const icon = c.iconName !== undefined ? (data?.renderIcon?.(c.iconName) ?? c.iconText ?? null) : (c.iconText ?? null);
    all.push({
      key: `x:${c.key}`,
      text: full,
      node: (
        <ChipShell chip={c} full={full}>
          {icon !== null && icon !== undefined && icon !== false ? <span aria-hidden="true" className="ac-ge-chip-icon">{icon}</span> : null}
          {c.title}
        </ChipShell>
      ),
    });
  }
  return { shown: all.slice(0, MAX_VISIBLE_CHIPS), hidden: all.slice(MAX_VISIBLE_CHIPS) };
}

export const AcEdge = memo(function AcEdge(props: EdgeProps<FlowEdge>) {
  const { sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, selected } = props;
  const edit = useContext(EdgeEditContext);
  const shape = data?.shape ?? FALLBACK_SHAPE;
  const routes = useContext(EdgeRouteContext);
  const canEdit = edit !== null && edit.editable && selected === true;
  const pathMode = canEdit && edit.pathEditEdgeId === props.id;
  const [draft, setDraft] = useState<EdgeDraft | null>(null);
  const chipDrag = useRef<ChipDrag | null>(null);
  const wps = draft?.waypoints ?? data?.waypoints ?? null;
  const labelT = draft?.labelT ?? data?.labelT ?? 0.5;
  const labelOffset = draft?.labelOffset ?? data?.labelOffset;
  // 자동 경로: 편집기가 모든 엣지를 한 번에 계산한 결과를 쓴다. 경유점을 끄는 중(draft)이거나 아직 계산 전이면 임시 모양
  const routed = shape.route !== undefined && routes !== null && draft?.waypoints === undefined ? routes.get(props.id) : undefined;
  const result =
    routed !== undefined
      ? routed.path
      : buildEdgePath({
          source: { x: sourceX, y: sourceY, side: SIDE_OF[sourcePosition] },
          target: { x: targetX, y: targetY, side: SIDE_OF[targetPosition] },
          waypoints: wps,
          shape: shape.route !== undefined && routes !== null ? ROUTE_PLACEHOLDER_SHAPE : shape,
          radius: data?.radius ?? null,
          bend: data?.bend ?? null,
        });
  const path = result.d;
  const at = result.labelAt(labelT);
  const labelX = at.x + (labelOffset?.x ?? 0);
  const labelY = at.y + (labelOffset?.y ?? 0);
  const style: CSSProperties | undefined =
    data?.color !== undefined || data?.dash !== undefined
      ? ({
          ...(data.color !== undefined ? { "--ac-ge-edge-color": data.color } : {}),
          ...(data.dash !== undefined ? { "--ac-ge-edge-dash": data.dash } : {}),
          ...(data.linecap !== undefined ? { strokeLinecap: data.linecap } : {}),
        } as CSSProperties)
      : undefined;
  const source = { x: sourceX, y: sourceY };
  const target = { x: targetX, y: targetY };

  const onPathDoubleClick = (e: ReactMouseEvent): void => {
    if (!canEdit || !shape.supportsWaypoints) return;
    const current = data?.waypoints ?? [];
    const click = edit.screenToFlow({ x: e.clientX, y: e.clientY });
    const on = nearestOnSegments(result.segments, click)?.point ?? click;
    const pt = { x: Math.round(on.x * 10) / 10, y: Math.round(on.y * 10) / 10 };
    const index = insertIndexFor(source, current, target, pt);
    const next = insertWaypoint(current, index, pt);
    if (next === null) {
      edit.notify(format(edit.messages.waypointLimit, { max: MAX_WAYPOINTS }));
      return;
    }
    edit.commit(props.id, { waypoints: next });
    edit.announce(format(edit.messages.waypointAdded, { i: index + 1, x: Math.round(pt.x), y: Math.round(pt.y) }));
  };

  const chipHandlers = canEdit
    ? {
        onPointerDown: (e: ReactPointerEvent<HTMLElement>) => {
          if (e.button !== 0) return;
          e.stopPropagation();
          e.currentTarget.setPointerCapture?.(e.pointerId);
          chipDrag.current = { pointerId: e.pointerId, startX: e.clientX, startY: e.clientY, started: false, t: labelT, offset: labelOffset ?? { x: 0, y: 0 }, last: null };
        },
        onPointerMove: (e: ReactPointerEvent<HTMLElement>) => {
          const d = chipDrag.current;
          if (d === null || e.pointerId !== d.pointerId) return;
          if (!d.started && Math.hypot(e.clientX - d.startX, e.clientY - d.startY) < DRAG_THRESHOLD) return;
          d.started = true;
          const p = edit.screenToFlow({ x: e.clientX, y: e.clientY });
          if (e.shiftKey) {
            // 경로에서 떼어 자유 위치(label_offset)
            const base = result.labelAt(d.t);
            d.last = { labelT: d.t, labelOffset: { x: Math.round(p.x - base.x), y: Math.round(p.y - base.y) } };
          } else {
            // 경로를 따라서만(label_t). 이미 뗀 어긋남은 유지
            d.last = { labelT: nearestLabelT(result.labelAt, { x: p.x - d.offset.x, y: p.y - d.offset.y }), labelOffset: d.offset };
          }
          setDraft(d.last);
        },
        onPointerUp: (e: ReactPointerEvent<HTMLElement>) => {
          const d = chipDrag.current;
          if (d === null || e.pointerId !== d.pointerId) return;
          chipDrag.current = null;
          e.currentTarget.releasePointerCapture?.(e.pointerId);
          const last = d.last;
          if (!d.started || last === null) {
            setDraft(null);
            return;
          }
          const patch: { label_t?: number; label_offset?: Point } = {};
          if (last.labelT !== undefined && last.labelT !== d.t) patch.label_t = last.labelT;
          if (last.labelOffset !== undefined && (last.labelOffset.x !== d.offset.x || last.labelOffset.y !== d.offset.y)) patch.label_offset = last.labelOffset;
          if (Object.keys(patch).length > 0) {
            edit.commit(props.id, patch);
            edit.announce(format(edit.messages.labelMoved, { pct: Math.round((patch.label_t ?? d.t) * 100) }));
          }
          setDraft(null);
        },
        onPointerCancel: () => {
          chipDrag.current = null;
          setDraft(null);
        },
        onDoubleClick: (e: ReactMouseEvent) => {
          e.stopPropagation();
          edit.commit(props.id, RESET_LABEL_PATCH);
          edit.announce(edit.messages.labelReset);
        },
        ...(pathMode
          ? {
              tabIndex: 0,
              role: "slider" as const,
              "aria-valuemin": 10,
              "aria-valuemax": 90,
              "aria-valuenow": Math.round(labelT * 100),
              "aria-label": format(edit.messages.labelHandleAria, { pct: Math.round(labelT * 100) }),
              onKeyDown: (e: KeyboardEvent<HTMLElement>) => {
                if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
                  e.preventDefault();
                  e.stopPropagation();
                  const next = snapLabelT(labelT + (e.key === "ArrowRight" ? 0.05 : -0.05));
                  edit.commit(props.id, { label_t: next });
                  edit.announce(format(edit.messages.labelMoved, { pct: Math.round(next * 100) }));
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  e.stopPropagation();
                  edit.exitPathEdit(props.id);
                }
              },
            }
          : {}),
      }
    : {};

  const chips = buildChipEntries(data);
  const iconNode: ReactNode =
    data?.iconName === undefined ? null : (data.renderIcon?.(data.iconName) ?? (data.iconFallback !== undefined && data.iconFallback !== "" ? data.iconFallback : null));

  // 새 데이터(아이콘·추가 칩·배지)가 없으면 이전과 글자 단위로 같은 DOM을 낸다(`flow.snapshot.test.tsx`)
  const extended = iconNode !== null || (data?.extraChips?.length ?? 0) > 0 || (data?.runBadges?.length ?? 0) > 0;
  const chipBody = (
    <>
      {data?.invalid ? `${data.invalidText} ` : ""}
      {data?.label}
      {chips.shown.map((c) => (
        <Fragment key={c.key}>{c.node}</Fragment>
      ))}
      {chips.hidden.length > 0 && (
        <span className="ac-ge-hint-chip" data-more="true" title={chips.hidden.map((c) => c.text).join(", ")}>
          {format(edit?.messages.edgeChipsMore ?? "+{n}", { n: chips.hidden.length })}
        </span>
      )}
    </>
  );

  const baseEdge = (
    <BaseEdge
      id={props.id}
      path={path}
      markerEnd={`url(#${data?.markerId ?? ""})`}
      interactionWidth={16}
      className="ac-ge-edge"
      style={style}
      {...(routed !== undefined ? routeFallbackAttrs(routed) : {})}
    />
  );
  return (
    <>
      {canEdit ? <g onDoubleClick={onPathDoubleClick}>{baseEdge}</g> : baseEdge}
      {canEdit && labelOffset !== undefined && (labelOffset.x !== 0 || labelOffset.y !== 0) && (
        <line className="ac-ge-edge-leader" x1={at.x} y1={at.y} x2={labelX} y2={labelY} />
      )}
      <EdgeLabelRenderer>
        {canEdit && shape.supportsWaypoints && (
          <ConnectedWaypointLayer
            source={source}
            target={target}
            waypoints={wps ?? []}
            segments={result.segments}
            screenToFlow={edit.screenToFlow}
            snapGrid={edit.snapGrid}
            keyboardMode={pathMode}
            messages={edit.messages}
            onDraft={(next) => setDraft(next === null ? null : { waypoints: next })}
            onCommit={(next) => edit.commit(props.id, { waypoints: next })}
            onLimit={() => edit.notify(format(edit.messages.waypointLimit, { max: MAX_WAYPOINTS }))}
            onAnnounce={edit.announce}
            onExit={() => edit.exitPathEdit(props.id)}
            onZoomHint={edit.zoomHint}
          />
        )}
        <div
          className={canEdit ? "ac-ge-edge-chip ac-ellipsis nodrag nopan" : "ac-ge-edge-chip ac-ellipsis"}
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          data-selected={selected ? "true" : undefined}
          data-invalid={data?.invalid ? "true" : undefined}
          data-edge-state={data?.state}
          data-badged={
            data?.orderBadge !== undefined ||
            data?.countBadge !== undefined ||
            (data?.hintChips?.length ?? 0) > 0 ||
            (data?.extraChips?.length ?? 0) > 0 ||
            (data?.runBadges?.length ?? 0) > 0 ||
            data?.iconFromProperty === true
              ? "true"
              : undefined
          }
          data-wide={(data?.extraChips?.length ?? 0) > 0 || (data?.runBadges?.length ?? 0) > 0 ? "true" : undefined}
          data-edge-id={extended ? props.id : undefined}
          title={data?.label}
          {...chipHandlers}
        >
          {data?.orderBadge !== undefined && (
            <span className="ac-ge-order" title={data.orderText} aria-label={data.orderText}>
              {data.orderBadge}
            </span>
          )}
          {iconNode !== null && (
            <span className="ac-ge-edge-icon" aria-hidden="true" data-edge-icon={data?.iconName}>
              {iconNode}
            </span>
          )}
          {iconNode !== null ? <span className="ac-ge-chip-text">{chipBody}</span> : chipBody}
          {data?.runBadges?.map((b, i) => (
            <span key={i} className="ac-ge-run-badge" data-tone={b.tone ?? "neutral"} title={b.ariaLabel} aria-label={b.ariaLabel}>
              {b.text}
            </span>
          ))}
          {data?.countBadge !== undefined && (
            <span className="ac-ge-count" title={data.countText} aria-label={data.countText}>
              ×{data.countBadge}
            </span>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
});
