import type { Side } from "../shapes/types";
import type { EdgeSpec, NodeTypeDescriptor, PortDef, PortSpec } from "@agent-console/contracts";

/** 노드 카드가 그리는 포트 한 줄. */
export interface PortView {
  /** 포트 이름(PortDef.name). 엣지 끝점이 가리키는 값 */
  id: string;
  label: string;
  schemaSummary?: string;
  /** 권위 있는 포트 목록에 없는데 엣지가 참조 중(무효 엣지 표시용) */
  missing?: boolean;
  /** 이 포트에 엣지가 연결되어 있다(포트 라벨 자동 표시용). 편집기가 채운다 */
  connected?: boolean;
  /** 핸들이 붙는 노드 면(편집기가 결정해 채움). 없으면 입력=left·출력=right */
  side?: Side;
  /**
   * 기본 배치(포트 행 옆)가 아닐 때 핸들의 위치(px). 위·아래 면이면 가장자리를 따른 가로 위치, 좌·우 면이면 포트 영역 안 세로 위치.
   * 없으면 핸들은 포트 행 안에 그대로 있다. 편집기가 채운다.
   */
  offset?: number;
}

export interface NodePorts {
  inputs: PortView[];
  outputs: PortView[];
}

function summarizeSchema(schema: PortDef["schema"]): string | undefined {
  if (schema === null || schema === undefined) return undefined;
  const t = schema["type"];
  if (typeof t === "string") return t;
  if (Array.isArray(t)) return t.filter((x): x is string => typeof x === "string").join("|") || undefined;
  return undefined;
}

export function toPortViews(defs: readonly PortDef[] | null | undefined): PortView[] {
  return (defs ?? []).map((d) => {
    const view: PortView = { id: d.name, label: d.label ?? d.name };
    const summary = summarizeSchema(d.schema);
    if (summary !== undefined) view.schemaSummary = summary;
    return view;
  });
}

/** 정적 포트(동적 포트 타입이면 undefined — resolvePorts로 계산해야 한다). */
export function staticPorts(descriptor: NodeTypeDescriptor | undefined): PortSpec | undefined {
  if (descriptor === undefined || descriptor.dynamic_ports === true) return undefined;
  return descriptor.static_ports ?? { inputs: [], outputs: [] };
}

/**
 * 노드의 최종 포트 목록.
 * - `authoritative`(정적 포트 또는 계산된 포트)가 있으면 그것을 기준으로, 엣지가 참조하지만 목록에 없는 포트는 `missing`으로 덧붙인다.
 * - 없으면(알 수 없는 타입, 계산 전) 엣지가 참조하는 포트 이름에서 복원한다(missing 아님).
 */
export function buildNodePorts(
  nodeId: string,
  authoritative: PortSpec | undefined,
  edges: readonly EdgeSpec[],
): NodePorts {
  const inputs = toPortViews(authoritative?.inputs);
  const outputs = toPortViews(authoritative?.outputs);
  const flag = authoritative !== undefined;
  const add = (list: PortView[], name: string): void => {
    if (list.some((p) => p.id === name)) return;
    list.push(flag ? { id: name, label: name, missing: true } : { id: name, label: name });
  };
  for (const e of edges) {
    if (e.source.node === nodeId) add(outputs, e.source.port);
    if (e.target.node === nodeId) add(inputs, e.target.port);
  }
  return { inputs, outputs };
}

/** React Flow 핸들 id ↔ 포트. 방향 접두어로 입력/출력을 구분한다. */
export const inHandleId = (port: string): string => `in:${port}`;
export const outHandleId = (port: string): string => `out:${port}`;

export function parseHandleId(id: string | null | undefined): { side: "in" | "out"; port: string } | undefined {
  if (id === null || id === undefined) return undefined;
  if (id.startsWith("in:")) return { side: "in", port: id.slice(3) };
  if (id.startsWith("out:")) return { side: "out", port: id.slice(4) };
  return undefined;
}
