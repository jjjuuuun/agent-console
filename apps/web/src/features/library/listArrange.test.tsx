import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { agents, edgeTypes, nodeTypes, resourceTypes } from "../../testing/teamFixtures";
import { folderGroupDef, labelsGroupDef, modifiedSortDef, projectGroupDef } from "./arrangeDefs";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

const mk = (name: string, o: Record<string, unknown> = {}) => ({ id: name, name, ...o });

describe("정의 목록 공용 묶기·정렬 데이터", () => {
  it("폴더는 attributes.ui.folder를 읽고 값이 없으면 빈 폴더(없음)다", () => {
    const def = folderGroupDef<ReturnType<typeof mk>>();
    expect(def.usable).toBeUndefined();
    expect(def.read(mk("a"))).toEqual([""]);
    expect(def.read(mk("b", { attributes: { ui: { folder: "x/y" } } }))).toEqual(["x/y"]);
  });
  it("라벨은 여러 값, 프로젝트는 항목이 하나라도 있어야 쓸 수 있다", () => {
    expect(labelsGroupDef().multi).toBe(true);
    const def = projectGroupDef<ReturnType<typeof mk>>("없음");
    expect(def.usable?.([mk("a")]).ok).toBe(false);
    expect(def.usable?.([mk("a", { project: "p1" })]).ok).toBe(true);
  });
  it("최근 수정 정렬은 수정 시각이 있을 때만 후보다", () => {
    const def = modifiedSortDef();
    expect(def.available?.([mk("a")])).toBe(false);
    expect(def.available?.([mk("a", { saved_at: 1 })])).toBe(true);
  });
});

describe("리소스 목록 보기(5.2R.63)", () => {
  const list = [
    { id: "d1", type: "rt-doc", name: "문서 하나", version_hash: "v1", labels: ["공통"] },
    { id: "d2", type: "rt-doc", name: "문서 둘", version_hash: "v2" },
    { id: "c1", type: "rt-cfg", name: "설정 하나", version_hash: "v3", labels: ["공통"] },
  ];
  const clients = () =>
    createFakeClients({ listResourceTypes: vi.fn(async () => resourceTypes), listResources: vi.fn(async () => list), listAgents: vi.fn(async () => []) });

  it("기본은 종류별 묶음이고 머리에 디스크립터 제목이 보이며 접힘을 기억한다", async () => {
    mountApp(clients().clients, "/resources");
    const listbox = await screen.findByRole("listbox", { name: "리소스 목록" });
    const heads = Array.from(listbox.querySelectorAll<HTMLElement>(".ac-grouphead"));
    expect(heads.map((h) => h.textContent)).toEqual(["문서종류(2)", "설정종류(1)"]);
    expect(screen.getByRole("button", { name: /종류별 · 이름순/ })).toBeTruthy();
    fireEvent.click(heads[0]!);
    expect(JSON.parse(localStorage.getItem("ac.list.collapsed.resources.type")!)).toEqual(["문서종류"]);
    expect(within(listbox).queryByText("문서 하나")).toBeNull();
  });
});

describe("팀 구성 목록 보기(5.2R.63)", () => {
  const g = (id: string, name: string, o: Record<string, unknown> = {}) => ({ id, name, labels: [], version_hash: "h", node_count: 1, edge_count: 0, entry_labels: [], ...o });
  const clients = (graphs: unknown[]) =>
    createFakeClients({
      listGraphs: vi.fn(async () => graphs),
      listNodeTypes: vi.fn(async () => nodeTypes),
      listEdgeTypes: vi.fn(async () => edgeTypes),
      listResourceTypes: vi.fn(async () => resourceTypes),
      listAgents: vi.fn(async () => agents),
      listRuns: vi.fn(async () => []),
    });

  it("폴더 값이 없으면 평면이고 수정 시각이 없으면 최근 수정 정렬 옵션이 숨는다", async () => {
    mountApp(clients([g("t1", "팀 하나"), g("t2", "팀 둘")]).clients, "/teams");
    const grid = await screen.findByRole("grid", { name: "팀 구성 목록" });
    expect(grid.querySelector(".ac-grouphead")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /이름순/ }));
    expect(screen.getByRole("menuitemradio", { name: /^이름/ })).toBeTruthy();
    expect(screen.queryByRole("menuitemradio", { name: /최근 수정/ })).toBeNull();
  });

  it("라벨로 묶으면 머리 줄이 생기고 라벨 둘인 팀은 두 묶음에 보인다", async () => {
    const t = Math.floor(Date.now() / 1000);
    mountApp(clients([g("t1", "팀 하나", { labels: ["a", "b"], saved_at: t }), g("t2", "팀 둘", { labels: ["b"], saved_at: t })]).clients, "/teams");
    const grid = await screen.findByRole("grid", { name: "팀 구성 목록" });
    fireEvent.click(screen.getByRole("button", { name: /최근 수정순/ }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: /^라벨/ }));
    const heads = Array.from(grid.querySelectorAll<HTMLElement>(".ac-grouphead"));
    expect(heads.map((h) => h.textContent)).toEqual(["a(1)", "b(2)"]);
    expect(within(grid).getAllByText("팀 하나")).toHaveLength(2);
  });
});
