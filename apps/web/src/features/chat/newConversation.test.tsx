import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import type { CopyApplyRequest, ProjectView } from "@agent-console/contracts/projects";
import { mountApp } from "../../testing/screenHarness";
import { createFakeClients, createFakeRest } from "../../testing/fakes";
import { DEFINITION_KINDS } from "../library";

afterEach(cleanup);

const MODULES = [{ id: "m-1", kind: "k", version: "0.0.1", status: "active", web_roles: ["conversations", "runs", "projects", "definitions:graph"] }];
const view = (id: string, over: Partial<ProjectView> = {}): ProjectView =>
  ({
    project: { id, name: `프로젝트 ${id}`, folder: `/home/me/work/${id}`, description: "" },
    status: "ready",
    config_writable: true,
    kinds: [DEFINITION_KINDS.graph],
    config_dir: ".cfg-dir",
    records_state: "ready",
    records_writable: true,
    version_hash: "h1",
    ...over,
  }) as ProjectView;
const graph = (id: string, name = id, over: Record<string, unknown> = {}) => ({ id, name, version_hash: "v", node_count: 3, edge_count: 2, entry_labels: ["입구"], validation: null, ...over });

interface Setup {
  views?: ProjectView[];
  /** 프로젝트별 공간 그래프 목록(id -> 목록, null = 공용) */
  graphs?: Record<string, unknown[]>;
  rest?: Record<string, unknown>;
}
function mount(path: string, s: Setup = {}) {
  const spaces: Record<string, unknown[]> = { __library: [graph("lib-team", "공용 팀")], a: [graph("g1", "리뷰 팀"), graph("g2", "문서 팀")], ...s.graphs };
  const createConversation = vi.fn(async (b: { graph_id: string }) => ({ id: "c-new", graph_id: b.graph_id, created_at: 1, updated_at: 1 }));
  const made = createFakeClients({
    listModules: vi.fn(async () => MODULES),
    listProjects: vi.fn(async () => s.views ?? [view("a")]),
    listConversations: vi.fn(async () => []),
    listGraphs: vi.fn(async () => []),
    createConversation,
    // 가져오기 대화상자는 종류 목록과 항목을 복사 API로 읽는다(그래프 목록 API가 아님)
    listCopyKinds: vi.fn(async () => [{ kind: DEFINITION_KINDS.graph, library: true, portable: true }]),
    listCopyItems: vi.fn(async (space: string | null) => (spaces[space ?? "__library"] ?? []).map((g) => ({ kind: DEFINITION_KINDS.graph, id: (g as { id: string }).id, name: (g as { name: string }).name }))),
    ...s.rest,
  });
  made.space.mockImplementation(((id: string | null) => createFakeRest({ listGraphs: vi.fn(async () => spaces[id ?? "__library"] ?? []) })) as never);
  return { ...made, createConversation, ...mountApp(made.clients, path) };
}

describe("새 대화 대화상자(프로젝트 홈의 [채팅 시작] → ?new=1)", () => {
  it("폴더 줄 + 그 프로젝트 공간의 구성이 보이고, [대화 시작]이 project_id를 실어 대화를 만든다", async () => {
    const { createConversation, space, router } = mount("/chat?prj=a&new=1");
    const dialog = await screen.findByRole("dialog", { name: "새 대화" });
    expect(await within(dialog).findByText("프로젝트 a")).toBeTruthy();
    expect(within(dialog).getByText("폴더")).toBeTruthy();
    const radios = await within(dialog).findAllByRole("radio");
    expect(radios.map((r) => r.textContent)).toEqual([expect.stringContaining("리뷰 팀"), expect.stringContaining("문서 팀")]);
    expect(space).toHaveBeenCalledWith("a");
    // 제목 입력과 [대화 시작]이 같은 대화상자에 있다
    fireEvent.change(within(dialog).getByLabelText("제목"), { target: { value: "첫 대화" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "대화 시작" }));
    await waitFor(() => expect(createConversation).toHaveBeenCalled());
    expect(createConversation.mock.calls[0]?.[0]).toEqual({ graph_id: "g1", title: "첫 대화", project_id: "a" });
    await waitFor(() => expect(router.state.location.pathname).toBe("/chat/c-new"));
  });

  it("?new=1은 한 번 읽고 지운다", async () => {
    const { router } = mount("/chat?prj=a&new=1");
    await screen.findByRole("dialog", { name: "새 대화" });
    await waitFor(() => expect(router.state.location.search).not.toContain("new="));
  });

  it("폴더 문제 상태면 폴더 줄에 이유가 보이고 [대화 시작]은 aria-disabled + 이유, 만들지 않는다", async () => {
    const { createConversation } = mount("/chat?prj=a&new=1", { views: [view("a", { status: "folder_missing" })] });
    const dialog = await screen.findByRole("dialog", { name: "새 대화" });
    const start = within(dialog).getByRole("button", { name: "대화 시작" });
    await waitFor(() => expect(start.getAttribute("aria-disabled")).toBe("true"));
    expect(start.getAttribute("title")).toContain("폴더를 쓸 수 없어");
    fireEvent.click(start);
    expect(createConversation).not.toHaveBeenCalled();
  });

  it("기록을 쓸 수 없는 폴더(records_writable=false)도 시작을 막고 이유를 보인다", async () => {
    mount("/chat?prj=a&new=1", { views: [view("a", { records_writable: false })] });
    const dialog = await screen.findByRole("dialog", { name: "새 대화" });
    const start = within(dialog).getByRole("button", { name: "대화 시작" });
    await waitFor(() => expect(start.getAttribute("aria-disabled")).toBe("true"));
    expect(start.getAttribute("title")).toBe("이 폴더에 쓸 수 없어 대화·실행 기록을 저장할 수 없습니다");
  });

  it("구성 0개 → [공용에서 가져오기…] → 가져오면 방금 가져온 구성이 선택된다", async () => {
    const projectGraphs: unknown[] = [];
    const applyCopy = vi.fn(async (r: CopyApplyRequest) => {
      projectGraphs.push(graph("lib-team", "공용 팀"));
      return { items: r.items.map((i) => ({ kind: i.kind, id: i.id, status: "copied" })) };
    });
    const planCopy = vi.fn<(r: unknown) => Promise<unknown>>(async () => ({ items: [{ kind: DEFINITION_KINDS.graph, id: "lib-team", name: "공용 팀", reason: "requested", source_version: "v", target_state: "absent", default_action: "copy" }] }));
    mount("/chat?prj=a&new=1", { graphs: { a: projectGraphs }, rest: { planCopy, applyCopy } });
    const dialog = await screen.findByRole("dialog", { name: "새 대화" });
    expect(await within(dialog).findByText("이 프로젝트에 팀 구성이 없습니다")).toBeTruthy();
    // [대화 시작]은 구성을 고르기 전까지 막힘
    expect(within(dialog).getByRole("button", { name: "대화 시작" }).getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(within(dialog).getByRole("button", { name: "공용에서 가져오기…" }));
    const copyDialog = await screen.findByRole("dialog", { name: "공용에서 가져오기 — 프로젝트 a" });
    fireEvent.click(await within(copyDialog).findByRole("checkbox", { name: "공용 팀" }));
    fireEvent.click(within(copyDialog).getByRole("button", { name: "다음" }));
    fireEvent.click(await within(copyDialog).findByRole("button", { name: "가져오기 (1)" }));
    await waitFor(() => expect(applyCopy).toHaveBeenCalled());
    expect(applyCopy.mock.calls[0]?.[0]).toMatchObject({ source: { project_id: null }, target: { project_id: "a" } });
    // 복사 대화상자가 닫히고, 가져온 구성이 선택된 상태로 시작할 수 있다
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /공용에서 가져오기/ })).toBeNull());
    const radio = await within(dialog).findByRole("radio", { name: /공용 팀/ });
    await waitFor(() => expect(radio.getAttribute("aria-checked")).toBe("true"));
    expect(within(dialog).getByRole("button", { name: "대화 시작" }).getAttribute("aria-disabled")).toBeNull();
  }, 60_000);

  it("422 project.not_imported(in_library) → 경고 배너 + [가져와서 실행]이 계획 단계로 열리고, 전부 성공하면 같은 요청을 다시 보낸다", async () => {
    let calls = 0;
    const err = new ApiError(422, { code: "project.not_imported", message: "m", details: { project_id: "a", kind: DEFINITION_KINDS.graph, id: "g1", in_library: true } });
    const createConversation = vi.fn(async (b: { graph_id: string }) => {
      calls += 1;
      if (calls === 1) throw err;
      return { id: "c-new", graph_id: b.graph_id, created_at: 1, updated_at: 1 };
    });
    const planCopy = vi.fn<(r: unknown) => Promise<unknown>>(async () => ({ items: [{ kind: DEFINITION_KINDS.graph, id: "g1", name: "리뷰 팀", reason: "requested", source_version: "v", target_state: "absent", default_action: "copy" }] }));
    const applyCopy = vi.fn(async (r: CopyApplyRequest) => ({ items: r.items.map((i) => ({ kind: i.kind, id: i.id, status: "copied" })) }));
    mount("/chat?prj=a&new=1", { rest: { createConversation, planCopy, applyCopy } });
    const dialog = await screen.findByRole("dialog", { name: "새 대화" });
    await within(dialog).findAllByRole("radio");
    fireEvent.click(within(dialog).getByRole("button", { name: "대화 시작" }));
    expect(await within(dialog).findByText("‘리뷰 팀’은(는) 이 프로젝트에 없고 공용 구성에만 있습니다")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "가져와서 실행" }));
    const copyDialog = await screen.findByRole("dialog", { name: "공용에서 가져오기 — 프로젝트 a" });
    expect(planCopy.mock.calls[0]?.[0]).toMatchObject({ items: [{ kind: DEFINITION_KINDS.graph, id: "g1" }] });
    fireEvent.click(await within(copyDialog).findByRole("button", { name: "가져오고 실행 (1)" }));
    await waitFor(() => expect(createConversation).toHaveBeenCalledTimes(2));
  });

  it("in_library=false면 danger 배너 + [구성 화면으로]", async () => {
    const err = new ApiError(422, { code: "project.not_imported", message: "m", details: { project_id: "a", kind: DEFINITION_KINDS.graph, id: "g1", in_library: false } });
    mount("/chat?prj=a&new=1", { rest: { createConversation: vi.fn(async () => { throw err; }) } });
    const dialog = await screen.findByRole("dialog", { name: "새 대화" });
    await within(dialog).findAllByRole("radio");
    fireEvent.click(within(dialog).getByRole("button", { name: "대화 시작" }));
    expect(await within(dialog).findByText("‘리뷰 팀’을(를) 찾을 수 없습니다")).toBeTruthy();
    expect(within(dialog).getByRole("link", { name: "구성 화면으로" })).toBeTruthy();
    expect(within(dialog).queryByRole("button", { name: "가져와서 실행" })).toBeNull();
  });

  it("[바꾸기]로 이 대화상자의 대상 프로젝트만 바꾸면 그 프로젝트 공간의 구성을 다시 읽고 안내가 붙는다", async () => {
    const { space } = mount("/chat?prj=a&new=1", { views: [view("a"), view("b")], graphs: { b: [graph("bg", "다른 팀")] } });
    const dialog = await screen.findByRole("dialog", { name: "새 대화" });
    await within(dialog).findAllByRole("radio");
    fireEvent.click(within(dialog).getByRole("button", { name: "이 대화상자의 폴더 바꾸기" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "프로젝트 b" }));
    expect(await within(dialog).findByRole("radio", { name: /다른 팀/ })).toBeTruthy();
    expect(space).toHaveBeenCalledWith("b");
    expect(within(dialog).getByText("시작하면 현재 프로젝트가 ‘프로젝트 b’(으)로 바뀝니다.")).toBeTruthy();
  });
});
