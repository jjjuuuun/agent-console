import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createFakeClients, versionConflict } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { agents, resourceTypes } from "../../testing/teamFixtures";

afterEach(cleanup);

const effective = { value: { backend: null, model: "공통 모델" }, provenance: { "/model": "L0", "/system_prompt": "L1" }, layers: [{ id: "L0", label: "공통", source: "x" }, { id: "L1", label: "에이전트", source: "agent:ag1" }] };

function clients(extra: Record<string, unknown> = {}) {
  return createFakeClients({
    listAgents: vi.fn(async () => agents),
    listAgentUsages: vi.fn(async (id: string) => (id === "ag1" ? [{ kind: "graph", id: "tm1", name: "임의 팀", node_ids: ["a1"] }] : [])),
    getAgentVersioned: vi.fn(async (id: string) => ({ value: agents.find((a) => a.id === id), version_hash: "ah1" })),
    getAgentEffectiveSettings: vi.fn(async () => effective),
    updateAgentVersioned: vi.fn(async (_id: string, a: unknown) => ({ value: a, version_hash: "ah2" })),
    getAgentActivity: vi.fn(async () => [
      { event_id: "e1", run_id: "run-aaaa-1111", seq: 2, ts: 200, node_path: [], type: "x.done" },
      { event_id: "e2", run_id: "run-aaaa-1111", seq: 1, ts: 100, node_path: [], type: "x.start" },
    ]),
    listBackends: vi.fn(async () => []),
    listResourceTypes: vi.fn(async () => resourceTypes),
    listResources: vi.fn(async () => []),
    ...extra,
  });
}

describe("에이전트 목록", () => {
  it("이름순 목록에 사용 팀 수가 붙고 검색·미사용 필터가 동작한다", async () => {
    const { clients: c } = clients();
    mountApp(c, "/agents");
    const list = await screen.findByRole("listbox", { name: "에이전트 목록" });
    expect(within(list).getAllByRole("option").map((o) => o.textContent)).toEqual([expect.stringContaining("둘째 에이전트"), expect.stringContaining("첫째 에이전트")]);
    // 숫자 배지 대신 글자: 0곳이면 "팀에 없음", 1곳은 적지 않는다(5.2R.60)
    await waitFor(() => expect(within(list).getByText(/팀에 없음/)).toBeTruthy());
    expect(list.querySelector(".ac-badge")).toBeNull();
    expect(within(list).queryByText("상속")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "미사용" }));
    await waitFor(() => expect(within(screen.getByRole("listbox", { name: "에이전트 목록" })).getAllByRole("option")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "전체" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "에이전트 검색" }), { target: { value: "역할1" } });
    expect(within(screen.getByRole("listbox", { name: "에이전트 목록" })).getAllByRole("option")).toHaveLength(1);
  });

  it("새 에이전트는 이름·id·역할만으로 만든다", async () => {
    const createAgent = vi.fn(async (a: { id: string }) => a);
    const { clients: c } = clients({ createAgent });
    mountApp(c, "/agents");
    fireEvent.click(await screen.findByRole("button", { name: /새 에이전트/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("이름"), { target: { value: "My Agent" } });
    fireEvent.change(within(dialog).getByLabelText("역할"), { target: { value: "검토" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "만들기" }));
    await waitFor(() => expect(createAgent).toHaveBeenCalledWith({ id: "my-agent", name: "My Agent", role: "검토" }));
  });
});

describe("에이전트 아이콘(표시)", () => {
  it("목록 줄과 상세 머리에는 아바타가 없다", async () => {
    const { clients: c } = clients();
    const { container } = mountApp(c, "/agents/ag1");
    await screen.findByRole("heading", { name: "첫째 에이전트" });
    expect(container.querySelector(".lib-detail-head .lib-avatar, .lib-row .lib-avatar")).toBeNull();
  });

  it("고급 표시의 아이콘·색이 attributes.ui로 저장되고 비우면 키가 사라진다", async () => {
    const { clients: c, rest } = clients();
    mountApp(c, "/agents/ag1");
    fireEvent.click(await screen.findByText("표시 (고급)"));
    fireEvent.change(await screen.findByLabelText("아이콘"), { target: { value: "🚀" } });
    fireEvent.change(screen.getByLabelText("색"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(rest.updateAgentVersioned).toHaveBeenCalledTimes(1));
    expect(rest.updateAgentVersioned.mock.calls[0]![1]).toMatchObject({ attributes: { ui: { icon: "🚀", color: "3" } } });
  });

  it("저장된 아이콘·색을 비우면 저장이 켜지고 attributes.ui만 사라진다(다른 attributes는 그대로)", async () => {
    const base = agents.find((a) => a.id === "ag1")!;
    const withUi = { ...base, attributes: { keep: 1, ui: { icon: "A", color: "3" } } };
    const { clients: c, rest } = clients({ getAgentVersioned: vi.fn(async () => ({ value: withUi, version_hash: "ah1" })) });
    mountApp(c, "/agents/ag1");
    fireEvent.click(await screen.findByText("표시 (고급)"));
    fireEvent.change(await screen.findByLabelText("아이콘"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("색"), { target: { value: "" } });
    await waitFor(() => expect((screen.getByLabelText("아이콘") as HTMLInputElement).value).toBe(""));
    expect((screen.getByLabelText("색") as HTMLInputElement).value).toBe("");
    const save = screen.getByRole("button", { name: "저장" }) as HTMLButtonElement;
    await waitFor(() => expect(save.disabled).toBe(false));
    fireEvent.click(save);
    await waitFor(() => expect(rest.updateAgentVersioned).toHaveBeenCalledTimes(1));
    const sent = rest.updateAgentVersioned.mock.calls[0]![1] as { attributes?: Record<string, unknown> };
    expect(sent.attributes).toEqual({ keep: 1 });
  });
  it("아이콘 칸에서 Delete·Backspace 키로 지워도 삭제 대화상자가 열리지 않고 값이 비워진다(5.2R.26)", async () => {
    const base = agents.find((a) => a.id === "ag1")!;
    const withUi = { ...base, attributes: { ui: { icon: "A", color: "3" } } };
    const { clients: c } = clients({ getAgentVersioned: vi.fn(async () => ({ value: withUi, version_hash: "ah1" })) });
    mountApp(c, "/agents/ag1");
    fireEvent.click(await screen.findByText("표시 (고급)"));
    const icon = (await screen.findByLabelText("아이콘")) as HTMLInputElement;
    icon.focus();
    fireEvent.keyDown(icon, { key: "Delete" });
    fireEvent.keyDown(icon, { key: "Backspace" });
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.change(icon, { target: { value: "" } });
    await waitFor(() => expect((screen.getByLabelText("아이콘") as HTMLInputElement).value).toBe(""));
    await waitFor(() => expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(false));
  });
});

describe("에이전트 상세", () => {
  it("저장 원문에서 바꾼 필드만 If-Match로 저장한다(기본값이 이 층 값으로 굳지 않는다)", async () => {
    const { clients: c, rest } = clients();
    mountApp(c, "/agents/ag1");
    const role = await screen.findByLabelText("역할", { selector: "input" });
    fireEvent.change(role, { target: { value: "새 역할" } });
    expect(await screen.findByText("저장 안 됨")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(rest.updateAgentVersioned).toHaveBeenCalledTimes(1));
    const [id, sent, hash] = rest.updateAgentVersioned.mock.calls[0]!;
    expect(id).toBe("ag1");
    expect(hash).toBe("ah1");
    expect(sent).toMatchObject({ id: "ag1", name: "첫째 에이전트", role: "새 역할", system_prompt: "지침" });
    expect(sent).not.toHaveProperty("prompt_input_template");
    expect(sent).not.toHaveProperty("backend");
  });

  it("출처 표시: 상속 값은 공통 층 배지, 이 층 값은 에이전트 배지", async () => {
    const { clients: c } = clients();
    mountApp(c, "/agents/ag1");
    const form = await screen.findByText("시스템 프롬프트");
    expect(form).toBeTruthy();
    // 유효 설정(출처 표)은 에이전트와 따로 읽으므로 배지는 조금 뒤에 나온다
    expect((await screen.findAllByText(/공통에서 상속/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText("에이전트").length).toBeGreaterThan(0);
  });

  it("다른 곳에서 먼저 저장했으면 충돌 배너", async () => {
    const { clients: c } = clients({ updateAgentVersioned: vi.fn(async () => { throw versionConflict(); }) });
    mountApp(c, "/agents/ag1");
    fireEvent.change(await screen.findByLabelText("역할", { selector: "input" }), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(await screen.findByText("다른 곳에서 먼저 수정되었습니다")).toBeTruthy();
  });

  it("사용처 탭은 팀 구성 링크를, 최근 활동 탭은 실행별 묶음을 보인다", async () => {
    const { clients: c } = clients();
    mountApp(c, "/agents/ag1");
    fireEvent.click(await screen.findByRole("tab", { name: /사용처/ }));
    const link = await screen.findByRole("link", { name: "임의 팀" });
    expect(link.getAttribute("href")).toBe("/teams/tm1");
    fireEvent.click(screen.getByRole("tab", { name: "최근 활동" }));
    const run = await screen.findByRole("link", { name: /실행 상세 열기 run-aaaa/ });
    expect(run.getAttribute("href")).toContain("/runs/run-aaaa-1111?tab=agents&actor=ag1");
  });

  it("사용 중인 에이전트를 지울 때는 사용처를 보이고 이해 확인이 필요하다", async () => {
    const deleteAgent = vi.fn(async () => undefined);
    const { clients: c } = clients({ deleteAgent });
    mountApp(c, "/agents/ag1");
    await screen.findByLabelText("역할", { selector: "input" });
    fireEvent.click(screen.getByRole("button", { name: "에이전트 메뉴" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "삭제" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("임의 팀")).toBeTruthy();
    const del = within(dialog).getByRole("button", { name: "삭제" }) as HTMLButtonElement;
    expect(del.disabled).toBe(true);
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "이해했습니다" }));
    fireEvent.click(del);
    await waitFor(() => expect(deleteAgent).toHaveBeenCalledWith("ag1", "ah1"));
  });

  it("없는 에이전트는 안내", async () => {
    const { ApiError } = await import("@agent-console/api-client");
    const { clients: c } = clients({ getAgentVersioned: vi.fn(async () => { throw new ApiError(404, { code: "not_found", message: "x" }); }) });
    mountApp(c, "/agents/none");
    expect(await screen.findByText("에이전트를 찾을 수 없습니다")).toBeTruthy();
  });
});
