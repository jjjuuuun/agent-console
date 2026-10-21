import type { ReactNode } from "react";
import type { DelegationStrategyDescriptor, EdgeSpec, EdgeTypeDescriptor, Graph, GraphUiLayout, NodeSpec, NodeTypeDescriptor, PortSpec } from "@agent-console/contracts";
import type { GraphEditorMessages } from "../messages";
import { format } from "../messages";
import { categoryColorVar } from "./color";
import { pickDescriptor } from "./descriptors";
import { resolveHints } from "./hints";
import { edgesOf, nodesOf } from "./ops";
import { buildNodePorts, inHandleId, outHandleId, staticPorts } from "./ports";
import type { NodePorts } from "./ports";
import { measureChipSize, measureNodeSize } from "./size";
import type { ResourceChip } from "./team";
import { declaredLabels, declaredTexts } from "./declared";
import { placeHandles } from "./handles";
import { AUTO_SIDE, BUILTIN_DIRECTIONS, FALLBACK_EDGE_SHAPE, builtinEdgeShape, SIDES, isAutoDirection, portLayoutKey, resolveEdgeShape, resolvePortSide } from "./layout";
import { deriveAutoSides } from "./autoSide";
import type { Side } from "../shapes/types";
import type { DirectionSides } from "./layout";
import { BUILTIN_EDGE_SHAPES, createEdgeShapeRegistry } from "../shapes/registry";
import type { EdgeShapeRegistry } from "../shapes/registry";
import type { EdgeShapeDescriptor } from "../shapes/types";
import { schedulingOf } from "./ops";
import { deriveNodeBadges, deriveResourceChips, formatElapsed, isChipShape, nonExecutableNodeIds } from "./team";
import type { NodeAvatar, BindSummary, ChipView, EdgeBadge, NodeRunBadge, NodeStateView } from "../types";
import { resolveEdgeStyle } from "./edgeStyle";
import type { IssueSummary } from "./issues";
import { nodeAriaLabel } from "../components/NodeCard";
import type { FlowEdge, FlowNode } from "../components/flow";

export { pickDescriptor };

export interface ResolvedPortsInfo {
  spec: PortSpec | undefined;
  loading: boolean;
  failed: boolean;
}

export interface FlowModelInput {
  graph: Graph;
  nodeTypes: readonly NodeTypeDescriptor[];
  edgeTypes: readonly EdgeTypeDescriptor[];
  /** 동적 포트 계산 결과(노드 id 기준). 정적 포트는 여기 없어도 된다 */
  resolved: ReadonlyMap<string, ResolvedPortsInfo>;
  nodeStates: Readonly<Record<string, NodeStateView>>;
  edgeStates: Readonly<Record<string, string>>;
  selectedNodes: ReadonlySet<string>;
  selectedEdges: ReadonlySet<string>;
  positionOverrides: ReadonlyMap<string, { x: number; y: number }>;
  readOnly: boolean;
  messages: GraphEditorMessages;
  markerId: string;
  issues?: IssueSummary;
  /** 리소스 보기. false면 `executable=false` 노드와 그 연결을 숨기고 도착 카드에 칩 줄을 단다. 기본 true */
  showResources?: boolean;
  portLabels?: "auto" | "always";
  waitingNodes?: Readonly<Record<string, { since: string }>>;
  nowMs?: number;
  edgeOrder?: Readonly<Record<string, number>>;
  edgeCounts?: Readonly<Record<string, number>>;
  nodeBadgesOverride?: Readonly<Record<string, readonly string[]>>;
  onResourceChipsClick?: (nodeId: string) => void;
  /** 연결선 모양 레지스트리(생략 = 내장 5종) */
  edgeShapes?: EdgeShapeRegistry;
  /** 사용자 설정 층: `settings.editor.default_direction`·`default_edge_shape`(graph-edges §1.3·§3.2) */
  layoutDefaults?: { direction?: string | null; edgeShape?: string | null };
  /** 방향 어휘 표(생략 = 내장 lr·tb·rl·bt) */
  directions?: DirectionSides;
  nodeRunBadges?: Readonly<Record<string, NodeRunBadge>>;
  edgeBadges?: Readonly<Record<string, readonly EdgeBadge[]>>;
  edgeExtraChips?: Readonly<Record<string, readonly ChipView[]>>;
  bindSummaries?: Readonly<Record<string, BindSummary>>;
  nodeAvatars?: Readonly<Record<string, NodeAvatar>>;
  delegationStrategies?: readonly Pick<DelegationStrategyDescriptor, "id">[];
  edgeStrategyIds?: Readonly<Record<string, string>>;
  renderIcon?: (name: string) => ReactNode;
  /** 반복 영역 윤곽을 그릴 노드 id(연결 선택 중에만 앱이 아닌 편집기가 계산해 넘긴다) */
  loopRegionNodes?: ReadonlySet<string>;
}

/** 정의 바인딩 카드가 더하는 높이 추정(본문 한 줄 + 배지 줄 + [열기] 줄). 실제 높이는 DOM 측정이 바로잡는다. */
const BIND_META_H = 18;
const BIND_BADGES_H = 22;
const BIND_OPEN_H = 28;

export interface FlowModel {
  nodes: FlowNode[];
  edges: FlowEdge[];
  /** 노드 id → 최종 포트(설정 패널·접근성에 사용) */
  ports: Map<string, NodePorts>;
  /** 노드 id → 권위 있는 포트 스펙 */
  specs: Map<string, PortSpec | undefined>;
}

const BUILTIN_REGISTRY = createEdgeShapeRegistry(BUILTIN_EDGE_SHAPES);
const hintString = (hints: { [k: string]: unknown } | null | undefined, key: string): string | null => {
  const v = hints?.[key];
  return typeof v === "string" ? v : null;
};
const graphLayoutOf = (g: Graph): GraphUiLayout | null => {
  const v = g.ui?.["layout"];
  return v !== null && typeof v === "object" ? (v as GraphUiLayout) : null;
};

/** 접근성 이름에 덧붙이는 모양·경유점 문구(graph-edges §6.2). 엣지에 적힌 값이 없으면 빈 문자열(기존 문구 그대로). */
function layoutAriaSuffix(e: EdgeSpec, registry: EdgeShapeRegistry, m: GraphEditorMessages): string {
  const own = e.layout?.shape ? registry.get(e.layout.shape) : undefined;
  const n = e.layout?.waypoints?.length ?? 0;
  return (own !== undefined ? format(m.edgeAriaShape, { title: own.title }) : "") + (n > 0 ? format(m.edgeAriaWaypoints, { n }) : "");
}

const classSafe = (s: string): string => s.replace(/[^A-Za-z0-9_-]/g, "_");

/** 그래프 + 디스크립터 + 오버레이 → React Flow 노드/엣지(순수 함수). */
export function buildFlowModel(i: FlowModelInput): FlowModel {
  const gNodes = nodesOf(i.graph);
  const gEdges = edgesOf(i.graph);
  const byId = new Map(gNodes.map((n) => [n.id, n]));
  const ports = new Map<string, NodePorts>();
  const specs = new Map<string, PortSpec | undefined>();
  const showResources = i.showResources !== false;
  const hiddenIds = showResources ? new Set<string>() : nonExecutableNodeIds(i.graph, i.nodeTypes);
  const chips: Map<string, ResourceChip[]> = showResources
    ? new Map()
    : deriveResourceChips(i.graph, i.nodeTypes, (d, title) => resolveHints(d?.ui_hints, d?.title ?? title).iconText);
  const graphLayout = graphLayoutOf(i.graph);
  const directions = i.directions ?? BUILTIN_DIRECTIONS;
  const connectedIn = new Set<string>();
  const connectedOut = new Set<string>();
  for (const e of gEdges) {
    connectedOut.add(`${e.source.node}\u0000${e.source.port}`);
    connectedIn.add(`${e.target.node}\u0000${e.target.port}`);
  }
  const mark = (id: string, list: NodePorts["inputs"], set: Set<string>) =>
    list.map((p) => (set.has(`${id}\u0000${p.id}`) ? { ...p, connected: true } : p));
  // 노드마다 한 번만 계산하는 준비 값(포트·라벨·크기). 면 `auto` 파생이 다른 노드의 크기를 먼저 알아야 해서 따로 뺐다.
  const prepared = new Map<string, ReturnType<typeof prepare>>();
  function prepare(n: NodeSpec) {
    const d = pickDescriptor(n, i.nodeTypes);
    const info = i.resolved.get(n.id);
    const spec = d === undefined ? undefined : d.dynamic_ports === true ? info?.spec : staticPorts(d);
    const np = buildNodePorts(n.id, spec, gEdges);
    const label = n.label !== null && n.label !== undefined && n.label !== "" ? n.label : (d?.title ?? n.type);
    const typeTitle = d?.title ?? n.type;
    const state = i.nodeStates[n.id];
    const compact = isChipShape(d);
    const bind = i.bindSummaries?.[n.id];
    const shownTypeTitle = d === undefined ? format(i.messages.unknownType, { type: n.type }) : (bind?.subtitle ?? typeTitle);
    const base = compact
      ? measureChipSize(label, shownTypeTitle)
      : measureNodeSize({
          label,
          typeTitle: shownTypeTitle,
          inputLabels: np.inputs.map((p) => p.label),
          outputLabels: np.outputs.map((p) => p.label),
          hasSummary: state?.summary !== undefined || state?.errorSummary !== undefined,
        });
    const extraH = bind === undefined ? 0 : (bind.meta ? BIND_META_H : 0) + (bind.badges?.length ? BIND_BADGES_H : 0) + (bind.open ? BIND_OPEN_H : 0);
    const size = extraH > 0 ? { ...base, height: base.height + extraH } : base;
    return { d, info, spec, np, label, typeTitle, state, compact, size, bind };
  }
  const visible = gNodes.filter((n) => !hiddenIds.has(n.id));
  for (const n of visible) prepared.set(n.id, prepare(n));
  // 면 `auto`: 저장된 위치(드롭 시점)와 크기로만 파생한다. 드래그 중 임시 위치(positionOverrides)는 쓰지 않는다.
  // 포트별 값이 `auto`이거나, 노드 방향이 `auto`(노드 → 그래프 → 설정 → 힌트 중 처음 유효한 값)인데 포트별 지정이 없는 포트가 대상이다.
  const directionAuto = new Map<string, boolean>();
  const wanted = new Map<string, Set<string>>();
  for (const n of visible) {
    const p = prepared.get(n.id)!;
    const auto = isAutoDirection({ node: n.layout ?? null, graph: graphLayout, settings: i.layoutDefaults?.direction ?? null, hint: hintString(p.d?.ui_hints, "direction"), directions });
    directionAuto.set(n.id, auto);
    const own = n.layout?.ports ?? {};
    const keys = new Set(Object.entries(own).filter(([, v]) => v === AUTO_SIDE).map(([k]) => k));
    if (auto) {
      const all = [...p.np.inputs.map((x) => portLayoutKey("in", x.id)), ...p.np.outputs.map((x) => portLayoutKey("out", x.id))];
      for (const k of all) if (!(SIDES as readonly string[]).includes(own[k] ?? "")) keys.add(k);
    }
    if (keys.size > 0) wanted.set(n.id, keys);
  }
  const boxes = new Map(visible.map((n) => [n.id, { x: n.position?.x ?? 0, y: n.position?.y ?? 0, ...prepared.get(n.id)!.size }]));
  const shownEdges = gEdges.filter((e) => !hiddenIds.has(e.source.node) && !hiddenIds.has(e.target.node));
  const autoSides = wanted.size === 0 ? new Map<string, ReadonlyMap<string, Side>>() : deriveAutoSides(boxes, shownEdges, wanted);
  // 같은 면 핸들 순서: 포트마다 연결 상대 노드 중심의 평균(저장된 위치 기준, 드래그 중에는 바뀌지 않는다)
  const peerSums = new Map<string, { x: number; y: number; n: number }>();
  const addPeer = (self: string, key: string, other: string): void => {
    const o = boxes.get(other);
    if (o === undefined || self === other) return;
    const k = `${self}\u0000${key}`;
    const cur = peerSums.get(k) ?? { x: 0, y: 0, n: 0 };
    peerSums.set(k, { x: cur.x + o.x + o.width / 2, y: cur.y + o.y + o.height / 2, n: cur.n + 1 });
  };
  for (const e of shownEdges) {
    addPeer(e.source.node, portLayoutKey("out", e.source.port), e.target.node);
    addPeer(e.target.node, portLayoutKey("in", e.target.port), e.source.node);
  }
  const nodes: FlowNode[] = visible.map((n) => {
    const { d, info, spec, np, label, typeTitle, state, compact, size, bind } = prepared.get(n.id)!;
    const hints = resolveHints(d?.ui_hints, d?.title ?? n.type);
    specs.set(n.id, spec);
    ports.set(n.id, np);
    const badges = [
      ...deriveNodeBadges(n.id, i.graph, i.edgeTypes).map((b) => i.messages.badgeLabels[b] ?? b),
      ...(i.nodeBadgesOverride?.[n.id] ?? []),
    ];
    const kindOf = new Map(i.edgeTypes.map((t) => [t.id, t]));
    const incomingScheduling = gEdges.filter((e) => e.target.node === n.id).map((e) => schedulingOf(kindOf.get(e.kind)));
    const outgoingScheduling = gEdges.filter((e) => e.source.node === n.id).map((e) => schedulingOf(kindOf.get(e.kind)));
    const declCtx = { config: n.config, incomingScheduling, outgoingScheduling };
    badges.push(...declaredLabels(d?.ui_hints, "badges", declCtx, i.messages).filter((b) => !badges.includes(b)));
    const hintChips = declaredLabels(d?.ui_hints, "chips", declCtx, i.messages);
    const nodeChips = chips.get(n.id);
    const waiting = i.waitingNodes?.[n.id];
    const override = i.positionOverrides.get(n.id);
    const sideInput = {
      node: n.layout ?? null,
      graph: graphLayout,
      settings: i.layoutDefaults?.direction ?? null,
      hint: hintString(d?.ui_hints, "direction"),
      directions,
    };
    const withSide = (list: NodePorts["inputs"], io: "in" | "out") =>
      list.map((p) => ({ ...p, side: resolvePortSide({ ...sideInput, io, portId: p.id, autoSide: autoSides.get(n.id)?.get(portLayoutKey(io, p.id)), autoDirection: directionAuto.get(n.id) === true }).side }));
    const defaultRow = BUILTIN_DIRECTIONS["lr"];
    const placed = placeHandles({
      inputs: withSide(mark(n.id, np.inputs, connectedIn), "in"),
      outputs: withSide(mark(n.id, np.outputs, connectedOut), "out"),
      width: size.width,
      compact,
      peerOf: (io, portId) => {
        const v = peerSums.get(`${n.id}\u0000${portLayoutKey(io, portId)}`);
        return v === undefined ? undefined : { x: v.x / v.n, y: v.y / v.n };
      },
      ...(defaultRow !== undefined ? { defaultSides: defaultRow } : {}),
    });
    const data: FlowNode["data"] = {
      label,
      typeTitle,
      accent: d === undefined ? "var(--ac-cat-neutral)" : (hints.color ?? categoryColorVar(d.category)),
      iconText: i.nodeAvatars?.[n.id]?.text ?? hints.iconText,
      inputs: placed.inputs,
      outputs: placed.outputs,
      selected: i.selectedNodes.has(n.id),
      width: size.width,
      portsLoading: info?.loading === true,
      portsFailed: info?.failed === true,
      messages: i.messages,
      portLabels: i.portLabels ?? "auto",
    };
    const avatarColor = i.nodeAvatars?.[n.id]?.color;
    if (avatarColor !== undefined) data.avatarColor = avatarColor;
    if (compact) data.compact = true;
    if (d?.ui_hints?.shape === "stacked") data.stacked = true;
    if (bind !== undefined) data.bind = bind;
    const runBadge = i.nodeRunBadges?.[n.id];
    if (runBadge !== undefined) data.runBadge = runBadge;
    if (i.loopRegionNodes?.has(n.id) === true) data.loopRegion = true;
    if (hints.dashed) data.dashed = true;
    if (badges.length > 0) data.badges = badges;
    if (hintChips.length > 0) data.hintChips = hintChips;
    if (nodeChips !== undefined && nodeChips.length > 0) {
      data.resourceChips = nodeChips;
      if (i.onResourceChipsClick !== undefined) {
        const cb = i.onResourceChipsClick;
        data.onResourceChipsClick = () => cb(n.id);
      }
    }
    if (waiting !== undefined) {
      const since = Date.parse(waiting.since);
      const elapsed = Number.isNaN(since) ? "" : formatElapsed((i.nowMs ?? Date.now()) - since, i.messages);
      data.waitingText = format(i.messages.waitingFor, { elapsed }).trim();
    }
    if (state !== undefined) data.state = state;
    const ic = i.issues?.nodes.get(n.id);
    if (ic !== undefined && ic.error + ic.warning > 0) data.issueCount = { error: ic.error, warning: ic.warning };
    if (d === undefined) data.unknownType = n.type;
    return {
      id: n.id,
      type: "ac-node",
      position: override ?? { x: n.position?.x ?? 0, y: n.position?.y ?? 0 },
      data,
      selected: i.selectedNodes.has(n.id),
      draggable: !i.readOnly,
      connectable: !i.readOnly,
      deletable: false,
      focusable: true,
      initialWidth: size.width,
      initialHeight: size.height,
      ariaLabel: nodeAriaLabel({ label, typeTitle, ...(state !== undefined ? { state } : {}), ...(data.issueCount !== undefined ? { issueCount: data.issueCount } : {}), ...(bind !== undefined ? { bind } : {}), ...(runBadge !== undefined ? { runBadge } : {}) }, i.messages),
    };
  });

  const kinds = new Map(i.edgeTypes.map((t) => [t.id, t]));
  const edges: FlowEdge[] = [];
  for (const e of gEdges) {
    const s = byId.get(e.source.node);
    const t = byId.get(e.target.node);
    if (s === undefined || t === undefined) continue; // 끝점 노드가 없으면 그릴 수 없다(검증 이슈 몫)
    if (hiddenIds.has(e.source.node) || hiddenIds.has(e.target.node)) continue; // 리소스 보기 끔
    edges.push(toFlowEdge(e, s, t, ports, kinds.get(e.kind), i));
  }
  return { nodes, edges, ports, specs };
}

function toFlowEdge(
  e: EdgeSpec,
  s: NodeSpec,
  t: NodeSpec,
  ports: ReadonlyMap<string, NodePorts>,
  kind: EdgeTypeDescriptor | undefined,
  i: FlowModelInput,
): FlowEdge {
  const sp = ports.get(s.id);
  const tp = ports.get(t.id);
  const invalid =
    i.issues?.edges.has(e.id) === true ||
    sp?.outputs.find((p) => p.id === e.source.port)?.missing === true || tp?.inputs.find((p) => p.id === e.target.port)?.missing === true;
  const hints = resolveHints(kind?.ui_hints, kind?.title ?? e.kind);
  // 속성 기반 스타일(`ui_hints`가 항상 우선). 알 수 없는 종류는 속성을 모르므로 내장 기본.
  const style = resolveEdgeStyle(kind, i.delegationStrategies ?? [], { strategyId: i.edgeStrategyIds?.[e.id] ?? null });
  const state = i.edgeStates[e.id];
  const sLabel = s.label ?? s.id;
  const tLabel = t.label ?? t.id;
  const classes = ["ac-ge-edge-wrap"];
  if (invalid) classes.push("ac-ge-edge--invalid");
  if (hints.dashed) classes.push("ac-ge-edge--dashed");
  if (state !== undefined) classes.push(`ac-ge-edge--${classSafe(state)}`);
  const base = kind?.title ?? format(i.messages.unknownEdgeKind, { kind: e.kind });
  const declCtx = { config: e.config };
  // 라벨 추가 문구는 선언형 칩만(E-4): `placement: "title"` 칩은 종류 title 뒤에 붙고, 나머지는 작은 칩이다. config 키는 읽지 않는다.
  const declared = [
    ...declaredTexts(kind?.ui_hints, "badges", declCtx, i.messages),
    ...declaredTexts(kind?.ui_hints, "chips", declCtx, i.messages),
  ];
  const titleParts: string[] = [];
  if (e.label !== null && e.label !== undefined && e.label !== "") titleParts.push(e.label);
  for (const t of declared) if (t.placement === "title" && !titleParts.includes(t.text)) titleParts.push(t.text);
  const registry = i.edgeShapes ?? BUILTIN_REGISTRY;
  const shape = pickShape(e, kind, i, registry);
  const order = i.edgeOrder?.[e.id];
  const count = i.edgeCounts?.[e.id];
  const data: FlowEdge["data"] = {
    label: [base, ...titleParts].join(" · "),
    dashed: hints.dashed,
    invalid,
    invalidText: i.messages.edgeInvalid,
    markerId: i.markerId,
    shape,
  };
  const hintChips: string[] = [];
  for (const t of declared) if (t.placement !== "title" && !hintChips.includes(t.text)) hintChips.push(t.text);
  if (hintChips.length > 0) data.hintChips = hintChips;
  if (style.color !== undefined) data.color = style.color;
  if (style.dasharray !== undefined) {
    data.dash = style.dasharray;
    classes.push("ac-ge-edge--patterned");
    if (style.linecap !== undefined) data.linecap = style.linecap;
  }
  if (style.iconName !== undefined) {
    data.iconName = style.iconName;
    data.iconFromProperty = style.source.iconName === "property";
    data.iconFallback = style.iconName.length <= 2 ? style.iconName : hints.iconText;
  }
  if (i.renderIcon !== undefined) data.renderIcon = i.renderIcon;
  const extra = i.edgeExtraChips?.[e.id];
  if (extra !== undefined && extra.length > 0) data.extraChips = [...extra];
  const badges = i.edgeBadges?.[e.id];
  if (badges !== undefined && badges.length > 0) data.runBadges = badges.map((b) => ({ ...b }));
  data.kindTitle = base;
  const lay = e.layout ?? null;
  if (lay?.waypoints) data.waypoints = lay.waypoints.map((p) => ({ x: p.x, y: p.y }));
  if (typeof lay?.radius === "number") data.radius = lay.radius;
  if (typeof lay?.bend === "number") data.bend = lay.bend;
  if (typeof lay?.label_t === "number") data.labelT = Math.min(0.9, Math.max(0.1, lay.label_t));
  if (lay?.label_offset) data.labelOffset = { x: lay.label_offset.x, y: lay.label_offset.y };
  if (state !== undefined) data.state = state;
  if (order !== undefined) {
    data.orderBadge = order;
    data.orderText = format(i.messages.edgeOrderBadge, { n: order });
  }
  if (count !== undefined) {
    data.countBadge = count;
    data.countText = format(i.messages.edgeCountBadge, { n: count });
  }
  const chipTexts = [...(data.hintChips ?? []), ...(extra ?? []).map((c) => c.fullTitle ?? c.title), ...(badges ?? []).map((b) => b.ariaLabel)];
  return {
    id: e.id,
    type: "ac-edge",
    source: e.source.node,
    target: e.target.node,
    sourceHandle: outHandleId(e.source.port),
    targetHandle: inHandleId(e.target.port),
    selected: i.selectedEdges.has(e.id),
    deletable: false,
    focusable: true,
    className: classes.join(" "),
    data,
    ariaLabel:
      format(i.messages.edgeAria, { source: sLabel, sourcePort: e.source.port, target: tLabel, targetPort: e.target.port }) +
      layoutAriaSuffix(e, registry, i.messages) +
      (chipTexts.length > 0 ? `; ${[format(i.messages.edgeAriaKind, { title: base }), ...chipTexts].join("; ")}` : ""),
  };
}

/** 엣지의 모양: 엣지 → 그래프(종류별·전체) → 사용자 설정 → 디스크립터 힌트 → 내장(`auto`, 직접 고친 선·레지스트리에 `auto`가 없으면 `bezier`). 레지스트리에 없는 값은 건너뛴다. */
function pickShape(e: EdgeSpec, kind: EdgeTypeDescriptor | undefined, i: FlowModelInput, registry: EdgeShapeRegistry): EdgeShapeDescriptor {
  return inheritedEdgeShape(e, kind, i, registry, false);
}

/**
 * 엣지 자신의 `layout.shape`를 뺀 상속 결과 모양(연결 패널의 "상속 (현재: …)" 표시, `S` 키 안내).
 * `ignoreEdgeLayer`가 false면 엣지 층까지 본 최종 모양이다.
 */
export function inheritedEdgeShape(
  e: EdgeSpec,
  kind: EdgeTypeDescriptor | undefined,
  i: Pick<FlowModelInput, "graph" | "layoutDefaults">,
  registry: EdgeShapeRegistry = BUILTIN_REGISTRY,
  ignoreEdgeLayer = true,
): EdgeShapeDescriptor {
  const propertyShape = resolveEdgeStyle(kind).defaultShape;
  const r = resolveEdgeShape({
    edge: ignoreEdgeLayer ? null : (e.layout ?? null),
    kind: e.kind,
    graph: graphLayoutOf(i.graph),
    settings: i.layoutDefaults?.edgeShape ?? null,
    // 힌트(`ui_hints.edge_shape`)가 없으면 디스크립터 속성의 기본 모양(반복 연결 = 자동 경로). 레지스트리에 없으면 건너뛴다.
    hint: ((h) => (h !== null && registry.has(h) ? h : propertyShape !== undefined && registry.has(propertyShape) ? propertyShape : h))(hintString(kind?.ui_hints, "edge_shape")),
    isKnown: registry.has,
    fallback: builtinEdgeShape(e.layout, registry.has),
  });
  return registry.get(r.value) ?? registry.get(FALLBACK_EDGE_SHAPE) ?? BUILTIN_REGISTRY.list[0]!;
}
