import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModuleInfo } from "@agent-console/contracts";
import { createHarness } from "../features/chat/testing/chatFakes";
import { createFakeClients } from "../testing/fakes";
import { mountApp } from "../testing/screenHarness";
import { LINK_PART_IDS, type LinkPartDef } from "../modules";
import { DEFAULT_LINK_PARTS } from "./linkParts";

afterEach(cleanup);

// 임의의 가짜 모듈·역할: 화면이 켜지는 데 필요한 역할(기본 라우트 데이터)은 모두 active로 두고,
// 연동 부분이 요구하는 역할(테스트가 정한 임의 문자열)만 켜거나 끈다.
const ALL_ROLES = ["conversations", "runs", "usage", "settings", "definitions:agent", "definitions:graph", "definitions:resource", "versions", "exports", "imports", "conversations:runs", "usage:tokens", "runs:trace", "runs:team-rules", "definitions:teams"];
const base = (status = "active"): ModuleInfo => ({ id: "base-mod", kind: "k-any", version: "1", status, web_roles: ALL_ROLES });
const link = (status: string): ModuleInfo => ({ id: "link-mod", kind: "k-link", version: "1", status, web_roles: ["role-link"] });
const only = (...ids: string[]): LinkPartDef[] => DEFAULT_LINK_PARTS.filter((p) => ids.includes(p.id)).map((p) => ({ ...p, requires: ["role-link"] }));

describe("기본 연동 부분 데이터", () => {
  it("모든 기능 역할이 active인 기본 서버에서는 어떤 부분도 가려지지 않는다", async () => {
    const h = createHarness({ listModules: vi.fn(async () => [base()]) });
    mountApp(h.clients, "/chat/c1");
    // 상호작용 카드(연동 부분)가 보인다
    expect(await screen.findByText("어느 쪽으로 할까요?")).toBeTruthy();
    await screen.findByLabelText("메시지 입력");
    expect(screen.queryByText(/메시지를 보낼 수 없습니다/)).toBeNull();
  });
});

describe("정의-팀 연동 역할(definitions:teams)", () => {
  const agentsFor = (roles: string[]) => createFakeClients({
    listModules: vi.fn(async () => [{ ...base(), web_roles: roles }]),
    listAgents: vi.fn(async () => [{ id: "ag1", name: "에이전트1", role: "r" }]),
    getAgentVersioned: vi.fn(async () => ({ value: { id: "ag1", name: "에이전트1", role: "r" }, version_hash: "h" })),
    listAgentUsages: vi.fn(async () => [{ kind: "graph", id: "tm1", name: "임의 팀", node_ids: [] }]),
  });

  it("두 부분은 모두 definitions:teams 하나만 요구한다", () => {
    const parts = DEFAULT_LINK_PARTS.filter((p) => p.id === LINK_PART_IDS.agentsUsagesPanel || p.id === LINK_PART_IDS.teamsDraftPreview);
    expect(parts).toHaveLength(2);
    for (const p of parts) expect(p.requires).toEqual(["definitions:teams"]);
  });

  it("역할이 없으면 에이전트 사용처 탭이 숨고 사용처 요청이 나가지 않는다", async () => {
    const { clients, rest } = agentsFor(ALL_ROLES.filter((r) => r !== "definitions:teams"));
    mountApp(clients, "/agents/ag1");
    await screen.findByLabelText("역할", { selector: "input" });
    expect(screen.queryByRole("tab", { name: /사용/ })).toBeNull();
    expect(rest["listAgentUsages"]).not.toHaveBeenCalled();
  });

  it("역할이 있으면 사용처 요청이 나가고 탭이 보인다", async () => {
    const { clients, rest } = agentsFor(ALL_ROLES);
    mountApp(clients, "/agents/ag1");
    await screen.findByLabelText("역할", { selector: "input" });
    await waitFor(() => expect(rest["listAgentUsages"]).toHaveBeenCalledWith("ag1"));
    expect(screen.getAllByRole("tab", { name: /사용/ }).length).toBeGreaterThan(0);
  });
});

describe("연동 부분이 꺼진 서버", () => {
  it("채팅: 전송은 비활성 + 이유, 상호작용 카드는 없고 상호작용 구독도 하지 않는다", async () => {
    const h = createHarness({ listModules: vi.fn(async () => [base(), link("disabled")]) });
    const subscribe = vi.spyOn(h.ws, "subscribeInteractions");
    mountApp(h.clients, "/chat/c1", { linkParts: only(LINK_PART_IDS.chatSend, LINK_PART_IDS.chatInteractionCard) });
    const input = (await screen.findByLabelText("메시지 입력")) as HTMLTextAreaElement;
    await waitFor(() => expect(input.disabled).toBe(false)); // 대화를 읽기 전에는 입력이 잠시 잠겨 있다
    fireEvent.change(input, { target: { value: "안녕" } });
    expect((await screen.findAllByText(/이 서버에서는 메시지를 보낼 수 없습니다/)).length).toBeGreaterThan(0);
    expect((screen.getByRole("button", { name: "전송" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText("어느 쪽으로 할까요?")).toBeNull();
    expect(subscribe).not.toHaveBeenCalled();
  });

  it("사용량: 토큰 집계 자리에 안내 한 줄만 남고 집계용 목록은 부르지 않는다", async () => {
    const { clients, rest } = createFakeClients({ listModules: vi.fn(async () => [base(), link("disabled")]) });
    mountApp(clients, "/usage", { linkParts: only(LINK_PART_IDS.usageTokenRollup) });
    expect(await screen.findByText("플랫폼 실행분 토큰 집계는 이 서버에서 꺼져 있습니다.")).toBeTruthy();
    expect(rest["listAgents"]).not.toHaveBeenCalled();
    expect(rest["listGraphs"]).not.toHaveBeenCalled();
  });

  it("실행 기록: 위임 집계 보기 전환이 없다", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => [base(), link("disabled")]), listRuns: vi.fn(async () => []) });
    mountApp(clients, "/runs?view=handoffs", { linkParts: only(LINK_PART_IDS.runsHandoffView) });
    await screen.findByRole("heading", { name: "실행 기록", level: 1 });
    expect(screen.queryByRole("tab", { name: /위임/ })).toBeNull();
    expect(clients.rest["getHandoffs"]).not.toHaveBeenCalled();
  });

  it("역할을 가진 모듈이 켜져 있으면 같은 데이터로도 부분이 보인다", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => [base(), link("active")]), listRuns: vi.fn(async () => []) });
    mountApp(clients, "/runs", { linkParts: only(LINK_PART_IDS.runsHandoffView) });
    await screen.findByRole("heading", { name: "실행 기록", level: 1 });
    expect(await screen.findByRole("tab", { name: /위임/ })).toBeTruthy();
  });
});
