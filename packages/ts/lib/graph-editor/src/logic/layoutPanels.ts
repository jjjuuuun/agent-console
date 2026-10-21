/**
 * 패널에 그릴 값 만들기(순수 함수). 노드 [배치] 탭이 보여 줄 "상속 (현재: …)" 값과 포트 행을
 * 결정 함수(layout.ts)와 노드의 최종 포트 목록에서 계산한다. React·React Flow에 의존하지 않는다.
 */
import type { Graph, NodeLayout, NodeSpec, NodeTypeDescriptor } from "@agent-console/contracts";
import type { NodeLayoutPanelProps, NodeLayoutPortRow } from "../components/NodeLayoutPanel";
import { BUILTIN_DIRECTIONS, portLayoutKey, resolveDirection, resolvePortSide } from "./layout";
import type { DirectionSides } from "./layout";
import { graphUiLayoutOf, withPortSide } from "./nodeLayoutOps";
import type { NodePorts } from "./ports";

export interface NodeLayoutModelInput {
  graph: Graph;
  node: NodeSpec;
  descriptor?: NodeTypeDescriptor | undefined;
  /** 노드의 최종 포트 목록(동적 포트 포함) */
  ports: NodePorts | undefined;
  layoutDefaults?: { direction?: string | null; edgeShape?: string | null } | undefined;
  directions?: DirectionSides | undefined;
}

const hintDirection = (d: NodeTypeDescriptor | undefined): string | null => {
  const v = d?.ui_hints?.["direction"];
  return typeof v === "string" ? v : null;
};

/** [배치] 탭 props에서 콜백을 뺀 값. */
export type NodeLayoutModel = Pick<NodeLayoutPanelProps, "layout" | "directions" | "inheritedDirection" | "ports">;

export function nodeLayoutModel(i: NodeLayoutModelInput): NodeLayoutModel {
  const directions = i.directions ?? BUILTIN_DIRECTIONS;
  const base = {
    graph: graphUiLayoutOf(i.graph),
    settings: i.layoutDefaults?.direction ?? null,
    hint: hintDirection(i.descriptor),
    directions,
  };
  const inherited = resolveDirection({ ...base, node: null });
  const rows: NodeLayoutPortRow[] = [];
  const add = (io: "in" | "out", list: readonly { id: string; label: string }[]): void => {
    for (const p of list) {
      const key = portLayoutKey(io, p.id);
      const without: NodeLayout | null = withPortSide(i.node.layout, key, null);
      rows.push({ key, io, id: p.id, label: p.label, inheritedSide: resolvePortSide({ ...base, node: without, io, portId: p.id }).side });
    }
  };
  add("in", i.ports?.inputs ?? []);
  add("out", i.ports?.outputs ?? []);
  return { layout: i.node.layout ?? null, directions, inheritedDirection: { id: inherited.value, source: inherited.source }, ports: rows };
}
