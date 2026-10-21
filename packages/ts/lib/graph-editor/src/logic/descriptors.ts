import type { NodeSpec, NodeTypeDescriptor } from "@agent-console/contracts";

/** 그래프 노드에 맞는 디스크립터: type_version이 같은 것, 없으면 최신 버전. 없으면 undefined(알 수 없는 타입). */
export function pickDescriptor(node: NodeSpec, descriptors: readonly NodeTypeDescriptor[]): NodeTypeDescriptor | undefined {
  const same = descriptors.filter((d) => d.id === node.type);
  if (same.length === 0) return undefined;
  if (node.type_version !== null && node.type_version !== undefined) {
    const exact = same.find((d) => (d.version ?? 1) === node.type_version);
    if (exact !== undefined) return exact;
  }
  return same.reduce((a, b) => ((b.version ?? 0) >= (a.version ?? 0) ? b : a));
}
