/**
 * 팀 구성 화면의 순수 로직. 노드 타입 id·연결 종류 id를 비교하지 않고 디스크립터 속성
 * (`role`, `binds`, `executable`, `scheduling`, `invocation`, `interaction`, `connects`)만 읽는다.
 */
import { applyRoleToggle, declaredLabels, deriveNodeBadges, getRoleToggleInfo, newGraphUi, schedulingOf, type NodeBadgeId, type RoleToggle } from "@agent-console/graph-editor";
import { getContractSchema, type EdgeSpec, type EdgeTypeDescriptor, type Graph, type GraphSettings, type Issue, type NodeSpec, type NodeTypeDescriptor, type ResourceAttachment } from "@agent-console/contracts";
import type { SchemaNode } from "../../lib/schemaTools";

export const nodesOf = (g: Graph): NodeSpec[] => g.nodes ?? [];
export const edgesOf = (g: Graph): EdgeSpec[] => g.edges ?? [];
export const nodeLabel = (n: NodeSpec): string => (n.label != null && n.label !== "" ? n.label : n.id);

/** 같은 id의 여러 버전 중 최신만(입력 순서 유지). */
export function latestById<T extends { id: string; version?: number }>(items: readonly T[]): T[] {
  const best = new Map<string, T>();
  for (const it of items) {
    const cur = best.get(it.id);
    if (cur === undefined || (it.version ?? 0) >= (cur.version ?? 0)) best.set(it.id, it);
  }
  return [...best.values()];
}

/** 그래프 노드에 맞는 타입 디스크립터(type_version이 같은 것, 없으면 최신). 모르는 타입이면 undefined. */
export function descriptorOf(node: NodeSpec, nodeTypes: readonly NodeTypeDescriptor[]): NodeTypeDescriptor | undefined {
  const same = nodeTypes.filter((d) => d.id === node.type);
  if (same.length === 0) return undefined;
  if (node.type_version != null) {
    const exact = same.find((d) => (d.version ?? 1) === node.type_version);
    if (exact !== undefined) return exact;
  }
  return same.reduce((a, b) => ((b.version ?? 0) >= (a.version ?? 0) ? b : a));
}

export const edgeKindOf = (edge: EdgeSpec, edgeTypes: readonly EdgeTypeDescriptor[]): EdgeTypeDescriptor | undefined => latestById(edgeTypes).find((k) => k.id === edge.kind);

const roleOf = (d: NodeTypeDescriptor | undefined): string | undefined => d?.role ?? undefined;

// ---------------------------------------------------------------- 새 팀 구성

/**
 * "사용자 노드" 후보 타입: `scheduling=entry` 연결 종류의 출발(`connects.source`) 역할을 가진, 숨김이 아닌 노드 타입.
 * 역할 이름·타입 id는 비교하지 않는다(속성으로만 찾는다).
 */
export function entrySourceNodeTypes(nodeTypes: readonly NodeTypeDescriptor[], edgeTypes: readonly EdgeTypeDescriptor[]): NodeTypeDescriptor[] {
  const roles = new Set(
    latestById(edgeTypes)
      .filter((k) => schedulingOf(k) === "entry")
      .flatMap((k) => k.connects?.source ?? []),
  );
  return latestById(nodeTypes).filter((t) => t.role != null && roles.has(t.role) && t.ui_hints?.hidden !== true);
}

export interface StarterInput {
  id: string;
  name: string;
  description?: string;
  /** 시작 노드 타입(없으면 빈 팀 구성) */
  startNode?: NodeTypeDescriptor;
}

/** 새 팀 구성 문서. 시작 노드가 있으면 노드 하나만 들어간다(연결은 사용자가 그린다). */
export function starterGraph({ id, name, description, startNode }: StarterInput): Graph {
  const graph: Graph = { kind: undefined, id, name, nodes: [], edges: [] } as unknown as Graph;
  delete (graph as { kind?: unknown }).kind;
  // 새 그래프는 노드 방향 자동(5.2R.23). 기존 그래프의 명시 값은 건드리지 않는다.
  graph.ui = newGraphUi();
  if (description) graph.description = description;
  if (startNode !== undefined) {
    graph.nodes = [{ id: startNode.id, type: startNode.id, label: startNode.title, position: { x: 0, y: 0 } }];
  }
  return graph;
}

// ---------------------------------------------------------------- 팔레트

/** `binds.kind` -> 구역 표시 이름(그 종류에 묶인 노드 타입의 제목). */
export function definitionKindTitles(nodeTypes: readonly NodeTypeDescriptor[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const t of latestById(nodeTypes)) {
    if (t.binds != null && out[t.binds.kind] === undefined) out[t.binds.kind] = t.title;
  }
  return out;
}

/** 이 팀 구성에서 정의가 몇 번 쓰였나. 키 = `${binds.kind}:${정의 id}`. */
export function usageCounts(graph: Graph, nodeTypes: readonly NodeTypeDescriptor[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const n of nodesOf(graph)) {
    const d = descriptorOf(n, nodeTypes);
    if (d?.binds == null) continue;
    const ref = n.config?.[d.binds.field];
    if (typeof ref !== "string") continue;
    const key = `${d.binds.kind}:${ref}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

// ---------------------------------------------------------------- 팀 층 설정

function schemaKeys(model: string): string[] {
  const props = (getContractSchema(model) as SchemaNode)["properties"];
  return typeof props === "object" && props !== null ? Object.keys(props) : [];
}

/** 팀 구성 설정의 키 분리: 에이전트 설정(`AgentSettings`) / 대화·편집 규칙(그 밖의 키). 스키마에서 읽는다. */
export function teamSettingKeys(): { agent: string[]; user: string[] } {
  const agent = schemaKeys("AgentSettings");
  return { agent, user: schemaKeys("GraphSettings").filter((k) => !agent.includes(k)) };
}

/** 객체에서 키 일부만(없는 키는 건너뜀). */
export function pickKeys(source: Record<string, unknown> | null | undefined, keys: readonly string[]): Record<string, unknown> {
  return Object.fromEntries(Object.entries(source ?? {}).filter(([k]) => keys.includes(k)));
}

/** `settings`의 `keys` 부분을 `next`로 바꾼다(다른 키는 유지). 결과가 비면 undefined(키 삭제). */
export function replaceKeys(settings: GraphSettings | null | undefined, keys: readonly string[], next: Record<string, unknown>): GraphSettings | undefined {
  const kept = Object.fromEntries(Object.entries(settings ?? {}).filter(([k]) => !keys.includes(k)));
  const merged = { ...kept, ...next };
  return Object.keys(merged).length === 0 ? undefined : (merged as GraphSettings);
}

/** 그래프의 settings를 바꾼 새 그래프(undefined면 키 삭제). */
export function withSettings(graph: Graph, settings: GraphSettings | undefined): Graph {
  const next = { ...graph };
  if (settings === undefined) delete next.settings;
  else next.settings = settings;
  return next;
}

/** 팀 공용 첨부(`settings.resources`). */
export const sharedAttachments = (graph: Graph): ResourceAttachment[] => (graph.settings?.resources ?? []) as ResourceAttachment[];

export function withSharedAttachments(graph: Graph, next: readonly ResourceAttachment[]): Graph {
  const kept = { ...(graph.settings ?? {}) } as Record<string, unknown>;
  if (next.length === 0) delete kept["resources"];
  else kept["resources"] = [...next];
  return withSettings(graph, Object.keys(kept).length === 0 ? undefined : (kept as GraphSettings));
}

// ---------------------------------------------------------------- 노드 config 편집

/** 노드 config에서 문자열 값 하나. 비어 있으면(null·"") undefined. */
export function configText(node: NodeSpec, key: string): string | undefined {
  const v = node.config?.[key];
  return typeof v === "string" && v !== "" ? v : undefined;
}

/** 노드 config 키 하나를 바꾼다. 비우면(빈 문자열·null) 키를 지운다 -> 정의 값을 쓴다. */
export function withConfigText(node: NodeSpec, key: string, value: string): NodeSpec {
  const config = { ...(node.config ?? {}) };
  if (value === "") delete config[key];
  else config[key] = value;
  const next: NodeSpec = { ...node, config };
  if (Object.keys(config).length === 0) delete (next as { config?: unknown }).config;
  return next;
}

export function withNodeConfig(graph: Graph, nodeId: string, config: Record<string, unknown>): Graph {
  return {
    ...graph,
    nodes: nodesOf(graph).map((n) => {
      if (n.id !== nodeId) return n;
      const next: NodeSpec = { ...n, config };
      if (Object.keys(config).length === 0) delete (next as { config?: unknown }).config;
      return next;
    }),
  };
}

export function withNode(graph: Graph, nodeId: string, patch: Partial<NodeSpec>): Graph {
  return { ...graph, nodes: nodesOf(graph).map((n) => (n.id === nodeId ? { ...n, ...patch } : n)) };
}

export function withEdge(graph: Graph, edgeId: string, patch: Partial<EdgeSpec>): Graph {
  return { ...graph, edges: edgesOf(graph).map((e) => (e.id === edgeId ? { ...e, ...patch } : e)) };
}

// ---------------------------------------------------------------- 위임 연결

/** 이 노드로 들어오는 위임 연결(`invocation`이 있는 종류)과 그 종류. */
export function incomingInvocations(nodeId: string, graph: Graph, edgeTypes: readonly EdgeTypeDescriptor[]): { edge: EdgeSpec; kind: EdgeTypeDescriptor }[] {
  const out: { edge: EdgeSpec; kind: EdgeTypeDescriptor }[] = [];
  for (const edge of edgesOf(graph)) {
    if (edge.target.node !== nodeId) continue;
    const kind = edgeKindOf(edge, edgeTypes);
    if (kind?.invocation != null) out.push({ edge, kind });
  }
  return out;
}

/** 위임 방식 id: 연결 설정의 `strategy`(있으면) 아니면 종류가 정한 기본. */
export function strategyOfInvocation(edge: EdgeSpec, kind: EdgeTypeDescriptor): string | undefined {
  const own = edge.config?.["strategy"];
  if (typeof own === "string" && own !== "") return own;
  const base = kind.invocation?.["strategy"];
  return typeof base === "string" ? base : undefined;
}

// ---------------------------------------------------------------- 개요

export interface TeamOverview {
  entries: NodeSpec[];
  /** 답변을 내는 노드(마지막 답변 여부는 계획 요약에서 읽는다) */
  exits: NodeSpec[];
  asks: NodeSpec[];
  /** 선언형 배지 문구 -> 그 배지가 붙은 노드(예: 검토 지점). 문구는 디스크립터가 준다 */
  declared: Map<string, NodeSpec[]>;
}

/** 입구·답변·되묻기·선언형 배지(검토 등)를 그래프에서 계산한다(디스크립터 속성 기반). */
export function overviewOf(graph: Graph, nodeTypes: readonly NodeTypeDescriptor[], edgeTypes: readonly EdgeTypeDescriptor[]): TeamOverview {
  const entries: NodeSpec[] = [];
  const exits: NodeSpec[] = [];
  const asks: NodeSpec[] = [];
  const declared = new Map<string, NodeSpec[]>();
  for (const node of nodesOf(graph)) {
    const badges: NodeBadgeId[] = deriveNodeBadges(node.id, graph, edgeTypes);
    if (badges.includes("entry")) entries.push(node);
    if (badges.includes("exit")) exits.push(node);
    if (badges.includes("interaction")) asks.push(node);
    const d = descriptorOf(node, nodeTypes);
    const incoming = edgesOf(graph).filter((e) => e.target.node === node.id).map((e) => schedulingOf(edgeKindOf(e, edgeTypes) ?? ({} as EdgeTypeDescriptor)));
    const outgoing = edgesOf(graph).filter((e) => e.source.node === node.id).map((e) => schedulingOf(edgeKindOf(e, edgeTypes) ?? ({} as EdgeTypeDescriptor)));
    for (const label of declaredLabels(d?.ui_hints, "badges", { config: node.config, incomingScheduling: incoming, outgoingScheduling: outgoing }, { hintLabels: {} })) {
      declared.set(label, [...(declared.get(label) ?? []), node]);
    }
  }
  return { entries, exits, asks, declared };
}

// ---------------------------------------------------------------- 이슈

export interface IssueTarget {
  kind: "node" | "edge" | "graph";
  nodeId?: string;
  edgeId?: string;
  /** 표시 이름(노드 label 또는 "A → B") */
  label: string;
}

export function issueTarget(issue: Issue, graph: Graph): IssueTarget {
  if (issue.node_id != null) {
    const node = nodesOf(graph).find((n) => n.id === issue.node_id);
    return { kind: "node", nodeId: issue.node_id, label: node === undefined ? issue.node_id : nodeLabel(node) };
  }
  if (issue.edge_id != null) {
    const edge = edgesOf(graph).find((e) => e.id === issue.edge_id);
    if (edge !== undefined) {
      const byId = new Map(nodesOf(graph).map((n) => [n.id, n]));
      const a = byId.get(edge.source.node);
      const b = byId.get(edge.target.node);
      return { kind: "edge", edgeId: edge.id, nodeId: edge.source.node, label: `${a === undefined ? edge.source.node : nodeLabel(a)} → ${b === undefined ? edge.target.node : nodeLabel(b)}` };
    }
    return { kind: "edge", edgeId: issue.edge_id, label: issue.edge_id };
  }
  return { kind: "graph", label: "" };
}

/** 이 노드에 속한 이슈(노드 직접 + 노드를 끝점으로 하는 연결). */
export function issuesOfNode(issues: readonly Issue[], nodeId: string, graph: Graph): Issue[] {
  const edgeIds = new Set(edgesOf(graph).filter((e) => e.source.node === nodeId || e.target.node === nodeId).map((e) => e.id));
  return issues.filter((i) => i.node_id === nodeId || (i.edge_id != null && edgeIds.has(i.edge_id)));
}

export const issuesOfEdge = (issues: readonly Issue[], edgeId: string): Issue[] => issues.filter((i) => i.edge_id === edgeId);

/** 실행을 막는 이슈가 있는가(서버가 `blocks_run`으로 알린 것만). */
export const blockingIssues = (issues: readonly Issue[]): Issue[] => issues.filter((i) => i.blocks_run === true);

// ---------------------------------------------------------------- 리소스 연결(노드 패널 "이 노드" 층)

export interface ResourceLink {
  edge: EdgeSpec;
  resourceNode: NodeSpec;
  /** 리소스 정의 id(`binds.field` 값) */
  resourceId: string;
  mode: string;
}

/**
 * 이 노드로 들어오는 연결 중, 출발이 "실행되지 않는 노드"(`executable=false`)이고 `binds`가 있는 것 = 리소스 연결.
 * 첨부 방식은 연결 설정 `mode`(없으면 첫 선택지 = 더함).
 */
export function resourceLinks(nodeId: string, graph: Graph, nodeTypes: readonly NodeTypeDescriptor[], defaultMode: string): ResourceLink[] {
  const byId = new Map(nodesOf(graph).map((n) => [n.id, n]));
  const out: ResourceLink[] = [];
  for (const edge of edgesOf(graph)) {
    if (edge.target.node !== nodeId) continue;
    const res = byId.get(edge.source.node);
    const d = res === undefined ? undefined : descriptorOf(res, nodeTypes);
    if (res === undefined || d === undefined || d.executable !== false || d.binds == null) continue;
    const ref = res.config?.[d.binds.field];
    if (typeof ref !== "string") continue;
    const mode = edge.config?.["mode"];
    out.push({ edge, resourceNode: res, resourceId: ref, mode: typeof mode === "string" && mode !== "" ? mode : defaultMode });
  }
  return out;
}

/** 리소스 노드를 붙일 수 있는 연결 종류: 출발이 리소스 노드 타입 역할, 도착이 이 노드 타입 역할을 허용하는 종류. */
export function resourceEdgeKinds(target: NodeSpec, resourceType: NodeTypeDescriptor, nodeTypes: readonly NodeTypeDescriptor[], edgeTypes: readonly EdgeTypeDescriptor[]): EdgeTypeDescriptor[] {
  const targetRole = roleOf(descriptorOf(target, nodeTypes));
  const sourceRole = roleOf(resourceType);
  const passes = (allowed: readonly string[] | undefined, role: string | undefined) => allowed !== undefined && allowed.length > 0 && role !== undefined && allowed.includes(role);
  return latestById(edgeTypes).filter((k) => passes(k.connects?.source, sourceRole) && passes(k.connects?.target, targetRole));
}

/** 리소스 정의를 만드는 노드 타입(`binds`가 있고 `executable=false`). */
export function resourceNodeType(nodeTypes: readonly NodeTypeDescriptor[]): NodeTypeDescriptor | undefined {
  return latestById(nodeTypes).find((t) => t.binds != null && t.executable === false);
}

export interface AttachResult {
  graph: Graph;
  nodeId: string;
  edgeId: string;
  /** 새 리소스 노드를 만들었는가 */
  createdNode: boolean;
}

/**
 * 리소스를 이 노드에 붙인다: 같은 리소스 노드가 이미 있으면 그 노드에서, 없으면 새로 만들어 연결한다.
 * 연결 종류는 `kind`(여럿일 때 호출자가 골랐다). 포트는 종류의 `default_ports`, 없으면 노드 타입 포트 순서의 첫 포트.
 */
export function attachResource(
  graph: Graph,
  target: NodeSpec,
  resource: { id: string; name: string },
  type: NodeTypeDescriptor,
  kind: EdgeTypeDescriptor,
  nodeTypes: readonly NodeTypeDescriptor[],
  ids: { node: string; edge: string },
): AttachResult | undefined {
  if (type.binds == null) return undefined;
  const existing = nodesOf(graph).find((n) => n.type === type.id && n.config?.[type.binds!.field] === resource.id);
  const targetType = descriptorOf(target, nodeTypes);
  const srcPort = kind.default_ports?.source ?? type.static_ports?.outputs?.[0]?.name;
  const tgtPort = kind.default_ports?.target ?? targetType?.static_ports?.inputs?.find((p) => p.name !== undefined)?.name;
  if (srcPort == null || tgtPort == null) return undefined;
  const anchor = target.position ?? { x: 0, y: 0 };
  const nodes = nodesOf(graph);
  const resourceNode: NodeSpec =
    existing ??
    ({ id: ids.node, type: type.id, label: resource.name, config: { [type.binds.field]: resource.id }, position: { x: (anchor.x ?? 0) - 240, y: (anchor.y ?? 0) + 120 + nodes.filter((n) => descriptorOf(n, nodeTypes)?.executable === false).length * 56 } } as NodeSpec);
  const edge: EdgeSpec = { id: ids.edge, source: { node: resourceNode.id, port: srcPort }, target: { node: target.id, port: tgtPort }, kind: kind.id };
  return { graph: { ...graph, nodes: existing === undefined ? [...nodes, resourceNode] : nodes, edges: [...edgesOf(graph), edge] }, nodeId: resourceNode.id, edgeId: edge.id, createdNode: existing === undefined };
}

/** 연결 하나를 지우고, 그 리소스 노드에 남은 연결이 없으면 노드도 지운다. */
export function detachResource(graph: Graph, edgeId: string): Graph {
  const edge = edgesOf(graph).find((e) => e.id === edgeId);
  if (edge === undefined) return graph;
  const edges = edgesOf(graph).filter((e) => e.id !== edgeId);
  const stillUsed = edges.some((e) => e.source.node === edge.source.node || e.target.node === edge.source.node);
  return { ...graph, edges, nodes: stillUsed ? nodesOf(graph) : nodesOf(graph).filter((n) => n.id !== edge.source.node) };
}

/** 고유 id 만들기(`prefix-1`, `prefix-2` …). */
export function freshId(prefix: string, existing: Iterable<string>): string {
  const used = new Set(existing);
  for (let n = 1; n < 100_000; n += 1) if (!used.has(`${prefix}-${n}`)) return `${prefix}-${n}`;
  return `${prefix}-${used.size + 1}`;
}

/** 서버 `GraphSummary.entry_labels` 요약: 하나면 이름, 둘 넘으면 "첫째 외 N", 없으면 undefined. */
export function summarizeEntries(labels: readonly string[] | null | undefined, more: (first: string, rest: number) => string): string | undefined {
  if (labels == null || labels.length === 0) return undefined;
  return labels.length === 1 ? labels[0] : more(labels[0]!, labels.length - 1);
}

// ---------------------------------------------------------------- 상대 노드가 없을 때 만들어서 토글

/**
 * 입구/답변/묻기 토글을 켜려는데 이을 상대(사용자) 노드가 없을 때: 연결 종류가 말하는 상대 역할의 노드 타입으로
 * 새 노드를 이 노드 옆에 놓고 토글을 켠다. 종류·타입은 디스크립터 속성(`connects`, `role`)으로만 고른다.
 * 만들 수 없으면(상대 역할의 기본 노드 타입 없음) undefined.
 */
export function addCounterpartAndToggle(
  graph: Graph,
  nodeId: string,
  toggle: RoleToggle,
  kindId: string,
  ctx: { nodeTypes: readonly NodeTypeDescriptor[]; edgeTypes: readonly EdgeTypeDescriptor[] },
): { graph: Graph; nodeId: string } | undefined {
  const node = nodesOf(graph).find((n) => n.id === nodeId);
  const kind = latestById(ctx.edgeTypes).find((k) => k.id === kindId);
  if (node === undefined || kind === undefined) return undefined;
  const asTarget = toggle === "entry";
  const roles = (asTarget ? kind.connects?.source : kind.connects?.target) ?? [];
  const type = latestById(ctx.nodeTypes).find((t) => t.role != null && roles.includes(t.role) && t.binds == null && t.executable !== false && t.ui_hints?.hidden !== true);
  if (type === undefined) return undefined;
  const id = freshId(type.id, nodesOf(graph).map((n) => n.id));
  const base = node.position ?? { x: 0, y: 0 };
  const added: NodeSpec = { id, type: type.id, label: uniqueLabel(type.title, nodesOf(graph).map(nodeLabel)), position: { x: (base.x ?? 0) + (asTarget ? -300 : 300), y: base.y ?? 0 } };
  const withNode_ = { ...graph, nodes: [...nodesOf(graph), added] };
  const res = applyRoleToggle(withNode_, nodeId, toggle, true, ctx, { kindId, userNodeId: id });
  return res.changed ? { graph: res.graph, nodeId: id } : undefined;
}

function uniqueLabel(name: string, existing: readonly string[]): string {
  if (!existing.includes(name)) return name;
  for (let n = 2; n < 10_000; n += 1) if (!existing.includes(`${name} ${n}`)) return `${name} ${n}`;
  return name;
}

// ---------------------------------------------------------------- 토글 한 번(패널·단축키 공용)

export interface ToggleOutcome {
  graph: Graph;
  changed: boolean;
  /** 끄면서 지운 연결 수 */
  removed: number;
  /** 켜려는데 후보(종류·상대)가 여럿이라 고르지 않았다 */
  ambiguous: boolean;
}

/**
 * 입구/답변/묻기 토글 한 번. `on`을 생략하면 지금 상태의 반대로 한다.
 * 후보가 여럿이면 첫 후보를 대신 고르지 않고 `ambiguous`로 알린다.
 */
export function toggleRoleOnGraph(
  graph: Graph,
  nodeId: string,
  toggle: RoleToggle,
  ctx: { nodeTypes: readonly NodeTypeDescriptor[]; edgeTypes: readonly EdgeTypeDescriptor[] },
  on?: boolean,
  options?: { kindId?: string; userNodeId?: string },
): ToggleOutcome {
  const want = on ?? !getRoleToggleInfo(nodeId, toggle, graph, ctx).on;
  const res = applyRoleToggle(graph, nodeId, toggle, want, ctx, options ?? {});
  return { graph: res.graph, changed: res.changed, removed: res.removedEdgeIds.length, ambiguous: res.reason === "ambiguous" };
}
