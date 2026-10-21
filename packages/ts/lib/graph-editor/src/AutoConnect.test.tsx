import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { GraphEditor, withoutEdges } from "./index";
import type { ChangeMeta, GraphEditorProps } from "./index";
import { teamEdgeTypes, teamNodeTypes } from "./testing";

beforeAll(() => {
  if (typeof globalThis.DOMMatrixReadOnly === "undefined") {
    globalThis.DOMMatrixReadOnly = class {
      m22 = 1;
      constructor() {}
    } as unknown as typeof DOMMatrixReadOnly;
  }
});
afterEach(cleanup);

const userOnly = (): Graph => ({ id: "g", name: "g", nodes: [{ id: "h1", type: "beta-human", label: "사용자", config: {}, position: { x: 0, y: 0 } }], edges: [] });
const lists = { things: [{ id: "t1", name: "정의 하나" }] };

function setup(over: Partial<GraphEditorProps>) {
  const calls: Array<{ next: Graph; meta: ChangeMeta }> = [];
  let graph = userOnly();
  const el = () => (
    <div style={{ width: 1000, height: 600 }}>
      <GraphEditor graph={graph} nodeTypes={teamNodeTypes} edgeTypes={teamEdgeTypes} showMinimap={false} definitionLists={lists} definitionKindTitles={{ things: "에이전트" }} onChange={(next, meta) => { calls.push({ next, meta }); graph = next; }} {...over} />
    </div>
  );
  const r = render(el());
  return { calls, rerender: () => r.rerender(el()) };
}

const addAgent = () => fireEvent.doubleClick(within(screen.getByRole("region", { name: "에이전트" })).getByText("정의 하나"));

describe("입구·답변 자동 연결 (GraphEditor)", () => {
  it("autoConnectIo가 켜져 있으면 한 번의 onChange(auto-connect)로 노드와 두 연결을 낸다", () => {
    const onAutoConnect = vi.fn();
    const { calls } = setup({ autoConnectIo: true, onAutoConnect });
    addAgent();
    expect(calls).toHaveLength(1);
    expect(calls[0]!.meta.reason).toBe("auto-connect");
    expect(calls[0]!.next.edges!.map((e) => e.kind)).toEqual(["e-start", "e-end"]);
    const info = onAutoConnect.mock.calls[0]![0] as { addedEdgeIds: string[]; graph: Graph };
    expect(withoutEdges(info.graph, info.addedEdgeIds).edges).toEqual([]);
  });
  it("기본(끔)이면 노드만 추가한다", () => {
    const { calls } = setup({});
    addAgent();
    expect(calls[0]!.meta.reason).toBe("add-node");
    expect(calls[0]!.next.edges).toEqual([]);
  });
  it("onAutoConnect가 없으면 내부 토스트의 [되돌리기]가 두 연결만 제거한다", () => {
    const { calls, rerender } = setup({ autoConnectIo: true });
    addAgent();
    rerender();
    expect(screen.getByText("입구·답변 연결을 만들었습니다")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "되돌리기" }));
    const last = calls.at(-1)!;
    expect(last.meta.reason).toBe("undo");
    expect(last.next.edges).toEqual([]);
    expect(last.next.nodes).toHaveLength(2);
  });
});
