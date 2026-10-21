/**
 * 입구·답변 자동 연결(순수 함수). 노드 타입 id·연결 종류 id·포트 이름을 비교하지 않는다.
 * 판단 근거는 디스크립터 속성뿐이다: 연결 종류 `scheduling`·`connects`·`default_ports`, 노드 타입 `role`·`executable`·포트 선언.
 */
import type { EdgeTypeDescriptor, Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { pickDescriptor } from "./descriptors";
import { edgesOf, nodesOf, schedulingOf } from "./ops";
import type { IdFactory } from "./ops";
import { applyRoleToggle, latestVersions } from "./team";
import type { ToggleContext } from "./team";

const roleOf = (d: NodeTypeDescriptor | undefined): string | undefined => d?.role ?? undefined;
const passes = (allowed: readonly string[] | undefined, role: string | undefined): boolean =>
  allowed === undefined || allowed.length === 0 || (role !== undefined && allowed.includes(role));
const names = (allowed: readonly string[] | undefined, role: string | undefined): boolean =>
  role !== undefined && allowed !== undefined && allowed.includes(role);

/**
 * 연결 종류 후보의 관련도 순서. ① 두 끝 역할을 `connects`가 모두 명시한 종류
 * ② `preferredKind`(마지막 선택·기본 종류) ③ 입력 목록 순서. 입력을 바꾸지 않는다.
 */
export function rankEdgeKinds(
  candidates: readonly EdgeTypeDescriptor[],
  ends: { sourceRole?: string | undefined; targetRole?: string | undefined },
  preferredKind?: string,
): EdgeTypeDescriptor[] {
  const explicit = (k: EdgeTypeDescriptor): number => (names(k.connects?.source, ends.sourceRole) && names(k.connects?.target, ends.targetRole) ? 1 : 0);
  const pref = (k: EdgeTypeDescriptor): number => (preferredKind !== undefined && k.id === preferredKind ? 1 : 0);
  return candidates
    .map((k, i) => ({ k, i }))
    .sort((a, b) => explicit(b.k) - explicit(a.k) || pref(b.k) - pref(a.k) || a.i - b.i)
    .map((x) => x.k);
}

export interface PlanAutoConnectInput {
  /** 새 노드가 이미 들어간 그래프 */
  graph: Graph;
  /** 방금 놓인 노드 */
  nodeId: string;
  nodeTypes: readonly NodeTypeDescriptor[];
  edgeTypes: readonly EdgeTypeDescriptor[];
  /** 마지막 선택·기본 연결 종류(관련도 ② 단계) */
  preferredKind?: string | undefined;
  /** 동적 포트 계산 결과(없으면 정적 포트만) */
  portsOf?: ToggleContext["portsOf"];
  idFactory?: IdFactory;
}

export interface AutoConnectPlan {
  graph: Graph;
  /** 만든 연결 id(입구, 답변 순) */
  addedEdgeIds: string[];
}

/** 이 그래프에서 스케줄링 `entry`·`exit` 연결이 있는가. */
function hasIo(graph: Graph, edgeTypes: readonly EdgeTypeDescriptor[]): boolean {
  const byId = new Map(edgeTypes.map((k) => [k.id, k]));
  return edgesOf(graph).some((e) => {
    const s = schedulingOf(byId.get(e.kind));
    return s === "entry" || s === "exit";
  });
}

/**
 * 첫 실행 가능 노드가 놓였을 때 입구(사용자 → 노드)·답변(노드 → 사용자) 연결을 만든다. 조건을 모두 만족할 때만:
 *  1. 그래프에 `scheduling` entry/exit 연결이 하나도 없다.
 *  2. 입구·답변 종류의 `connects`가 허용하는 사용자 쪽 노드가 정확히 하나다.
 *  3. 새 노드가 실행 가능(`executable !== false`)하고 두 종류의 반대쪽 역할을 받을 수 있으며,
 *     입구 종류의 도착 역할을 받을 수 있는 노드가 새 노드 하나뿐이다(첫 노드).
 * 하나라도 어긋나거나 포트를 정할 수 없으면 `null`(그래프는 바뀌지 않는다). 설정 끔(`auto_connect_io: false`)은 호출자가 확인한다.
 */
export function planAutoConnect(i: PlanAutoConnectInput): AutoConnectPlan | null {
  const nodes = nodesOf(i.graph);
  const node = nodes.find((n) => n.id === i.nodeId);
  if (node === undefined) return null;
  const desc = pickDescriptor(node, i.nodeTypes);
  if (desc === undefined || desc.executable === false) return null;
  if (hasIo(i.graph, i.edgeTypes)) return null;
  const kinds = latestVersions(i.edgeTypes).filter((k) => k.ui_hints?.hidden !== true);
  const own = roleOf(desc);
  const withUsers = (scheduling: "entry" | "exit"): { kind: EdgeTypeDescriptor; users: string[] }[] => {
    const asTarget = scheduling === "entry";
    return kinds
      .filter((k) => schedulingOf(k) === scheduling && passes(asTarget ? k.connects?.target : k.connects?.source, own))
      .map((k) => {
        const other = asTarget ? k.connects?.source : k.connects?.target;
        // 상대 쪽 역할이 선언되지 않았으면 사용자 노드를 추측하지 않는다
        const users = other === undefined || other.length === 0 ? [] : nodes.filter((n) => n.id !== i.nodeId && passes(other, roleOf(pickDescriptor(n, i.nodeTypes)))).map((n) => n.id);
        return { kind: k, users };
      })
      .filter((x) => x.users.length > 0);
  };
  const entryAll = withUsers("entry");
  const exitAll = withUsers("exit");
  if (entryAll.length === 0 || exitAll.length === 0) return null;
  const userIds = new Set([...entryAll, ...exitAll].flatMap((x) => x.users));
  if (userIds.size !== 1) return null;
  const userId = [...userIds][0] as string;
  const userNode = nodes.find((n) => n.id === userId);
  const userRole = userNode === undefined ? undefined : roleOf(pickDescriptor(userNode, i.nodeTypes));
  const best = (all: { kind: EdgeTypeDescriptor }[], ends: Parameters<typeof rankEdgeKinds>[1]): EdgeTypeDescriptor =>
    rankEdgeKinds(all.map((x) => x.kind), ends, i.preferredKind)[0] as EdgeTypeDescriptor;
  const entry = { kind: best(entryAll, { sourceRole: userRole, targetRole: own }) };
  const exit = { kind: best(exitAll, { sourceRole: own, targetRole: userRole }) };
  // 첫 실행 노드인지: 입구 종류가 도착으로 받는 역할을 가진 노드가 새 노드 하나뿐이어야 한다
  const entryTargets = entry.kind.connects?.target;
  const others = nodes.filter((n) => n.id !== i.nodeId && n.id !== userId && passes(entryTargets, roleOf(pickDescriptor(n, i.nodeTypes))) && pickDescriptor(n, i.nodeTypes)?.executable !== false);
  if (others.length > 0) return null;
  const ctx: ToggleContext = { nodeTypes: i.nodeTypes, edgeTypes: i.edgeTypes, ...(i.portsOf !== undefined ? { portsOf: i.portsOf } : {}), ...(i.idFactory !== undefined ? { idFactory: i.idFactory } : {}) };
  const a = applyRoleToggle(i.graph, i.nodeId, "entry", true, ctx, { kindId: entry.kind.id, userNodeId: userId });
  if (!a.changed) return null;
  const b = applyRoleToggle(a.graph, i.nodeId, "exit", true, ctx, { kindId: exit.kind.id, userNodeId: userId });
  if (!b.changed) return null;
  return { graph: b.graph, addedEdgeIds: [...a.addedEdgeIds, ...b.addedEdgeIds] };
}

/** 연결 id로 연결만 제거한다(자동 연결 되돌리기). 입력 그래프는 바뀌지 않는다. */
export function withoutEdges(graph: Graph, edgeIds: readonly string[]): Graph {
  const drop = new Set(edgeIds);
  return { ...graph, edges: edgesOf(graph).filter((e) => !drop.has(e.id)) };
}
