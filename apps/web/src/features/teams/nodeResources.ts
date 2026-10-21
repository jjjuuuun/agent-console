import type { EdgeTypeDescriptor, Graph, NodeSpec, NodeTypeDescriptor, ResourceAttachment } from "@agent-console/contracts";
import { attachResource, edgesOf, freshId, nodesOf, resourceEdgeKinds, resourceNodeType, type ResourceLink } from "./teamsLogic";

/** 노드 층의 첨부 목록은 두 출처의 합이다: 그래프의 리소스 연결(앞) + 노드 설정의 `resources`(뒤). */
export function nodeLayerAttachments(links: readonly ResourceLink[], own: readonly ResourceAttachment[]): ResourceAttachment[] {
  return [...links.map((l) => ({ ref: l.resourceId, mode: l.mode as ResourceAttachment["mode"] })), ...own];
}

export type NodeLayerOp =
  | { kind: "add"; attachment: ResourceAttachment }
  | { kind: "remove-link"; edgeId: string }
  | { kind: "remove-own"; index: number }
  | { kind: "mode-link"; edgeId: string; mode: string }
  | { kind: "mode-own"; index: number; mode: string }
  | { kind: "reorder-links"; edgeIds: string[] }
  | { kind: "reorder-own"; order: number[] }
  | { kind: "none" };

const same = (a: ResourceAttachment, b: ResourceAttachment) => a.ref === b.ref && (a.mode ?? "add") === (b.mode ?? "add");

/**
 * 첨부 목록 편집(`AttachmentList`는 새 배열만 돌려준다)을 그래프·노드 설정에 대한 한 가지 동작으로 푼다.
 * 길이가 늘면 추가, 줄면 처음 달라지는 자리가 삭제, 같으면 방식 변경 또는 순서 변경이다.
 * 연결 묶음과 노드 설정 묶음 사이를 가로지르는 순서 변경은 지원하지 않는다(none).
 */
export function diffNodeLayer(old: readonly ResourceAttachment[], next: readonly ResourceAttachment[], links: readonly ResourceLink[]): NodeLayerOp {
  const nLinks = links.length;
  if (next.length > old.length) return { kind: "add", attachment: next[next.length - 1]! };
  if (next.length < old.length) {
    let i = 0;
    while (i < next.length && same(old[i]!, next[i]!)) i += 1;
    return i < nLinks ? { kind: "remove-link", edgeId: links[i]!.edge.id } : { kind: "remove-own", index: i - nLinks };
  }
  const changed = old.findIndex((a, i) => !same(a, next[i]!));
  if (changed < 0) return { kind: "none" };
  if (old[changed]!.ref === next[changed]!.ref && old.every((a, i) => i === changed || same(a, next[i]!))) {
    const mode = next[changed]!.mode ?? "add";
    return changed < nLinks ? { kind: "mode-link", edgeId: links[changed]!.edge.id, mode } : { kind: "mode-own", index: changed - nLinks, mode };
  }
  // 순서 변경: 각 묶음 안에서만 허용
  const oldRefs = old.map((a) => a.ref);
  const order = next.map((a) => oldRefs.indexOf(a.ref));
  const withinLinks = order.slice(0, nLinks).every((o) => o >= 0 && o < nLinks);
  const withinOwn = order.slice(nLinks).every((o) => o >= nLinks);
  if (!withinLinks || !withinOwn) return { kind: "none" };
  if (order.slice(0, nLinks).some((o, i) => o !== i)) return { kind: "reorder-links", edgeIds: order.slice(0, nLinks).map((o) => links[o]!.edge.id) };
  return { kind: "reorder-own", order: order.slice(nLinks).map((o) => o - nLinks) };
}

/** 리소스 연결의 방식 바꾸기(연결 설정 `mode`). 기본 방식이면 키를 지운다. */
export function withLinkMode(graph: Graph, edgeId: string, mode: string, defaultMode: string): Graph {
  return {
    ...graph,
    edges: edgesOf(graph).map((e) => {
      if (e.id !== edgeId) return e;
      const config = { ...(e.config ?? {}) };
      if (mode === defaultMode) delete config["mode"];
      else config["mode"] = mode;
      const next = { ...e, config };
      if (Object.keys(config).length === 0) delete (next as { config?: unknown }).config;
      return next;
    }),
  };
}

/** 리소스 연결 순서: 주어진 연결 id 순서대로 그래프 엣지 배열 안의 해당 자리를 다시 채운다. */
export function reorderLinkEdges(graph: Graph, edgeIds: readonly string[]): Graph {
  const edges = edgesOf(graph);
  const ids = new Set(edgeIds);
  const byId = new Map(edges.map((e) => [e.id, e]));
  const queue = edgeIds.map((id) => byId.get(id)!).filter(Boolean);
  return { ...graph, edges: edges.map((e) => (ids.has(e.id) ? queue.shift()! : e)) };
}

/** 노드 설정의 첨부(`settings.resources`)를 바꾼 새 노드. 비면 키를 지우고, settings가 비면 그것도 지운다. */
export function withNodeOwnAttachments(node: NodeSpec, next: readonly ResourceAttachment[]): NodeSpec {
  const config = { ...(node.config ?? {}) };
  const settings = { ...((config["settings"] as Record<string, unknown> | null | undefined) ?? {}) };
  if (next.length === 0) delete settings["resources"];
  else settings["resources"] = [...next];
  if (Object.keys(settings).length === 0) delete config["settings"];
  else config["settings"] = settings;
  const out: NodeSpec = { ...node, config };
  if (Object.keys(config).length === 0) delete (out as { config?: unknown }).config;
  return out;
}

export function ownAttachments(node: NodeSpec): ResourceAttachment[] {
  const settings = node.config?.["settings"] as { resources?: ResourceAttachment[] | null } | null | undefined;
  return settings?.resources ?? [];
}

/** 그래프 안 노드 하나를 바꾼 새 그래프. */
export function replaceNode(graph: Graph, node: NodeSpec): Graph {
  return { ...graph, nodes: nodesOf(graph).map((n) => (n.id === node.id ? node : n)) };
}

/**
 * 리소스를 노드에 붙인다(노드 패널 [리소스] 탭의 추가와 같은 결과): 리소스 노드를 만들거나 재사용해 연결한다.
 * 연결 종류가 여럿이면 목록의 첫 종류를 쓴다(고르는 화면은 노드 패널). 붙일 수 없으면(리소스 타입·연결 종류·포트 없음) undefined.
 */
export function attachResourceToNode(
  graph: Graph,
  nodeId: string,
  resource: { id: string; name: string },
  nodeTypes: readonly NodeTypeDescriptor[],
  edgeTypes: readonly EdgeTypeDescriptor[],
): Graph | undefined {
  const node = nodesOf(graph).find((n) => n.id === nodeId);
  const type = resourceNodeType(nodeTypes);
  if (node === undefined || type === undefined) return undefined;
  const kind = resourceEdgeKinds(node, type, nodeTypes, edgeTypes)[0];
  if (kind === undefined) return undefined;
  return attachResource(graph, node, resource, type, kind, nodeTypes, {
    node: freshId(type.id, nodesOf(graph).map((n) => n.id)),
    edge: freshId("e", edgesOf(graph).map((e) => e.id)),
  })?.graph;
}
