import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import type { DelegationStrategyDescriptor, EdgeTypeDescriptor, NodeSpec } from "@agent-console/contracts";
import { DelegationSettings, delegatorStrategies } from "./DelegationSettings";

afterEach(cleanup);

// 임의 이름: 설정 스키마가 있는 방식(s-cfg)과 없는 방식(s-plain)
const strategies = [
  { id: "s-cfg", title: "설정 있는 방식", description: "도구 이름을 정함", config_schema: { type: "object", properties: { tool: { type: "string", title: "도구 이름" } } } },
  { id: "s-plain", title: "설정 없는 방식", config_schema: { type: "object", properties: {} } },
] as unknown as DelegationStrategyDescriptor[];
const kinds = [
  { id: "k-a", title: "A", invocation: { strategy: "s-cfg" } },
  { id: "k-b", title: "B", invocation: { strategy: "s-plain" } },
  { id: "k-c", title: "C" },
] as unknown as EdgeTypeDescriptor[];
const node = (config?: Record<string, unknown>): NodeSpec => ({ id: "d", type: "t", ...(config ? { config } : {}) }) as NodeSpec;
const edges = (kind: string, config?: Record<string, unknown>) => ({ edges: [{ id: "e", kind, source: { node: "d", port: "o" }, target: { node: "x", port: "i" }, ...(config ? { config } : {}) }] });

describe("위임 방식 설정 폼", () => {
  it("위임자가 쓰는 방식 중 설정 스키마가 있는 것만 고른다(연결 종류의 invocation 속성과 연결 config의 덮어쓰기로)", () => {
    expect(delegatorStrategies(node(), edges("k-a"), kinds, strategies).map((s) => s.id)).toEqual(["s-cfg"]);
    expect(delegatorStrategies(node(), edges("k-b"), kinds, strategies)).toEqual([]);
    expect(delegatorStrategies(node(), edges("k-c"), kinds, strategies)).toEqual([]);
    expect(delegatorStrategies(node(), edges("k-b", { strategy: "s-cfg" }), kinds, strategies).map((s) => s.id)).toEqual(["s-cfg"]);
    // 위임자가 아닌 노드(도착 쪽)는 대상이 아니다
    expect(delegatorStrategies({ id: "x" } as NodeSpec, edges("k-a"), kinds, strategies)).toEqual([]);
  });

  function Host({ initial }: { initial?: Record<string, unknown> }) {
    const [n, setN] = useState(node(initial));
    return (
      <>
        <DelegationSettings node={n} graph={edges("k-a")} edgeTypes={kinds} strategies={strategies} onChange={(config) => setN({ ...n, config })} />
        <pre data-testid="cfg">{JSON.stringify(n.config ?? null)}</pre>
      </>
    );
  }
  it("방식 설정은 노드 config의 {방식 id: 설정} 아래에 저장되고, 비우면 키가 사라진다", () => {
    render(<Host initial={{ ref: "x" }} />);
    fireEvent.click(screen.getByText("설정 있는 방식"));
    const input = screen.getByLabelText("도구 이름");
    fireEvent.change(input, { target: { value: "ask" } });
    expect(JSON.parse(screen.getByTestId("cfg").textContent!)).toEqual({ ref: "x", delegation: { "s-cfg": { tool: "ask" } } });
    fireEvent.change(screen.getByLabelText("도구 이름"), { target: { value: "" } });
    expect(JSON.parse(screen.getByTestId("cfg").textContent!)).toEqual({ ref: "x" });
  });
  it("해당 방식이 없으면 아무것도 그리지 않는다", () => {
    const { container } = render(<DelegationSettings node={node()} graph={edges("k-c")} edgeTypes={kinds} strategies={strategies} onChange={() => {}} />);
    expect(container.textContent).toBe("");
  });
});
