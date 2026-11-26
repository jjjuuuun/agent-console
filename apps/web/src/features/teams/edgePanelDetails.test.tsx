import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { EdgeSpec, EdgeTypeDescriptor, Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { IconRegistryProvider } from "@agent-console/ui";
import { ApiProvider } from "../../app/ApiContext";
import { appIcons } from "../../app/icons";
import { createAppQueryClient } from "../../app/queries";
import { ModulesProvider } from "../../modules";
import { createFakeClients } from "../../testing/fakes";
import { agents } from "../../testing/teamFixtures";
import { EdgePanel } from "./EdgePanel";
import type { TeamPanelContext } from "./panelContext";

afterEach(cleanup);

/**
 * 연결 패널 U-30 나머지(screen-delegation §14.4.3, 6R.20j): 포트 표시 이름 줄, 포트 id·분류 칩은 "자세히" 접힘 안, 속성 0개면 "연결 설정" 블록 없음.
 * 노드 타입·연결 종류·포트 이름은 전부 이 테스트가 만든 임의 값이다.
 */
const nodeTypes = [
  {
    id: "z-node", version: 1, title: "임의 노드", role: "z-r", executable: true, config_schema: { type: "object", properties: {} },
    static_ports: { inputs: [{ name: "i-raw" }, { name: "i-named", label: "받는 쪽 이름" }], outputs: [{ name: "o-raw" }, { name: "o-named", label: "보내는 쪽 이름" }] },
  },
] as unknown as NodeTypeDescriptor[];
const kind = (props: Record<string, unknown>, scheduling = "flow"): EdgeTypeDescriptor =>
  ({ id: "z-kind", title: "임의 종류", scheduling, config_schema: { type: "object", properties: props } }) as unknown as EdgeTypeDescriptor;

function mountPanel(edgeKind: EdgeTypeDescriptor, ports: { from: string; to: string }) {
  const graph = {
    id: "zg", name: "임의",
    nodes: [{ id: "A", type: "z-node", label: "가" }, { id: "B", type: "z-node", label: "나" }],
    edges: [{ id: "e1", kind: "z-kind", source: { node: "A", port: ports.from }, target: { node: "B", port: ports.to } }],
  } as unknown as Graph;
  const ctx: TeamPanelContext = {
    graphId: "zg", graph, savedNodeIds: new Set(), savedVersion: "h", dirty: false, nodeTypes, edgeTypes: [edgeKind], agents, resources: [], resourceTypes: [], interactionKinds: [],
    strategies: [], workspace: undefined, issues: [],
    plan: { data: undefined, isLoading: false, isError: false, isDraft: false, updating: false, error: null, refetch: () => {} } as never,
    disabled: false, onGraphChange: () => {}, onUndoableChange: () => {}, onApplySuggestion: () => {}, onPreviewBundle: () => {}, navigateTo: () => {},
  };
  const { clients } = createFakeClients({});
  return render(
    <QueryClientProvider client={createAppQueryClient({ retry: false })}>
      <ApiProvider clients={clients}>
        <ModulesProvider>
          <IconRegistryProvider icons={appIcons}>
            <EdgePanel ctx={ctx} edge={(graph.edges ?? [])[0] as EdgeSpec} />
          </IconRegistryProvider>
        </ModulesProvider>
      </ApiProvider>
    </QueryClientProvider>,
  );
}

describe("연결 패널 U-30", () => {
  it("포트 표시 이름 줄: 이름이 있으면 그 이름, 없으면 포트 id 원문(mono)", () => {
    const { container } = mountPanel(kind({}), { from: "o-named", to: "i-raw" });
    const line = container.querySelector(".team-edge-ports")!;
    expect(line.textContent).toBe("보내는 쪽 이름 → i-raw");
    expect(line.querySelectorAll(".lib-mono")).toHaveLength(1); // 원문(i-raw)만 mono
    expect(line.querySelector(".lib-mono")!.textContent).toBe("i-raw");
  });

  it("포트 id·분류 칩은 기본 영역에 없고 \"자세히\"를 펼치면 보인다(접으면 다시 사라진다)", () => {
    const { container } = mountPanel(kind({}), { from: "o-raw", to: "i-named" });
    const toggle = screen.getByRole("button", { name: "자세히" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(container.querySelector(".team-edge-details-list")).toBeNull();
    // 원문 id 줄은 접힘 안에서만 — 기본 영역에는 포트 표시 이름 줄만 있다
    expect(screen.queryByText("o-raw → i-named")).toBeNull();
    expect(container.querySelector("[data-edge-config] .ac-tag")).toBeNull(); // 분류 칩은 기본 영역에서 삭제

    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "자세히 접기" }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("포트 id")).toBeTruthy();
    expect(screen.getByText("o-raw → i-named")).toBeTruthy();
    expect(screen.getByText("분류")).toBeTruthy();
    expect(container.querySelector(".team-edge-details-list .ac-tag")!.textContent).toBe("순서"); // scheduling=flow

    fireEvent.click(screen.getByRole("button", { name: "자세히 접기" }));
    expect(container.querySelector(".team-edge-details-list")).toBeNull();
  });

  it("[복사]는 `out → in` 한 줄을 클립보드에 쓴다", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    mountPanel(kind({}), { from: "o-raw", to: "i-raw" });
    fireEvent.click(screen.getByRole("button", { name: "자세히" }));
    fireEvent.click(screen.getByRole("button", { name: "복사" }));
    expect(writeText).toHaveBeenCalledWith("o-raw → i-raw");
  });

  it("두 포트 모두 표시 이름이 있으면 줄에 mono 원문이 없다", () => {
    const { container } = mountPanel(kind({}), { from: "o-named", to: "i-named" });
    const line = container.querySelector(".team-edge-ports")!;
    expect(line.textContent).toBe("보내는 쪽 이름 → 받는 쪽 이름");
    expect(line.querySelector(".lib-mono")).toBeNull();
  });

  it("[복사]와 원문 mono 줄은 \"자세히\"를 펼치기 전에는 없다", () => {
    const { container } = mountPanel(kind({}), { from: "o-raw", to: "i-raw" });
    expect(screen.queryByRole("button", { name: "복사" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "자세히" }));
    const dd = container.querySelector(".team-edge-details-list dd .lib-mono")!;
    expect(dd.textContent).toBe("o-raw → i-raw");
  });

  it("분류 칩 문구는 scheduling 값별 메시지 표에서 온다(다른 값 대조)", () => {
    const { container } = mountPanel(kind({}, "entry"), { from: "o-raw", to: "i-raw" });
    fireEvent.click(screen.getByRole("button", { name: "자세히" }));
    expect(container.querySelector(".team-edge-details-list .ac-tag")!.textContent).toBe("입구");
  });

  it("메시지 표에 없는 scheduling 값이면 분류 행에 값 원문을 그대로 보인다(명세 §14.4.3)", () => {
    const { container } = mountPanel(kind({}, "z-unknown-scheduling"), { from: "o-raw", to: "i-raw" });
    fireEvent.click(screen.getByRole("button", { name: "자세히" }));
    expect(screen.getByText("분류")).toBeTruthy();
    expect(container.querySelector(".team-edge-details-list .ac-tag")!.textContent).toBe("z-unknown-scheduling");
  });

  it("스키마 속성이 0개면 \"연결 설정\" 블록(제목 포함)과 빈 안내가 없다", () => {
    const { container } = mountPanel(kind({}), { from: "o-raw", to: "i-raw" });
    expect(screen.queryByText("연결 설정")).toBeNull();
    expect(screen.queryByText("설정할 항목이 없습니다")).toBeNull();
    expect(container.querySelector(".lib-form [role=group], .lib-form form")).toBeNull();
  });

  it("스키마 속성이 있으면 \"연결 설정\" 제목이 나온다(대조)", () => {
    mountPanel(kind({ amount: { type: "integer", title: "양" } }), { from: "o-raw", to: "i-raw" });
    expect(screen.getByText("연결 설정")).toBeTruthy();
  });
});
