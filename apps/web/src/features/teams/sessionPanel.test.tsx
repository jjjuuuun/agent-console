import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DelegationStrategyDescriptor, EdgeSpec, EdgeTypeDescriptor, Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { IconRegistryProvider } from "@agent-console/ui";
import { ApiProvider } from "../../app/ApiContext";
import { appIcons } from "../../app/icons";
import { createAppQueryClient } from "../../app/queries";
import { ModulesProvider } from "../../modules";
import { createFakeClients } from "../../testing/fakes";
import { agents } from "../../testing/teamFixtures";
import { EdgeLegend, legendRows } from "./EdgeLegend";
import { EdgePanel } from "./EdgePanel";
import { SessionWhere } from "./SessionWhere";
import { incomingSessions, nodeSessionMode } from "./sessionView";
import type { TeamPanelContext } from "./panelContext";

afterEach(cleanup);

/**
 * R0: 테스트 전용 위임 방식(새 id·임의 속성 값)을 데이터로만 더해도 칩·동작 방식 블록·비교표·범례가 코드 수정 없이 나와야 한다.
 */
const nodeTypes = [
  { id: "z-node", version: 1, title: "임의 노드", role: "z-r", executable: true, config_schema: { type: "object", properties: {} }, static_ports: { inputs: [{ name: "i" }], outputs: [{ name: "o" }] } },
] as unknown as NodeTypeDescriptor[];
const kindDeleg = { id: "z-deleg", title: "임의 위임", description: "임의 위임 설명", scheduling: "none", invocation: { strategy: "zs-1" }, config_schema: { type: "object", properties: { strategy: { type: ["string", "null"], default: null, title: "위임 방식" } } } } as unknown as EdgeTypeDescriptor;
const kindFlow = { id: "z-flow", title: "임의 흐름", scheduling: "flow", session: "zq", config_schema: { type: "object", properties: {} } } as unknown as EdgeTypeDescriptor;
const strategies = [
  { id: "zs-1", title: "방식 하나", description: "첫 방식", member_fields: [], max_depth: 1, session: "x1", backend: "y2", nestable: false },
  { id: "zs-2", title: "방식 둘", member_fields: [], max_depth: null, session: "same", backend: "target", nestable: true },
  { id: "zs-3", title: "속성 없는 방식", member_fields: [], max_depth: undefined },
] as unknown as DelegationStrategyDescriptor[];

const graph0 = (config?: Record<string, unknown>): Graph =>
  ({
    id: "zg", name: "임의",
    nodes: [{ id: "L", type: "z-node", label: "리더" }, { id: "W", type: "z-node", label: "일꾼" }],
    edges: [{ id: "ed", kind: "z-deleg", source: { node: "L", port: "o" }, target: { node: "W", port: "i" }, ...(config ? { config } : {}) }],
  }) as unknown as Graph;

function Harness({ initial, onUndoable, list = strategies }: { initial: Graph; onUndoable?: (text: string) => void; list?: DelegationStrategyDescriptor[] }) {
  const [graph, setGraph] = useState<Graph>(initial);
  const ctx: TeamPanelContext = {
    graphId: "zg", graph, savedNodeIds: new Set(), savedVersion: "h", dirty: false, nodeTypes, edgeTypes: [kindDeleg, kindFlow], agents, resources: [], resourceTypes: [], interactionKinds: [],
    strategies: list, workspace: undefined, issues: [],
    plan: { data: undefined, isLoading: false, isError: false, isDraft: false, updating: false, error: null, refetch: () => {} } as never,
    disabled: false, onGraphChange: setGraph, onUndoableChange: (next, text) => { setGraph(next); onUndoable?.(text); }, onApplySuggestion: () => {}, onPreviewBundle: () => {}, navigateTo: () => {},
  };
  return <EdgePanel ctx={ctx} edge={(graph.edges ?? [])[0] as EdgeSpec} />;
}
function mount(ui: React.ReactNode) {
  const { clients } = createFakeClients({});
  return render(
    <QueryClientProvider client={createAppQueryClient({ retry: false })}>
      <ApiProvider clients={clients}>
        <ModulesProvider>
          <IconRegistryProvider icons={appIcons}>{ui}</IconRegistryProvider>
        </ModulesProvider>
      </ApiProvider>
    </QueryClientProvider>,
  );
}

describe("연결 패널: 동작 방식 블록·비교표(R0)", () => {
  it("임의 속성 값의 방식도 행·칩·옵션 요약이 나오고, 모르는 값은 원문이다", async () => {
    mount(<Harness initial={graph0()} />);
    const block = await screen.findByRole("region", { name: "동작 방식" });
    expect(within(block).getByText("실행 세션")).toBeTruthy();
    expect(within(block).getAllByText("x1").length).toBeGreaterThan(0); // 칩 + 원문 값
    expect(within(block).getByText("y2")).toBeTruthy();
    expect(within(block).getByText("1단계 — 대상은 다시 위임할 수 없습니다")).toBeTruthy();
    expect(within(block).getByText("불가")).toBeTruthy();
    // 방식 선택: 기본 문구와 속성 요약 보조 줄
    const combo = screen.getByRole("combobox", { name: /위임 방식/ });
    expect(combo.textContent).toContain("종류 기본 — 방식 하나");
    fireEvent.click(combo);
    const options = within(screen.getByRole("listbox", { name: "위임 방식 목록" })).getAllByRole("option");
    expect(options.map((o) => o.querySelector(".ses-option-title")!.textContent)).toEqual(["종류 기본 — 방식 하나", "방식 하나", "방식 둘", "속성 없는 방식"]);
    expect(options[2]!.querySelector(".ses-option-sub")!.textContent).toBe("같은 세션 · 깊이 제한 없음 · 대상 백엔드 · 중첩 가능");
    expect(options[3]!.querySelector(".ses-option-sub")).toBeNull(); // 속성 없는 방식은 보조 줄 없음
  });

  it("비교표: 현재 방식이 첫 열이고 열 머리로 방식을 바꾸면 되돌리기용 변경으로 적용된다", async () => {
    const seen = vi.fn();
    mount(<Harness initial={graph0()} onUndoable={seen} />);
    const block = await screen.findByRole("region", { name: "동작 방식" });
    fireEvent.click(within(block).getByRole("button", { name: /다른 방식과 비교/ }));
    const heads = within(block).getAllByRole("columnheader").slice(1);
    expect(heads.map((h) => h.textContent)).toEqual(["방식 하나", "방식 둘", "속성 없는 방식"]);
    fireEvent.click(within(heads[1]!).getByRole("button"));
    expect(seen).toHaveBeenCalledWith("위임 방식을 ‘방식 둘’(으)로 바꿨습니다");
    // 바뀐 방식이 현재 열(첫 열)이 된다
    const after = await screen.findByRole("region", { name: "동작 방식" });
    expect(within(after).getAllByText("같은 세션").length).toBeGreaterThan(0);
  });

  it("속성이 하나도 없는 방식은 블록이 없고, 알 수 없는 방식은 안내만 나온다", async () => {
    mount(<Harness initial={graph0({ strategy: "zs-3" })} />);
    await screen.findByRole("combobox", { name: /위임 방식/ });
    expect(screen.queryByRole("region", { name: "동작 방식" })).toBeNull();
    cleanup();
    mount(<Harness initial={graph0({ strategy: "ghost" })} />);
    expect(await screen.findByText("방식 ‘ghost’를 알 수 없습니다")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "동작 방식" })).toBeNull();
  });
});

describe("범례·노드 패널 첫 줄(R0)", () => {
  it("범례 행: 쓰는 종류는 방식·세션 칩과 함께, 없는 종류는 접힘, 세션 칩 설명은 문구가 있는 값만", () => {
    const edges = (graph0().edges ?? []) as never;
    const rows = legendRows(edges, [kindDeleg, kindFlow], strategies);
    expect(rows.used.map((r) => r.kind.id)).toEqual(["z-deleg"]);
    expect(rows.unused.map((r) => r.kind.id)).toEqual(["z-flow"]);
    mount(<EdgeLegend edges={edges} edgeTypes={[kindDeleg, kindFlow]} strategies={strategies} renderIcon={() => null} />);
    const button = screen.getByRole("button", { name: /연결 범례/ });
    fireEvent.click(button);
    const dialog = screen.getByRole("dialog", { name: "연결 범례" });
    expect(within(dialog).getByText(/임의 위임 · 방식 하나/)).toBeTruthy();
    expect(within(dialog).getByText(/이 팀에 없는 종류 1개/)).toBeTruthy();
    // 설명이 있는 세션 값(same)만 설명 행이 있고, 모르는 값(x1·zq)은 행이 없다
    expect(within(dialog).getByText("위임자 세션 안에서 실행됩니다")).toBeTruthy();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "연결 범례" })).toBeNull();
    expect(document.activeElement).toBe(button);
  });

  it("노드 패널 첫 줄: 같은 세션이면 위임자와 백엔드 문구, 별도 세션이면 없음", () => {
    const g = graph0({ strategy: "zs-2" });
    const mode = nodeSessionMode(incomingSessions("W", g, [kindDeleg, kindFlow], strategies));
    mount(<SessionWhere mode={mode} strategies={strategies} onViewEdge={() => {}} />);
    expect(screen.getByText(/실행 위치: 리더 세션 안/)).toBeTruthy();
    expect(screen.getByText(/대상 자신의 백엔드를 씁니다/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "연결 보기" })).toBeTruthy();
    cleanup();
    const none = nodeSessionMode(incomingSessions("W", graph0(), [kindDeleg, kindFlow], strategies));
    const { container } = mount(<SessionWhere mode={none} strategies={strategies} />);
    expect(container.querySelector("[data-session-where]")).toBeNull();
  });
});
