/**
 * 팀 구성 모드의 순수 로직. UI·캔버스 라이브러리를 모른다.
 *
 * 규칙: 노드 타입 id·엣지 종류 id를 비교하지 않는다. 판단 근거는 디스크립터 속성뿐이다.
 *  - 엣지: `scheduling`(flow/none/entry/exit), `interaction`, `invocation`, `connects`, `default_ports`
 *  - 노드: `role`, `executable`, `binds`, `ui_hints.hidden/shape`
 */
import type {
  EdgeSpec,
  EdgeTypeDescriptor,
  Graph,
  GraphPatch,
  NodeSpec,
  NodeTypeDescriptor,
  PortSpec,
} from "@agent-console/contracts";
import { format } from "../messages";
import type { GraphEditorMessages } from "../messages";
import { pickDescriptor } from "./descriptors";
import { defaultIdFactory, edgesOf, nodesOf, schedulingOf } from "./ops";
import type { IdFactory } from "./ops";

/** 같은 id의 여러 버전 중 최신만 남긴다(입력 순서 유지). */
export function latestVersions<T extends { id: string; version?: number }>(items: readonly T[]): T[] {
  const best = new Map<string, T>();
  for (const t of items) {
    const cur = best.get(t.id);
    if (cur === undefined || (t.version ?? 0) >= (cur.version ?? 0)) best.set(t.id, t);
  }
  return [...best.values()];
}

/** 팔레트·목록에서 숨기는 타입인가(`ui_hints.hidden`). 이미 그래프에 있는 노드는 그대로 그린다. */
export const isHiddenType = (d: { ui_hints?: { hidden?: boolean | null } | null }): boolean => d.ui_hints?.hidden === true;

/** 칩 카드(compact)로 그릴 타입인가: `ui_hints.shape`가 있으면 그것(`chip`이면 칩), 없으면 `executable === false`. */
export function isChipShape(d: NodeTypeDescriptor | undefined): boolean {
  if (d === undefined) return false;
  const shape = d.ui_hints?.shape;
  if (shape === "chip") return true;
  if (shape === "card") return false;
  return d.executable === false;
}

const roleOf = (d: NodeTypeDescriptor | undefined): string | undefined => d?.role ?? undefined;

/** `connects` 목록 검사: 빈 목록/없음 = 제한 없음, 역할을 모르면 제한이 있는 한 불통과. */
function rolePasses(allowed: readonly string[] | undefined, role: string | undefined): boolean {
  if (allowed === undefined || allowed.length === 0) return true;
  return role !== undefined && allowed.includes(role);
}

function descriptorOfType(typeId: string, nodeTypes: readonly NodeTypeDescriptor[]): NodeTypeDescriptor | undefined {
  return pickDescriptor({ id: "", type: typeId }, nodeTypes);
}

// ---------------------------------------------------------------- 연결 종류 후보

/**
 * 두 노드 타입을 이을 수 있는 엣지 종류(최신 버전만). `connects.source/target`과 노드 타입 `role`만 비교한다.
 * 타입을 모르면(역할 없음) `connects` 제한이 없는 종류만 통과한다.
 */
export function candidateEdgeKinds(
  sourceTypeId: string,
  targetTypeId: string,
  edgeTypes: readonly EdgeTypeDescriptor[],
  nodeTypes: readonly NodeTypeDescriptor[],
): EdgeTypeDescriptor[] {
  const sRole = roleOf(descriptorOfType(sourceTypeId, nodeTypes));
  const tRole = roleOf(descriptorOfType(targetTypeId, nodeTypes));
  // `ui_hints.hidden` 종류(이전 이름 등)는 새 연결 후보에서 뺀다. 이미 그 종류인 연결은 호출자가 따로 보여 준다.
  return latestVersions(edgeTypes).filter(
    (k) => k.ui_hints?.hidden !== true && rolePasses(k.connects?.source, sRole) && rolePasses(k.connects?.target, tRole),
  );
}

/** 연결 종류 한 줄 배지의 의미 키. 종류 id가 아니라 디스크립터 속성에서 계산한다. */
export type EdgeKindBadge = "entry" | "exit" | "delegate" | "ask" | "flow" | "none";

export function edgeKindBadge(k: EdgeTypeDescriptor): EdgeKindBadge {
  const s = schedulingOf(k);
  if (s === "entry") return "entry";
  if (s === "exit") return "exit";
  if (s === "flow") return "flow";
  if (k.invocation !== null && k.invocation !== undefined) return "delegate";
  if (k.interaction !== null && k.interaction !== undefined) return "ask";
  return "none";
}

/** 연결 거부에 쓰는 두 끝 역할(안내 문구용). */
export function endpointRoles(
  sourceTypeId: string | undefined,
  targetTypeId: string | undefined,
  nodeTypes: readonly NodeTypeDescriptor[],
): { sourceRole?: string; targetRole?: string } {
  const s = sourceTypeId === undefined ? undefined : roleOf(descriptorOfType(sourceTypeId, nodeTypes));
  const t = targetTypeId === undefined ? undefined : roleOf(descriptorOfType(targetTypeId, nodeTypes));
  return { ...(s !== undefined ? { sourceRole: s } : {}), ...(t !== undefined ? { targetRole: t } : {}) };
}

// ---------------------------------------------------------------- 상황 배지

export type NodeBadgeId = "entry" | "exit" | "interaction";

/**
 * 노드 상황 배지(순수 함수): 입구(`scheduling=entry` 연결의 도착), 답변(`exit` 연결의 출발),
 * 묻기(`interaction`이 있는 연결의 출발). 연결 종류 이름은 쓰지 않는다.
 */
export function deriveNodeBadges(nodeId: string, graph: Graph, edgeTypes: readonly EdgeTypeDescriptor[]): NodeBadgeId[] {
  const byId = new Map(edgeTypes.map((t) => [t.id, t]));
  const out = new Set<NodeBadgeId>();
  for (const e of edgesOf(graph)) {
    const k = byId.get(e.kind);
    if (k === undefined) continue;
    if (e.target.node === nodeId && schedulingOf(k) === "entry") out.add("entry");
    if (e.source.node === nodeId && schedulingOf(k) === "exit") out.add("exit");
    if (e.source.node === nodeId && k.interaction !== null && k.interaction !== undefined) out.add("interaction");
  }
  return (["entry", "exit", "interaction"] as const).filter((b) => out.has(b));
}

// ---------------------------------------------------------------- 입구/답변/묻기 단축 조작

/** 스케줄링·interaction 속성 어휘(연결 종류 id가 아님). */
export type RoleToggle = "entry" | "exit" | "interaction";

export interface ToggleKindInfo {
  id: string;
  title: string;
  /** 이 종류로 이을 수 있는 상대(사용자) 노드 id들 */
  counterpartIds: string[];
}

export interface ToggleInfo {
  available: boolean;
  on: boolean;
  /** 이 노드에 이미 있는 해당 연결 수 */
  count: number;
  kinds: ToggleKindInfo[];
  /** 상대 노드 후보(모든 종류의 합집합) */
  userNodes: { id: string; label: string }[];
  /** 쓸 수 없을 때 이유 코드: no-kind(알맞은 연결 종류 없음) | no-counterpart(이을 상대 노드 없음) */
  reasonIfUnavailable?: "no-kind" | "no-counterpart";
}

const matchesToggle = (toggle: RoleToggle, k: EdgeTypeDescriptor): boolean =>
  toggle === "interaction" ? k.interaction !== null && k.interaction !== undefined : schedulingOf(k) === toggle;

/** `entry`는 이 노드가 연결의 도착, 나머지는 출발이다. */
const nodeIsTarget = (toggle: RoleToggle): boolean => toggle === "entry";

export interface ToggleContext {
  nodeTypes: readonly NodeTypeDescriptor[];
  edgeTypes: readonly EdgeTypeDescriptor[];
  /** 동적 포트 타입의 계산된 포트(없으면 정적 포트만 사용) */
  portsOf?: (nodeId: string) => PortSpec | undefined;
  idFactory?: IdFactory;
}

function nodeLabel(n: NodeSpec): string {
  return n.label !== null && n.label !== undefined && n.label !== "" ? n.label : n.id;
}

/** 노드 하나의 입구/답변/묻기 토글 상태. */
export function getRoleToggleInfo(nodeId: string, toggle: RoleToggle, graph: Graph, ctx: ToggleContext): ToggleInfo {
  const node = nodesOf(graph).find((n) => n.id === nodeId);
  const empty: ToggleInfo = { available: false, on: false, count: 0, kinds: [], userNodes: [] };
  if (node === undefined) return { ...empty, reasonIfUnavailable: "no-kind" };
  const ownRole = roleOf(pickDescriptor(node, ctx.nodeTypes));
  const asTarget = nodeIsTarget(toggle);
  const kinds = latestVersions(ctx.edgeTypes).filter((k) => matchesToggle(toggle, k));
  const eligible: ToggleKindInfo[] = [];
  for (const k of kinds) {
    const ownAllowed = asTarget ? k.connects?.target : k.connects?.source;
    if (!rolePasses(ownAllowed, ownRole)) continue;
    const otherAllowed = asTarget ? k.connects?.source : k.connects?.target;
    // 상대 노드는 연결 종류가 말하는 역할로만 찾는다(제한이 없으면 후보를 추측하지 않는다)
    const counterpartIds =
      otherAllowed === undefined || otherAllowed.length === 0
        ? []
        : nodesOf(graph)
            .filter((n) => n.id !== nodeId && rolePasses(otherAllowed, roleOf(pickDescriptor(n, ctx.nodeTypes))))
            .map((n) => n.id);
    eligible.push({ id: k.id, title: k.title, counterpartIds });
  }
  const kindIds = new Set(kinds.map((k) => k.id));
  const count = edgesOf(graph).filter(
    (e) => kindIds.has(e.kind) && (asTarget ? e.target.node === nodeId : e.source.node === nodeId),
  ).length;
  const ids = new Set(eligible.flatMap((k) => k.counterpartIds));
  const userNodes = nodesOf(graph)
    .filter((n) => ids.has(n.id))
    .map((n) => ({ id: n.id, label: nodeLabel(n) }));
  const base = { on: count > 0, count, kinds: eligible, userNodes };
  if (eligible.length === 0) return { ...base, available: count > 0, ...(count > 0 ? {} : { reasonIfUnavailable: "no-kind" as const }) };
  if (userNodes.length === 0) return { ...base, available: count > 0, ...(count > 0 ? {} : { reasonIfUnavailable: "no-counterpart" as const }) };
  return { ...base, available: true };
}

export interface ToggleChoice {
  kindId: string;
  kindTitle: string;
  userNodeId: string;
  userLabel: string;
}

/** 켤 때 고를 수 있는 (연결 종류, 상대 노드) 조합 전부. */
export function toggleChoices(info: ToggleInfo): ToggleChoice[] {
  const label = new Map(info.userNodes.map((u) => [u.id, u.label]));
  return info.kinds.flatMap((k) =>
    k.counterpartIds.map((id) => ({ kindId: k.id, kindTitle: k.title, userNodeId: id, userLabel: label.get(id) ?? id })),
  );
}

export interface ToggleOptions {
  kindId?: string;
  userNodeId?: string;
}

export interface ToggleResult {
  graph: Graph;
  changed: boolean;
  /** 새로 만든 엣지 id(켤 때) */
  addedEdgeIds: string[];
  removedEdgeIds: string[];
  /** 바뀌지 않은 이유(에러 아님) */
  reason?: "unavailable" | "exists" | "no-port" | "ambiguous";
}

function firstPort(spec: PortSpec | undefined, side: "inputs" | "outputs"): string | undefined {
  return spec?.[side]?.[0]?.name;
}

/**
 * 입구/답변/묻기 토글을 적용한다. 켜면 엣지 하나를 만들고(종류·상대는 options 또는 첫 후보, 포트는 `default_ports`
 * → 없으면 노드 타입 포트 순서의 첫 포트), 끄면 해당 속성 연결을 지운다(options로 좁힐 수 있음). 입력 그래프는 바꾸지 않는다.
 */
export function applyRoleToggle(graph: Graph, nodeId: string, toggle: RoleToggle, on: boolean, ctx: ToggleContext, options: ToggleOptions = {}): ToggleResult {
  const unchanged = (reason: ToggleResult["reason"]): ToggleResult => ({
    graph,
    changed: false,
    addedEdgeIds: [],
    removedEdgeIds: [],
    ...(reason !== undefined ? { reason } : {}),
  });
  const asTarget = nodeIsTarget(toggle);
  const kindIds = new Set(latestVersions(ctx.edgeTypes).filter((k) => matchesToggle(toggle, k)).map((k) => k.id));
  // 구버전 id 도 같은 id이므로 위 집합으로 충분
  if (!on) {
    const removed = edgesOf(graph).filter(
      (e) =>
        kindIds.has(e.kind) &&
        (asTarget ? e.target.node === nodeId : e.source.node === nodeId) &&
        (options.kindId === undefined || e.kind === options.kindId) &&
        (options.userNodeId === undefined || (asTarget ? e.source.node : e.target.node) === options.userNodeId),
    );
    if (removed.length === 0) return unchanged(undefined);
    const ids = new Set(removed.map((e) => e.id));
    return {
      graph: { ...graph, edges: edgesOf(graph).filter((e) => !ids.has(e.id)) },
      changed: true,
      addedEdgeIds: [],
      removedEdgeIds: [...ids],
    };
  }
  const info = getRoleToggleInfo(nodeId, toggle, graph, ctx);
  // 후보가 여럿인데 사용자가 고르지 않았으면 첫 후보를 대신 고르지 않는다(자유도 원칙)
  const pairs = toggleChoices(info).filter(
    (p) => (options.kindId === undefined || p.kindId === options.kindId) && (options.userNodeId === undefined || p.userNodeId === options.userNodeId),
  );
  if (pairs.length === 0) return unchanged("unavailable");
  if (pairs.length > 1) return unchanged("ambiguous");
  const kindInfo = info.kinds.find((k) => k.id === pairs[0]!.kindId);
  const otherId = pairs[0]!.userNodeId;
  if (kindInfo === undefined) return unchanged("unavailable");
  const kind = latestVersions(ctx.edgeTypes).find((k) => k.id === kindInfo.id);
  if (kind === undefined) return unchanged("unavailable");
  const srcId = asTarget ? otherId : nodeId;
  const tgtId = asTarget ? nodeId : otherId;
  if (edgesOf(graph).some((e) => e.kind === kind.id && e.source.node === srcId && e.target.node === tgtId)) return unchanged("exists");
  const portsFor = (id: string): PortSpec | undefined => {
    const n = nodesOf(graph).find((x) => x.id === id);
    const d = n === undefined ? undefined : pickDescriptor(n, ctx.nodeTypes);
    return d?.dynamic_ports === true ? ctx.portsOf?.(id) : (d?.static_ports ?? ctx.portsOf?.(id) ?? undefined);
  };
  const srcPort = kind.default_ports?.source ?? firstPort(portsFor(srcId), "outputs");
  const tgtPort = kind.default_ports?.target ?? firstPort(portsFor(tgtId), "inputs");
  if (srcPort === undefined || srcPort === null || tgtPort === undefined || tgtPort === null) return unchanged("no-port");
  const edges = edgesOf(graph);
  const id = (ctx.idFactory ?? defaultIdFactory)("e", new Set(edges.map((e) => e.id)));
  const edge: EdgeSpec = { id, source: { node: srcId, port: srcPort }, target: { node: tgtId, port: tgtPort }, kind: kind.id };
  return { graph: { ...graph, edges: [...edges, edge] }, changed: true, addedEdgeIds: [id], removedEdgeIds: [] };
}

// ---------------------------------------------------------------- 이슈 제안

/**
 * 서버가 준 수정 제안(patch)을 그래프에 적용한다(순수 함수). 이슈 코드를 해석하지 않는다.
 * 이미 있는 id의 노드·엣지는 건너뛰고, 끝점 노드가 그래프에 없는 엣지도 건너뛴다(어긋난 제안 방어).
 */
export function applyGraphPatch(graph: Graph, patch: GraphPatch | undefined | null): { graph: Graph; addedNodeIds: string[]; addedEdgeIds: string[]; removedEdgeIds: string[] } {
  const nodes = nodesOf(graph);
  const nodeIds = new Set(nodes.map((n) => n.id));
  const removeIds = new Set(patch?.remove_edge_ids ?? []);
  const kept = edgesOf(graph).filter((e) => !removeIds.has(e.id));
  const removedEdgeIds = edgesOf(graph).filter((e) => removeIds.has(e.id)).map((e) => e.id);
  const newNodes = (patch?.add_nodes ?? []).filter((n) => !nodeIds.has(n.id)).map((n) => structuredClone(n));
  for (const n of newNodes) nodeIds.add(n.id);
  const edgeIds = new Set(kept.map((e) => e.id));
  const newEdges = (patch?.add_edges ?? [])
    .filter((e) => !edgeIds.has(e.id) && nodeIds.has(e.source.node) && nodeIds.has(e.target.node))
    .map((e) => structuredClone(e));
  return {
    graph: { ...graph, nodes: [...nodes, ...newNodes], edges: [...kept, ...newEdges] },
    addedNodeIds: newNodes.map((n) => n.id),
    addedEdgeIds: newEdges.map((e) => e.id),
    removedEdgeIds,
  };
}

// ---------------------------------------------------------------- 리소스 보기

/** 리소스처럼 실행되지 않는 노드(`executable === false`)의 id 집합. 모르는 타입은 포함하지 않는다. */
export function nonExecutableNodeIds(graph: Graph, nodeTypes: readonly NodeTypeDescriptor[]): Set<string> {
  const out = new Set<string>();
  for (const n of nodesOf(graph)) {
    if (pickDescriptor(n, nodeTypes)?.executable === false) out.add(n.id);
  }
  return out;
}

export interface ResourceChip {
  /** 노드 타입 id(같은 타입끼리 묶는 키) */
  key: string;
  iconText: string;
  title: string;
  count: number;
  /** 툴팁용 이름들 */
  names: string[];
}

/**
 * 리소스 보기를 껐을 때 카드 아래에 보일 칩. 숨겨진(`executable=false`) 노드에서 나가는 연결의 도착 노드별로
 * 타입 단위로 묶는다. `iconOf`는 호출자가 타입별 아이콘 텍스트를 정해 주는 함수다.
 */
export function deriveResourceChips(
  graph: Graph,
  nodeTypes: readonly NodeTypeDescriptor[],
  iconOf: (d: NodeTypeDescriptor | undefined, fallbackTitle: string) => string,
): Map<string, ResourceChip[]> {
  const hidden = nonExecutableNodeIds(graph, nodeTypes);
  const byId = new Map(nodesOf(graph).map((n) => [n.id, n]));
  const result = new Map<string, Map<string, ResourceChip>>();
  for (const e of edgesOf(graph)) {
    if (!hidden.has(e.source.node) || hidden.has(e.target.node)) continue;
    const res = byId.get(e.source.node);
    if (res === undefined || !byId.has(e.target.node)) continue;
    const d = pickDescriptor(res, nodeTypes);
    const per = result.get(e.target.node) ?? new Map<string, ResourceChip>();
    const chip = per.get(res.type) ?? { key: res.type, iconText: iconOf(d, res.type), title: d?.title ?? res.type, count: 0, names: [] };
    if (!chip.names.includes(nodeLabel(res))) {
      chip.count += 1;
      chip.names.push(nodeLabel(res));
    }
    per.set(res.type, chip);
    result.set(e.target.node, per);
  }
  return new Map([...result].map(([id, per]) => [id, [...per.values()]]));
}

/**
 * 이 노드가 리소스를 받을 수 있는가(`connects` + `executable` 기반): 실행되는 노드이고,
 * 어떤 연결 종류가 "실행되지 않는 노드 타입의 역할 → 이 노드의 역할"을 허용한다.
 */
export function canHaveResources(
  node: NodeSpec,
  nodeTypes: readonly NodeTypeDescriptor[],
  edgeTypes: readonly EdgeTypeDescriptor[],
): boolean {
  const d = pickDescriptor(node, nodeTypes);
  if (d === undefined || d.executable === false) return false;
  const role = roleOf(d);
  const resourceRoles = new Set(
    latestVersions(nodeTypes)
      .filter((t) => t.executable === false)
      .map(roleOf)
      .filter((r): r is string => r !== undefined),
  );
  return latestVersions(edgeTypes).some((k) => {
    const src = k.connects?.source ?? [];
    if (src.length === 0 || !src.some((r) => resourceRoles.has(r))) return false;
    return rolePasses(k.connects?.target, role) && (k.connects?.target?.length ?? 0) > 0;
  });
}

// ---------------------------------------------------------------- 대기 경과 표시

/** 밀리초 → 경과 문구(템플릿은 messages). 음수는 0초. */
export function formatElapsed(ms: number, m: Pick<GraphEditorMessages, "elapsedSeconds" | "elapsedMinutes" | "elapsedHours">): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const min = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  if (h > 0) return format(m.elapsedHours, { h, m: min });
  if (min > 0) return format(m.elapsedMinutes, { m: min, s: sec });
  return format(m.elapsedSeconds, { s: sec });
}
