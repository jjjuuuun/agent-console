import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Project, ProjectView } from "@agent-console/contracts/projects";
import { mountApp } from "../../testing/screenHarness";
import { createFakeClients } from "../../testing/fakes";
import { ProjectSwitcher } from "./ProjectSwitcher";

afterEach(cleanup);

const project = (id: string, over: Partial<Project> = {}): Project => ({ id, name: id.toUpperCase(), ...over }) as Project;
/** 서버 목록 응답(ProjectView)으로 감싼다. */
const views = (...ps: Project[]): ProjectView[] => ps.map((p) => ({ project: p, status: "ready", config_writable: true, kinds: [], records_writable: true, config_dir: ".cfg-dir" }) as ProjectView);
const mod = (id: string, roles: string[]) => ({ id, kind: "k", version: "0.0.1", status: "active", web_roles: roles });
const conv = (id: string, project_id: string | null) => ({ id, graph_id: "g1", title: `대화-${id}`, created_at: 1, updated_at: 1, project_id });

describe("ProjectSwitcher(표현)", () => {
  it("프로젝트가 0개면 [프로젝트 만들기] 버튼 하나만 그린다", () => {
    const onCreate = vi.fn();
    render(<ProjectSwitcher projects={[]} current={null} onSelect={() => {}} onCreate={onCreate} />);
    fireEvent.click(screen.getByRole("button", { name: "프로젝트 만들기" }));
    expect(onCreate).toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("열면 모든 프로젝트와 프로젝트 목록이 있고, 고르면 닫힌다. 검색칸은 6개부터", () => {
    const onSelect = vi.fn();
    render(<ProjectSwitcher projects={[project("a"), project("b")]} current={null} onSelect={onSelect} onCreate={() => {}} onManage={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /프로젝트: 모든 프로젝트/ }));
    const list = screen.getByRole("listbox", { name: "프로젝트 목록" });
    expect(within(list).getAllByRole("option").map((o) => o.textContent)).toEqual(["모든 프로젝트✓", "A", "B"]);
    expect(screen.queryByRole("searchbox")).toBeNull();
    fireEvent.click(within(list).getByRole("option", { name: "B" }));
    expect(onSelect).toHaveBeenCalledWith("b");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByRole("button", { name: /프로젝트: 모든 프로젝트/ })).toBeTruthy();
  });

  it("프로젝트가 많으면 검색으로 거르고, 없는 이름이면 안내한다", () => {
    const many = ["a", "b", "c", "d", "e", "f"].map((id) => project(id));
    render(<ProjectSwitcher projects={many} current="c" onSelect={() => {}} onCreate={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /프로젝트: C/ }));
    const search = screen.getByRole("searchbox", { name: "프로젝트 검색" });
    fireEvent.change(search, { target: { value: "e" } });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["E"]);
    fireEvent.change(search, { target: { value: "zzz" } });
    expect(screen.getByText("일치하는 프로젝트가 없습니다")).toBeTruthy();
  });

  it("목록에서 방향키로 옮기고 Esc로 닫으면 트리거로 돌아온다", () => {
    render(<ProjectSwitcher projects={[project("a"), project("b")]} current={null} onSelect={() => {}} onCreate={() => {}} />);
    const trigger = screen.getByRole("button", { name: /프로젝트: 모든 프로젝트/ });
    fireEvent.click(trigger);
    const options = screen.getAllByRole("option");
    options[0]!.focus();
    fireEvent.keyDown(options[0]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(options[1]);
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});

/** 사이드바 프로젝트 영역(펼침 또는 레일)을 기다린다. */
async function findRegion() {
  return screen.findByRole("region", { name: "프로젝트" });
}
async function clickAdd() {
  const region = await findRegion();
  const railBtn = region.querySelector<HTMLElement>(".prj-rail-btn");
  if (railBtn !== null) {
    fireEvent.click(railBtn);
    fireEvent.click(await screen.findByRole("menuitem", { name: "폴더 추가" }));
    return;
  }
  fireEvent.click(within(region).getByRole("button", { name: "폴더 추가" }));
}

describe("앱 안의 프로젝트 UI", () => {
  it("주소의 ?prj= 로 들어오면 그 프로젝트가 현재이고, 없는 프로젝트면 첫 프로젝트(이름순)로 돌아간다 — 프로젝트가 있으면 '모든 프로젝트'는 없다", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => [mod("m-1", ["conversations", "projects"])]), listProjects: vi.fn(async () => views(project("b"), project("a"))) });
    const { router } = mountApp(clients, "/chat?prj=ghost");
    expect(await findRegion()).toBeTruthy();
    await waitFor(() => expect(router.state.location.search).not.toContain("ghost"));
    // 이름순 첫 프로젝트가 현재다(레일 아이콘 이름에 보인다)
    await waitFor(() => expect(screen.getByRole("button", { name: "프로젝트: A" })).toBeTruthy());
  });

  it("로그 필터 `project`(로그 묶음 id)는 현재 프로젝트를 바꾸지 않고 주소에 그대로 남는다(쿼리 이름 분리)", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => [mod("m-1", ["conversations", "projects"])]), listProjects: vi.fn(async () => views(project("a"), project("proj-a"))) });
    const { router } = mountApp(clients, "/chat?project=proj-a");
    expect(await findRegion()).toBeTruthy();
    await waitFor(() => expect(screen.getByRole("button", { name: "프로젝트: A" })).toBeTruthy());
    expect(router.state.location.search).toBe("?project=proj-a");
  });

  it("프로젝트 역할이 없으면 전환기·필터·태그가 전부 없고 나머지는 그대로 동작한다", async () => {
    const { clients, rest } = createFakeClients({ listModules: vi.fn(async () => [mod("m-1", ["conversations"])]), listConversations: vi.fn(async () => [conv("c-a", "a")]) });
    mountApp(clients, "/chat");
    const list = await screen.findByRole("listbox", { name: "대화 목록" });
    await waitFor(() => expect(within(list).getAllByRole("option")).toHaveLength(1));
    expect(screen.queryByRole("button", { name: /프로젝트/ })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "보기 범위" })).toBeNull();
    expect(rest.listProjects).not.toHaveBeenCalled();
  });

  it("모듈 목록을 못 받은 서버(구버전)에서도 프로젝트 UI를 만들지 않는다", async () => {
    const { clients, rest } = createFakeClients();
    mountApp(clients, "/chat");
    await screen.findByRole("complementary", { name: "사이드바" });
    expect(screen.queryByRole("button", { name: /프로젝트/ })).toBeNull();
    expect(rest.listProjects).not.toHaveBeenCalled();
  });

  it("프로젝트 0개면 [폴더 추가]로 폴더 대화상자가 열리고, 경로를 확인해 추가하면 그 프로젝트 홈으로 간다", async () => {
    const created = views(project("fresh", { name: "새 앱", folder: "/w/fresh" }))[0]!;
    let list: ProjectView[] = [];
    const checkFolder = vi.fn(async (r: { path: string }) => ({ input: r.path, path: r.path, exists: true, is_dir: true, readable: true, writable: true, can_create: false, status: "ok", suggested_id: "fresh", config_dir: ".cfg-dir" }));
    const createProject = vi.fn(async () => {
      list = [created];
      return { value: created, version_hash: "h" };
    });
    const { clients } = createFakeClients({
      listModules: vi.fn(async () => [mod("m-1", ["conversations", "projects"])]),
      listProjects: vi.fn(async () => list),
      getFolderCapabilities: vi.fn(async () => ({ browse: true, native_dialog: false })),
      listFolders: vi.fn(async () => ({ path: "/", entries: [], roots: [] })),
      checkFolder,
      createProject,
    });
    const { router } = mountApp(clients, "/chat");
    await clickAdd();
    const dialog = await screen.findByRole("dialog", { name: "프로젝트 폴더 추가" });
    fireEvent.click(within(dialog).getByRole("button", { name: "경로를 직접 입력" }));
    const input = within(dialog).getByLabelText("폴더 경로");
    fireEvent.change(input, { target: { value: "/w/fresh" } });
    fireEvent.blur(input);
    await waitFor(() => expect((within(dialog).getByLabelText(/^이름/) as HTMLInputElement).value).toBe("fresh"));
    fireEvent.change(within(dialog).getByLabelText(/^이름/), { target: { value: "새 앱" } });
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "프로젝트 추가" }));
    });
    await waitFor(() => expect(createProject).toHaveBeenCalledWith({ folder: "/w/fresh", name: "새 앱", id: "fresh" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/fresh"));
    expect(router.state.location.search).toContain("prj=fresh");
  });
});

describe("설정 > 프로젝트 섹션", () => {
  const modules = [mod("m-set", ["settings", "projects"])];

  it("프로젝트 역할이 있을 때만 섹션이 생기고, 없으면 목록에서 사라진다", async () => {
    const off = createFakeClients({ listModules: vi.fn(async () => [mod("m-set", ["settings"])]) });
    const first = mountApp(off.clients, "/settings");
    const nav = await screen.findByRole("navigation", { name: "설정 섹션" });
    await waitFor(() => expect(within(nav).getAllByRole("link").length).toBeGreaterThan(1));
    expect(within(nav).queryByRole("link", { name: /^프로젝트/ })).toBeNull();
    first.unmount();

    const on = createFakeClients({ listModules: vi.fn(async () => modules), listProjects: vi.fn(async () => views(project("a"))) });
    mountApp(on.clients, "/settings#projects");
    const nav2 = await screen.findByRole("navigation", { name: "설정 섹션" });
    expect(await within(nav2).findByRole("link", { name: /^프로젝트/ })).toBeTruthy();
  });

  const counts = (no_project: number, by_project: Record<string, number> = {}) => ({ total: no_project + Object.values(by_project).reduce((a, b) => a + b, 0), no_project, by_project });

  it("등록 표는 이름(홈 링크)·폴더·상태·동작만 두고 가이드·편집 폼이 없다", async () => {
    const a = project("a", { name: "앱", folder: "/w/app" });
    const { clients } = createFakeClients({ listModules: vi.fn(async () => modules), listProjects: vi.fn(async () => views(a)) });
    mountApp(clients, "/settings#projects");
    const table = await screen.findByRole("table", { name: "등록된 프로젝트" });
    expect(within(table).getByRole("link", { name: "앱" }).getAttribute("href")).toContain("/projects/a");
    expect(within(table).getByText("/w/app")).toBeTruthy();
    expect(within(table).getByRole("button", { name: /경로 다시 지정/ })).toBeTruthy();
    expect(within(table).getByRole("button", { name: /등록 해제/ })).toBeTruthy();
    expect(screen.queryByLabelText("작업 폴더")).toBeNull();
    expect(screen.queryByText(/삭제…/)).toBeNull();
  });

  it("앱에 남은 기록은 채팅 → 실행 순서로 select=project, remove_source 기본 켜짐으로 옮긴다", async () => {
    const a = project("a", { name: "앱", folder: "/w/app" });
    const calls: string[] = [];
    const { clients } = createFakeClients({
      listModules: vi.fn(async () => modules),
      listProjects: vi.fn(async () => views(a)),
      getConversationProjectCounts: vi.fn(async () => counts(0, { a: 3 })),
      getRunProjectCounts: vi.fn(async () => counts(0, { a: 2 })),
      moveConversationsToProject: vi.fn(async (r: unknown) => { calls.push(`chat:${JSON.stringify(r)}`); return { moved: 3 }; }),
      moveRunsToProject: vi.fn(async (r: unknown) => { calls.push(`run:${JSON.stringify(r)}`); return { moved: 2 }; }),
    });
    mountApp(clients, "/settings#projects");
    fireEvent.click(await screen.findByRole("button", { name: /앱 프로젝트 폴더로 옮기기/ }));
    const dialog = await screen.findByRole("dialog", { name: /이전 기록을 프로젝트 폴더로 옮기기/ });
    expect((within(dialog).getByRole("checkbox", { name: /옮긴 뒤 앱에서 지우기/ }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(within(dialog).getByRole("button", { name: "옮기기 (5)" }));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[0]).toBe('chat:{"project_id":"a","select":"project","remove_source":true}');
    expect(calls[1]).toBe('run:{"project_id":"a","select":"project","remove_source":true}');
  });

  it("프로젝트 없는 이전 기록은 기능별로 프로젝트에 넣고, 폴더에 바로 저장(기본 켜짐)이면 move-to-project를 부른다", async () => {
    const a = project("a", { name: "앱", folder: "/w/app" });
    const move = vi.fn(async () => ({ moved: 4 }));
    const { clients } = createFakeClients({
      listModules: vi.fn(async () => modules),
      listProjects: vi.fn(async () => views(a)),
      getConversationProjectCounts: vi.fn(async () => counts(4)),
      getRunProjectCounts: vi.fn(async () => counts(0)),
      moveConversationsToProject: move,
    });
    mountApp(clients, "/settings#projects");
    expect(await screen.findByText("프로젝트에 속하지 않은 이전 기록이 있습니다")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: /프로젝트에 넣기/ })[0] as HTMLElement);
    const dialog = await screen.findByRole("dialog", { name: /이전 기록 4건을 프로젝트에 넣기/ });
    expect(within(dialog).getByRole("button", { name: "넣기" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(within(dialog).getByRole("radio", { name: /앱/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "넣기" }));
    await waitFor(() => expect(move).toHaveBeenCalledWith({ project_id: "a", select: "null", remove_source: true }));
  });

  it("[그대로 두기]는 그 기능의 안내를 접고 [숨긴 안내 보기]로 다시 연다", async () => {
    const a = project("a", { name: "앱", folder: "/w/app" });
    const { clients } = createFakeClients({
      listModules: vi.fn(async () => modules),
      listProjects: vi.fn(async () => views(a)),
      getConversationProjectCounts: vi.fn(async () => counts(2)),
      getRunProjectCounts: vi.fn(async () => counts(0)),
    });
    mountApp(clients, "/settings#projects");
    fireEvent.click(await screen.findByRole("button", { name: /그대로 두기/ }));
    expect(screen.queryByRole("button", { name: /프로젝트에 넣기/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "숨긴 안내 보기" }));
    expect(await screen.findByRole("button", { name: /프로젝트에 넣기/ })).toBeTruthy();
  });

  it("등록 해제된 프로젝트는 접힌 목록에 앱 기록 개수와 함께 나온다", async () => {
    const a = project("a", { name: "앱", folder: "/w/app" });
    const gone = project("g", { name: "옛앱", folder: "/w/old", archived: true });
    const { clients } = createFakeClients({
      listModules: vi.fn(async () => modules),
      listProjects: vi.fn(async () => views(a, gone)),
      getConversationProjectCounts: vi.fn(async () => counts(0, { g: 3 })),
      getRunProjectCounts: vi.fn(async () => counts(0, { g: 2 })),
    });
    mountApp(clients, "/settings#projects");
    const summary = await screen.findByText("등록 해제된 프로젝트 (1)");
    fireEvent.click(summary);
    expect(await screen.findByText(/앱에 저장됨: 채팅 3 · 실행 2/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "다시 등록" })).toBeTruthy();
  });
});
