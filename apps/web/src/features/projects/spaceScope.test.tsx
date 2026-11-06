import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CopyApplyRequest, ProjectView } from "@agent-console/contracts/projects";
import { mountApp } from "../../testing/screenHarness";
import { createFakeClients, createFakeRest } from "../../testing/fakes";
import { DEFINITION_KINDS } from "../library";

afterEach(cleanup);

/** 구성 화면 머리의 공간 칩(사이드바의 프로젝트 칩과 구분한다). */
const chip = () => document.querySelector<HTMLElement>(".space-chip") as HTMLElement;

const MODULES = [{ id: "m-1", kind: "k", version: "0.0.1", status: "active", web_roles: ["projects", "definitions:graph", "definitions:agent", "definitions:resource", "conversations"] }];
const view = (id: string, over: Partial<ProjectView> = {}): ProjectView =>
  ({
    project: { id, name: `프로젝트 ${id}`, folder: `/home/me/work/${id}`, description: "" },
    status: "ready",
    config_writable: true,
    kinds: [DEFINITION_KINDS.graph, DEFINITION_KINDS.agent, DEFINITION_KINDS.resource],
    config_dir: ".cfg-dir",
    records_state: "ready",
    records_writable: true,
    version_hash: "h1",
    ...over,
  }) as ProjectView;
const graph = (id: string, name = id) => ({ id, name, version_hash: "v", node_count: 1, edge_count: 0, entry_labels: [], validation: null, saved_at: 100 });

function mount(path: string, over: Record<string, unknown> = {}, views: ProjectView[] = [view("a")]) {
  const made = createFakeClients({
    listModules: vi.fn(async () => MODULES),
    listProjects: vi.fn(async () => views),
    listGraphs: vi.fn(async () => [graph("lib-team", "공용 팀")]),
    listAgents: vi.fn(async () => []),
    listResources: vi.fn(async () => []),
    ...over,
  });
  const spaceGraphs = vi.fn(async () => [graph("copy-team", "사본 팀")]);
  made.space.mockImplementation(((id: string | null) => createFakeRest({ listGraphs: id === null ? made.rest.listGraphs : spaceGraphs, listAgents: vi.fn(async () => []), listResources: vi.fn(async () => []) })) as never);
  return { ...made, spaceGraphs, ...mountApp(made.clients, path) };
}

describe("구성 화면의 공간(?prj=)", () => {
  it("?prj가 없으면 공용: 공용 목록을 읽고 머리 칩은 '공용', 사본 안내 줄은 없다", async () => {
    const { rest, spaceGraphs, router } = mount("/teams");
    expect(await screen.findByText("공용 팀")).toBeTruthy();
    expect(chip().getAttribute("data-space")).toBe("library");
    expect(spaceGraphs).not.toHaveBeenCalled();
    expect(rest.listGraphs).toHaveBeenCalled();
    expect(screen.queryByText("이 프로젝트의 사본입니다. 수정은 공용 구성에 영향을 주지 않습니다.")).toBeNull();
    // 공용 화면에 현재 프로젝트 질의가 다시 붙지 않는다
    expect(router.state.location.search).toBe("");
  });

  it("?prj=a면 그 프로젝트의 사본 저장소를 읽고, 머리 칩과 한 줄 안내가 '프로젝트: …'로 바뀐다", async () => {
    const { space, spaceGraphs } = mount("/teams?prj=a");
    expect(await screen.findByText("사본 팀")).toBeTruthy();
    expect(screen.queryByText("공용 팀")).toBeNull();
    expect(space).toHaveBeenCalledWith("a");
    expect(spaceGraphs).toHaveBeenCalled();
    expect(chip().getAttribute("aria-label")).toBe("프로젝트: 프로젝트 a");
    expect(chip().getAttribute("data-space")).toBe("project");
    expect(screen.getByText("이 프로젝트의 사본입니다. 수정은 공용 구성에 영향을 주지 않습니다.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "← 프로젝트 a 홈" })).toBeTruthy();
  });

  it("칩을 열면 [공용 구성 보기]가 같은 화면의 ?prj 없는 주소로 간다", async () => {
    const { router } = mount("/teams?prj=a");
    await screen.findByText("사본 팀");
    fireEvent.click(chip());
    fireEvent.click(screen.getByRole("link", { name: "공용 구성 보기" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/teams"));
    expect(router.state.location.search).toBe("");
    expect(await screen.findByText("공용 팀")).toBeTruthy();
  });

  it("모르는 프로젝트 id는 공용으로 본다", async () => {
    const { spaceGraphs } = mount("/teams?prj=ghost");
    expect(await screen.findByText("공용 팀")).toBeTruthy();
    expect(spaceGraphs).not.toHaveBeenCalled();
  });
});

describe("구성 목록의 복사 동작", () => {
  it("공용 화면: 선택한 항목을 [이 프로젝트로 가져오기…]하면 복사 계획 대화상자가 계획 단계로 열린다", async () => {
    const planCopy = vi.fn<(r: unknown) => Promise<unknown>>(async () => ({ items: [{ kind: DEFINITION_KINDS.graph, id: "lib-team", name: "공용 팀", reason: "requested", source_version: "v", target_state: "absent", default_action: "copy" }] }));
    const applyCopy = vi.fn(async (r: CopyApplyRequest) => ({ items: r.items.map((i) => ({ kind: i.kind, id: i.id, status: "copied" })) }));
    mount("/teams", { planCopy, applyCopy });
    await screen.findByText("공용 팀");
    fireEvent.click(screen.getByRole("button", { name: "선택" }));
    fireEvent.click(screen.getByText("공용 팀"));
    fireEvent.click(await screen.findByRole("button", { name: "선택한 1개를 이 프로젝트로 가져오기…" }));
    const dialog = await screen.findByRole("dialog", { name: "공용에서 가져오기 — 프로젝트 a" });
    expect(planCopy.mock.calls[0]?.[0]).toEqual({ source: { project_id: null }, target: { project_id: "a" }, items: [{ kind: DEFINITION_KINDS.graph, id: "lib-team" }], include_references: true });
    fireEvent.click(await within(dialog).findByRole("button", { name: "가져오기 (1)" }));
    await waitFor(() => expect(applyCopy).toHaveBeenCalled());
  });

  it("프로젝트 사본 화면: 같은 동작이 [공용에 저장…]이고 방향이 반대(원본 = 프로젝트, 대상 = 공용)", async () => {
    const planCopy = vi.fn<(r: unknown) => Promise<unknown>>(async () => ({ items: [{ kind: DEFINITION_KINDS.graph, id: "copy-team", name: "사본 팀", reason: "requested", source_version: "v", target_state: "absent", default_action: "copy" }] }));
    mount("/teams?prj=a", { planCopy });
    await screen.findByText("사본 팀");
    fireEvent.click(screen.getByRole("button", { name: "선택" }));
    fireEvent.click(screen.getByText("사본 팀"));
    fireEvent.click(await screen.findByRole("button", { name: "공용에 저장…" }));
    await screen.findByRole("dialog", { name: "공용에 저장 — 프로젝트 a" });
    expect(planCopy.mock.calls[0]?.[0]).toMatchObject({ source: { project_id: "a" }, target: { project_id: null } });
  });

  it("프로젝트가 읽기 전용 폴더면 가져오기 동작이 aria-disabled가 아니라 눌러도 열리지 않는다(이유는 도구 title)", async () => {
    const planCopy = vi.fn();
    mount("/teams", { planCopy }, [view("a", { config_writable: false })]);
    await screen.findByText("공용 팀");
    fireEvent.click(screen.getByRole("button", { name: "선택" }));
    fireEvent.click(screen.getByText("공용 팀"));
    const act = await screen.findByRole("button", { name: /이 프로젝트로 가져오기/ });
    fireEvent.click(act);
    expect(planCopy).not.toHaveBeenCalled();
  });

  it("프로젝트가 하나도 없으면 가져오기 도구가 없다", async () => {
    mount("/teams", {}, []);
    await screen.findByText("공용 팀");
    expect(screen.queryByRole("button", { name: "선택" })).toBeNull();
  });
});
