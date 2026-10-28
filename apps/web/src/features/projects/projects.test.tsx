import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Project } from "@agent-console/contracts/projects";
import { mountApp } from "../../testing/screenHarness";
import { createFakeClients } from "../../testing/fakes";
import { guideSteps } from "./ProjectGuide";
import { ProjectSwitcher } from "./ProjectSwitcher";

afterEach(cleanup);

const project = (id: string, over: Partial<Project> = {}): Project => ({ id, name: id.toUpperCase(), ...over }) as Project;
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

describe("첫 프로젝트 안내 단계", () => {
  it("완료 여부는 서버 데이터로만 계산한다", () => {
    expect(guideSteps({ projects: [], project: undefined, hasConversation: false }).map((s) => s.done)).toEqual([false, false, false]);
    const p = project("a", { folder: "/w" });
    expect(guideSteps({ projects: [p], project: p, hasConversation: false }).map((s) => s.done)).toEqual([true, true, false]);
    expect(guideSteps({ projects: [p], project: p, hasConversation: true }).map((s) => s.done)).toEqual([true, true, true]);
    // 계약 0.11.0: 폴더가 없는 옛 프로젝트(folder_unset)는 설정 단계가 끝나지 않았다
    const legacy = project("b", { folder: null });
    expect(guideSteps({ projects: [legacy], project: legacy, hasConversation: false })[1]!.done).toBe(false);
  });
});


/** 사이드바 프로젝트 영역(펼침 또는 레일)을 기다린다. */
async function findRegion() {
  return screen.findByRole("region", { name: "프로젝트" });
}
/** 영역에서 프로젝트를 고른다: 레일이면 팝오버를 열고 메뉴 항목, 펼침이면 항목 버튼. */
async function pickProject(name: string) {
  const region = await findRegion();
  const railBtn = region.querySelector<HTMLElement>(".prj-rail-btn");
  if (railBtn !== null) {
    fireEvent.click(railBtn);
    fireEvent.click(await screen.findByRole("menuitemradio", { name: new RegExp(`^${name}`) }));
    return;
  }
  fireEvent.click(within(region).getByRole("button", { name: new RegExp(`^${name}`) }));
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
  it("프로젝트 역할이 있으면 사이드바에 프로젝트 영역이 있고, 고르면 주소와 대화 목록이 따라간다", async () => {
    const { clients } = createFakeClients(
      { listModules: vi.fn(async () => [mod("m-1", ["conversations", "projects"])]), listConversations: vi.fn(async () => [conv("c-a", "a"), conv("c-b", "b"), conv("c-shared", null)]) },
      { listProjects: vi.fn(async () => [project("a"), project("b")]) },
    );
    const { router } = mountApp(clients, "/chat");
    const list = await screen.findByRole("listbox", { name: "대화 목록" });
    await waitFor(() => expect(within(list).getAllByRole("option")).toHaveLength(3));

    await pickProject("A");

    await waitFor(() => expect(router.state.location.search).toContain("prj=a"));
    await waitFor(() => expect(within(screen.getByRole("listbox", { name: "대화 목록" })).getAllByRole("option").map((o) => o.textContent)).toEqual(expect.arrayContaining([expect.stringContaining("대화-c-a"), expect.stringContaining("대화-c-shared")])));
    const rows = within(screen.getByRole("listbox", { name: "대화 목록" })).getAllByRole("option");
    expect(rows).toHaveLength(2);
    expect(screen.getByText("범위 밖 1개 숨김")).toBeTruthy();

    // 보기 범위를 "이 프로젝트만"으로
    fireEvent.change(screen.getByRole("combobox", { name: "보기 범위" }), { target: { value: "project_only" } });
    await waitFor(() => expect(within(screen.getByRole("listbox", { name: "대화 목록" })).getAllByRole("option")).toHaveLength(1));

    // 칩의 ✕ = 모든 프로젝트 보기
    fireEvent.click(screen.getByRole("button", { name: /모든 프로젝트 보기로/ }));
    await waitFor(() => expect(within(screen.getByRole("listbox", { name: "대화 목록" })).getAllByRole("option")).toHaveLength(3));
    expect(router.state.location.search).not.toContain("prj=");
  });

  it("주소의 ?prj= 로 들어오면 그 프로젝트가 현재이고, 없는 프로젝트면 모든 프로젝트로 돌아간다", async () => {
    const { clients } = createFakeClients(
      { listModules: vi.fn(async () => [mod("m-1", ["conversations", "projects"])]) },
      { listProjects: vi.fn(async () => [project("a")]) },
    );
    const { router } = mountApp(clients, "/chat?prj=ghost");
    expect(await findRegion()).toBeTruthy();
    await waitFor(() => expect(router.state.location.search).not.toContain("ghost"));
  });

  it("로그 필터 `project`(로그 묶음 id)는 현재 프로젝트를 바꾸지 않고 주소에 그대로 남는다(쿼리 이름 분리)", async () => {
    const { clients } = createFakeClients(
      { listModules: vi.fn(async () => [mod("m-1", ["conversations", "projects"])]) },
      { listProjects: vi.fn(async () => [project("a"), project("proj-a")]) },
    );
    const { router } = mountApp(clients, "/chat?project=proj-a");
    expect(await findRegion()).toBeTruthy();
    await new Promise((r) => setTimeout(r, 50));
    expect(router.state.location.search).toBe("?project=proj-a");
  });

  it("직접 진입해 프로젝트 목록이 늦게 로드돼도, 프로젝트를 바꾸면 이전 프로젝트의 로그 필터가 교체된다", async () => {
    let release: (v: Project[]) => void = () => undefined;
    const late = new Promise<Project[]>((r) => (release = r));
    const { clients } = createFakeClients(
      { listModules: vi.fn(async () => [mod("m-1", ["conversations", "projects", "logs"])]) },
      { listProjects: vi.fn(() => late) },
    );
    const { router } = mountApp(clients, "/logs/sessions?prj=a&project=a");
    await new Promise((r) => setTimeout(r, 100));
    release([project("a"), project("b")]);
    await screen.findByRole("button", { name: "필터 초기화" });
    await pickProject("B");
    await waitFor(() => expect(router.state.location.search).toContain("prj=b"));
    await waitFor(() => expect(router.state.location.search).toContain("project=b"));
  });

  it("프로젝트 역할이 없으면 전환기·필터·태그가 전부 없고 나머지는 그대로 동작한다", async () => {
    const { clients, projects } = createFakeClients({ listModules: vi.fn(async () => [mod("m-1", ["conversations"])]), listConversations: vi.fn(async () => [conv("c-a", "a")]) });
    mountApp(clients, "/chat");
    const list = await screen.findByRole("listbox", { name: "대화 목록" });
    await waitFor(() => expect(within(list).getAllByRole("option")).toHaveLength(1));
    expect(screen.queryByRole("button", { name: /프로젝트/ })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "보기 범위" })).toBeNull();
    expect(projects.listProjects).not.toHaveBeenCalled();
  });

  it("모듈 목록을 못 받은 서버(구버전)에서도 프로젝트 UI를 만들지 않는다", async () => {
    const { clients, projects } = createFakeClients();
    mountApp(clients, "/chat");
    await screen.findByRole("complementary", { name: "사이드바" });
    expect(screen.queryByRole("button", { name: /프로젝트/ })).toBeNull();
    expect(projects.listProjects).not.toHaveBeenCalled();
  });

  it("프로젝트 0개면 [폴더 추가]로 만들기 창이 열리고, 만들면 그 프로젝트로 전환한다", async () => {
    const created = project("fresh", { name: "새 앱" });
    let list: Project[] = [];
    const { clients, projects } = createFakeClients(
      { listModules: vi.fn(async () => [mod("m-1", ["conversations", "projects"])]) },
      { listProjects: vi.fn(async () => list), createProject: vi.fn(async () => { list = [created]; return { value: created, version_hash: "h" }; }) },
    );
    const { router } = mountApp(clients, "/chat");
    await clickAdd();
    const dialog = await screen.findByRole("dialog", { name: "새 프로젝트" });
    fireEvent.change(within(dialog).getByLabelText(/^이름/), { target: { value: "새 앱" } });
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "만들기" }));
    });
    await waitFor(() => expect(projects.createProject).toHaveBeenCalled());
    await waitFor(() => expect(router.state.location.search).toContain("prj=fresh"));
    expect((await screen.findAllByRole("button", { name: /프로젝트.*새 앱/ })).length).toBeGreaterThan(0);
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

    const on = createFakeClients({ listModules: vi.fn(async () => modules) }, { listProjects: vi.fn(async () => [project("a")]) });
    mountApp(on.clients, "/settings#projects");
    const nav2 = await screen.findByRole("navigation", { name: "설정 섹션" });
    expect(await within(nav2).findByRole("link", { name: /^프로젝트/ })).toBeTruthy();
  });

  it("프로젝트를 고쳐 저장하면 바뀐 필드만 If-Match 해시와 함께 보낸다", async () => {
    const a = project("a", { name: "앱", folder: "/old" });
    const { clients, projects } = createFakeClients(
      { listModules: vi.fn(async () => modules) },
      {
        listProjects: vi.fn(async () => [a]),
        getProjectVersioned: vi.fn(async () => ({ value: a, version_hash: "h1" })),
        updateProject: vi.fn(async () => ({ value: a, version_hash: "h2" })),
      },
    );
    mountApp(clients, "/settings#projects");
    const dir = (await screen.findByLabelText("작업 폴더")) as HTMLInputElement;
    fireEvent.change(dir, { target: { value: "/new" } });
    fireEvent.click(screen.getByRole("button", { name: "프로젝트 저장" }));
    await waitFor(() => expect(projects.updateProject).toHaveBeenCalledWith("a", { folder: "/new" }, "h1"));
  });

  it("삭제는 삭제 계획을 보여 주고 고른 방식으로 지운다", async () => {
    const a = project("a", { name: "앱" });
    const { clients, projects } = createFakeClients(
      { listModules: vi.fn(async () => modules) },
      {
        listProjects: vi.fn(async () => [a]),
        getProjectVersioned: vi.fn(async () => ({ value: a, version_hash: "h1" })),
        getDeletePlan: vi.fn(async () => ({ project_id: "a", default_mode: "move_to_shared", definitions: [{ kind: "k-x", id: "d1", name: "정의 하나" }], warnings: [] })),
        deleteProject: vi.fn(async () => undefined),
      },
    );
    mountApp(clients, "/settings#projects");
    fireEvent.click(await screen.findByRole("button", { name: "삭제…" }));
    const dialog = await screen.findByRole("dialog", { name: /프로젝트 “앱” 삭제/ });
    expect(await within(dialog).findByText("정의 하나")).toBeTruthy();
    expect((within(dialog).getByRole("radio", { name: /공용으로 옮기기/ }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(within(dialog).getByRole("radio", { name: /함께 삭제/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "삭제" }));
    await waitFor(() => expect(projects.deleteProject).toHaveBeenCalledWith("a", { mode: "delete_definitions" }));
  });
});
