/**
 * 노드 어디서나 연결(UX-P11, ux-overhaul §11.4 B+D)의 포트 추론(순수 함수).
 * 포트 이름·연결 종류 id·노드 타입 id를 비교하지 않는다. 근거는 디스크립터의 `default_ports`와 노드의 포트 목록뿐이다.
 * 추론 순서: 시작/끝 핸들이 정한 포트 -> 연결 종류의 `default_ports` -> 포트 목록의 첫 호환 포트
 * (호환 = 포트 존재·방향이 맞고 같은 종류의 같은 연결이 아직 없음). 후보가 둘 이상이면 호출자가 선택 UI(포트 열)로 묻는다.
 */
import type { EdgeTypeDescriptor, Graph } from "@agent-console/contracts";
import { checkConnection } from "./ops";
import type { Connection, PortLookup } from "./ops";

/** 연결의 한 끝. `port`가 있으면 사용자가 포트 핸들에서 시작/끝낸 것이다(방향도 거기서 정해진다). */
export interface ConnectEnd {
  node: string;
  port?: { side: "in" | "out"; port: string };
}

export interface ResolvedEnds {
  source: { node: string; port?: string };
  target: { node: string; port?: string };
}

/**
 * 방향 결정(D안): 시작 쪽이 출발이다. 단 시작/끝 핸들의 방향이 정해져 있으면 그것을 따른다
 * (입력 핸들에서 시작하면 시작 노드가 도착). 같은 방향 두 핸들이면 `undefined`.
 */
export function resolveEnds(start: ConnectEnd, end: ConnectEnd): ResolvedEnds | undefined {
  const a = start.port;
  const b = end.port;
  if (a !== undefined && b !== undefined && a.side === b.side) return undefined;
  const startIsSource = a !== undefined ? a.side === "out" : b !== undefined ? b.side === "in" : true;
  const [s, t] = startIsSource ? [start, end] : [end, start];
  return {
    source: { node: s.node, ...(s.port !== undefined ? { port: s.port.port } : {}) },
    target: { node: t.node, ...(t.port !== undefined ? { port: t.port.port } : {}) },
  };
}

export interface InferredKindConnection {
  kind: string;
  connection: Connection;
}

export interface InferPortsResult {
  items: InferredKindConnection[];
  /** 모든 후보가 같은 연결과 겹칠 때 그 연결 id(없으면 생략) */
  duplicateEdgeId?: string;
}

const unique = (xs: readonly (string | null | undefined)[]): string[] => [...new Set(xs.filter((x): x is string => typeof x === "string" && x !== ""))];

/**
 * 후보 종류마다 포트를 추론한다. 포트를 정할 수 없거나 같은 연결이 이미 있는 종류는 빠진다.
 * 포트 목록을 모르는 노드(`portsOf`가 `undefined`)는 시작/끝 핸들이 정한 포트나 `default_ports`만 쓴다.
 */
export function inferKindPorts(
  graph: Graph,
  ends: ResolvedEnds,
  candidates: readonly EdgeTypeDescriptor[],
  edgeTypes: readonly EdgeTypeDescriptor[],
  portsOf: PortLookup,
): InferPortsResult {
  const sp = portsOf(ends.source.node);
  const tp = portsOf(ends.target.node);
  const items: InferredKindConnection[] = [];
  let duplicateEdgeId: string | undefined;
  for (const k of candidates) {
    const outs = ends.source.port !== undefined ? [ends.source.port] : unique([k.default_ports?.source, ...(sp?.outputs ?? [])]);
    const ins = ends.target.port !== undefined ? [ends.target.port] : unique([k.default_ports?.target, ...(tp?.inputs ?? [])]);
    let found: Connection | undefined;
    search: for (const o of outs) {
      for (const i of ins) {
        const c: Connection = { source: { node: ends.source.node, port: o }, target: { node: ends.target.node, port: i } };
        const v = checkConnection(graph, c, portsOf, { edgeTypes, kind: k.id });
        if (v.ok || v.reason === "cycle") {
          found = c;
          break search;
        }
        if (v.reason === "duplicate") duplicateEdgeId ??= v.existingEdgeId;
      }
    }
    if (found !== undefined) items.push({ kind: k.id, connection: found });
  }
  return { items, ...(items.length === 0 && duplicateEdgeId !== undefined ? { duplicateEdgeId } : {}) };
}
