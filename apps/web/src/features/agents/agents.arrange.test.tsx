import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Agent } from "@agent-console/contracts";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { resourceTypes } from "../../testing/teamFixtures";
import { agentGroupDefs, agentSortDefs, attributeKeys, folderPaths } from "./arrange";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

const mk = (id: string, extra: Record<string, unknown> = {}) => ({ kind: "agent", id, name: `에이전트-${id}`, ...extra }) as unknown as Agent;

describe("에이전트 묶는 기준 데이터", () => {
  const list = [
    mk("a", { role: "r1", labels: ["x", "y"], attributes: { ui: { folder: "개발팀/백엔드" }, team_tag: "t1", obj: { k: 1 } } }),
    mk("b", { role: "r2", attributes: { ui: { folder: "개발팀" } } }),
    mk("c", { role: "r3" }),
  ];
  it("폴더는 계층, 라벨은 여러 값, 역할은 모두 다르면 쓸 수 없다", () => {
    const defs = agentGroupDefs({ attrKey: "team_tag", roleReason: "사유" });
    expect(defs.find((d) => d.id === "folder")?.read(list[0]!)).toEqual(["개발팀/백엔드"]);
    expect(defs.find((d) => d.id === "labels")?.multi).toBe(true);
    expect(defs.find((d) => d.id === "role")?.usable?.(list)).toEqual({ ok: false, reason: "사유" });
    expect(defs.find((d) => d.id === "attribute")?.read(list[0]!)).toEqual(["t1"]);
  });
  it("속성 키 후보에는 ui와 객체 값이 없고, 폴더 후보에는 중간 단계가 있다", () => {
    expect(attributeKeys(list)).toEqual(["team_tag"]);
    expect(folderPaths(list)).toEqual(["개발팀", "개발팀/백엔드"]);
  });
  it("사용 많은 순 정렬은 사용 수가 있을 때만 후보에 있다", () => {
    expect(agentSortDefs(undefined).map((d) => d.id)).toEqual(["name"]);
    const defs = agentSortDefs((id) => (id === "b" ? 3 : 0));
    expect(defs.map((d) => d.id)).toEqual(["name", "usage"]);
    expect([...list].sort(defs[1]!.compare).map((a) => a.id)).toEqual(["b", "a", "c"]);
  });
});

function clients(list: Agent[], extra: Record<string, unknown> = {}) {
  return createFakeClients({
    listAgents: vi.fn(async () => list),
    listAgentUsages: vi.fn(async () => []),
    getAgentVersioned: vi.fn(async (id: string) => ({ value: list.find((a) => a.id === id), version_hash: "h1" })),
    updateAgentVersioned: vi.fn(async (_id: string, a: unknown) => ({ value: a, version_hash: "h2" })),
    listBackends: vi.fn(async () => []),
    listResourceTypes: vi.fn(async () => resourceTypes),
    listResources: vi.fn(async () => []),
    ...extra,
  });
}

describe("에이전트 목록 묶기(화면)", () => {
  it("폴더 값이 없으면 머리 없이 평면이고 보기 글자는 '폴더별 · 이름순'이다", async () => {
    const { clients: c } = clients([mk("a"), mk("b")]);
    mountApp(c, "/agents");
    const listbox = await screen.findByRole("listbox", { name: "에이전트 목록" });
    expect(listbox.querySelector(".ac-grouphead")).toBeNull();
    expect(screen.getByRole("button", { name: /폴더별 · 이름순/ }).getAttribute("title")).toBe("보기");
  });

  it("폴더 값이 있으면 머리가 계층으로 보이고 접으면 기억한다", async () => {
    const list = [
      mk("a", { attributes: { ui: { folder: "개발팀/백엔드" } } }),
      mk("b", { attributes: { ui: { folder: "개발팀" } } }),
      mk("c"),
    ];
    const { clients: c } = clients(list);
    mountApp(c, "/agents");
    const listbox = await screen.findByRole("listbox", { name: "에이전트 목록" });
    const heads = Array.from(listbox.querySelectorAll<HTMLElement>(".ac-grouphead"));
    expect(heads.map((h) => h.textContent)).toEqual(["개발팀(1)", "백엔드(1)", "(폴더 없음)(1)"]);
    fireEvent.click(heads[0]!);
    expect(JSON.parse(localStorage.getItem("ac.list.collapsed.agents.folder")!)).toEqual(["개발팀"]);
    expect(within(listbox).queryByText("에이전트-a")).toBeNull();
  });

  it("M으로 폴더 이동하면 다른 속성을 보존한 채 저장하고 되돌리기가 원복한다", async () => {
    const list = [mk("a", { attributes: { keep: 1, ui: { icon: "x" } } }), mk("b", { attributes: { ui: { folder: "기존" } } })];
    const updateAgentVersioned = vi.fn(async (_id: string, a: unknown) => ({ value: a, version_hash: "h2" }));
    const { clients: c } = clients(list, { updateAgentVersioned });
    mountApp(c, "/agents/a");
    const listbox = await screen.findByRole("listbox", { name: "에이전트 목록" });
    await waitFor(() => expect(within(listbox).getByText("에이전트-a")).toBeTruthy());
    fireEvent.keyDown(document.body, { key: "m" });
    const dialog = await screen.findByRole("dialog", { name: "폴더로 이동" });
    fireEvent.change(within(dialog).getByRole("searchbox", { name: "폴더 찾기 또는 새 이름 입력" }), { target: { value: "새폴더" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /새 폴더 "새폴더" 만들기/ }));
    await waitFor(() => expect(updateAgentVersioned).toHaveBeenCalledTimes(1));
    const [id, body, version] = updateAgentVersioned.mock.calls[0] as unknown as [string, Agent, string];
    expect(id).toBe("a");
    expect(version).toBe("h1");
    expect(body.attributes).toEqual({ keep: 1, ui: { icon: "x", folder: "새폴더" } });
    fireEvent.click((await screen.findAllByRole("button", { name: "되돌리기" })).find((b) => b.closest(".ac-toast") !== null)!);
    await waitFor(() => expect(updateAgentVersioned).toHaveBeenCalledTimes(2));
    expect((updateAgentVersioned.mock.calls[1] as unknown as [string, Agent])[1].attributes).toEqual({ keep: 1, ui: { icon: "x" } });
  });
});
