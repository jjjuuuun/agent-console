import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { startMessages } from "../start";
import { conversation, createHarness, type Harness } from "./testing/chatFakes";

beforeAll(preloadScreens, 120_000);
afterEach(cleanup);

function mount(h: Harness, path: string) {
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: [path] });
  render(<AppRoot createClients={async () => h.clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
  return router;
}

const empty = { listConversations: async () => [], listGraphs: async () => [], listAgents: async () => [], listRuns: async () => [] };
const presets = [
  { id: "p-b", name: "둘째", featured: 2, start_graph: "g-b", items: [{ kind: "graph", id: "g-b", name: "B" }], badges: ["체험"] },
  { id: "p-a", name: "첫째", featured: 1, start_graph: "g-a", items: [{ kind: "graph", id: "g-a", name: "A" }], badges: ["체험"] },
  { id: "p-x", name: "목록 밖", items: [] },
];

describe("첫 단계 안내 통일 (5.2R.10)", () => {
  it("시작하기 카드: 단계 3개(팀 만들기·대화 시작·결과 보기), 에이전트·리소스 단계 없음", async () => {
    mount(createHarness(empty), "/chat");
    const card = await screen.findByRole("region", { name: startMessages.title });
    const steps = within(card).getByRole("list", { name: startMessages.stepsLabel });
    expect(within(steps).getAllByRole("listitem").map((li) => li.getAttribute("data-step"))).toEqual(["create", "talk", "review"]);
    expect(card.textContent).not.toContain("에이전트 만들기");
    expect(card.textContent).not.toContain("리소스 연결");
  });

  it("5.2R.21: 대화가 없으면 빈 대화 목록 열을 접고, [+ 새 대화]는 목록 머리의 하나뿐이다", async () => {
    mount(createHarness(empty), "/chat");
    await screen.findByRole("region", { name: startMessages.title });
    expect(document.querySelector('[data-screen="chat"]')?.getAttribute("data-empty")).toBe("true");
    expect(screen.getAllByRole("button", { name: "+ 새 대화" })).toHaveLength(1);
    expect(document.querySelector(".chat-list-empty button")).toBeNull();
  });

  it("F7 회귀: 팀 만들기·결과 보기 버튼은 to 경로로 이동하고 새 대화 다이얼로그를 열지 않는다", async () => {
    const h = createHarness(empty);
    const router = mount(h, "/chat");
    const card = await screen.findByRole("region", { name: startMessages.title });
    const teamBtn = within(card).getByRole("link", { name: startMessages.steps["create"]!.action });
    expect(teamBtn.getAttribute("href")).toBe("/teams");
    expect(within(card).getByRole("link", { name: startMessages.steps["review"]!.action }).getAttribute("href")).toBe("/runs");
    fireEvent.click(teamBtn);
    await waitFor(() => expect(router.state.location.pathname).toBe("/teams"));
    expect(screen.queryByRole("dialog", { name: "새 대화" })).toBeNull();
  });

  it("팀 구성 목록 빈 상태도 같은 단계 문구를 쓴다(옛 '먼저 에이전트가 필요합니다' 없음)", async () => {
    mount(createHarness(empty), "/teams");
    const steps = await screen.findByRole("list", { name: startMessages.stepsLabel });
    expect(within(steps).getByText(startMessages.steps["create"]!.label)).toBeTruthy();
    expect(within(steps).getByText(startMessages.steps["talk"]!.hint)).toBeTruthy();
    expect(screen.queryByText("먼저 에이전트가 필요합니다")).toBeNull();
  });

  it("바로 시작: featured 순서, 목록 밖 프리셋은 숨김, 체험 배지", async () => {
    mount(createHarness({ ...empty, listPresets: async () => presets }), "/chat");
    const row = await screen.findByRole("region", { name: startMessages.quick.title });
    const cards = within(row).getAllByRole("listitem");
    expect(cards.map((c) => c.getAttribute("data-quick-start"))).toEqual(["p-a", "p-b"]);
    expect(cards[0]!.textContent).toContain("체험");
  });

  it("[시작] = 적용 -> start_graph의 target_id(이름 바뀜)로 대화 생성 -> 대화 화면", async () => {
    const applyPreset = vi.fn(async () => ({ preset_id: "p-a", items: [{ source: "s", kind: "graph", id: "g-a", target_id: "g-a-2", action: "created" }] }));
    const createConversation = vi.fn(async (req: { graph_id: string }) => conversation({ id: "c-new", graph_id: req.graph_id }));
    const router = mount(createHarness({ ...empty, listPresets: async () => presets, applyPreset, createConversation }), "/chat");
    const row = await screen.findByRole("region", { name: startMessages.quick.title });
    fireEvent.click(within(row).getByRole("button", { name: `첫째 ${startMessages.quick.start}` }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/chat/c-new"));
    expect(applyPreset).toHaveBeenCalledWith("p-a", {});
    expect(createConversation).toHaveBeenCalledWith({ graph_id: "g-a-2" });
  });

  it("프리셋 0개여도 단계 안내는 동작한다", async () => {
    mount(createHarness({ ...empty, listPresets: async () => [] }), "/chat");
    const card = await screen.findByRole("region", { name: startMessages.title });
    expect(within(card).queryByRole("region", { name: startMessages.quick.title })).toBeNull();
    expect(within(card).getAllByRole("listitem").length).toBe(3);
  });
});
