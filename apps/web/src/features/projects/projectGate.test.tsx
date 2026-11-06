import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Project, ProjectView } from "@agent-console/contracts/projects";
import { mountApp } from "../../testing/screenHarness";
import { createFakeClients } from "../../testing/fakes";

afterEach(cleanup);

const project = (id: string, over: Partial<Project> = {}): Project => ({ id, name: id.toUpperCase(), folder: `/w/${id}`, ...over }) as Project;
const views = (...ps: Project[]): ProjectView[] => ps.map((p) => ({ project: p, status: "ready", config_writable: true, kinds: [], records_writable: true }) as ProjectView);
const mod = (id: string, roles: string[]) => ({ id, kind: "k", version: "0.0.1", status: "active", web_roles: roles });
const modules = [mod("m", ["conversations", "runs", "logs", "memory", "projects", "settings", "definitions:graph"])];

describe("프로젝트 문맥 화면 문지기(33p)", () => {
  it("프로젝트가 0개면 채팅·실행·로그·메모리 본문 전체가 NoProjectState 하나로 바뀌고 액션·필터가 없다", async () => {
    for (const path of ["/chat", "/runs", "/logs/sessions", "/memory"]) {
      const { clients } = createFakeClients({ listModules: vi.fn(async () => modules), listProjects: vi.fn(async () => []) });
      const view = mountApp(clients, path);
      const none = await screen.findByTestId("no-project-state", {}, { timeout: 5000 });
      expect(within(none).getByRole("button", { name: "폴더 추가" })).toBeTruthy();
      expect(screen.queryByRole("searchbox")).toBeNull();
      expect(screen.queryByText("프로젝트 없이도 모든 기능을 쓸 수 있습니다")).toBeNull();
      view.unmount();
    }
  });

  it("목록 조회가 실패하면 0개로 단정하지 않고 오류 블록과 다시 시도를 보인다", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => modules), listProjects: vi.fn(async () => { throw new Error("boom"); }) });
    mountApp(clients, "/chat");
    expect(await screen.findByText("프로젝트 목록을 불러오지 못했습니다", {}, { timeout: 5000 })).toBeTruthy();
    expect(screen.queryByTestId("no-project-state")).toBeNull();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeTruthy();
  });

  it("프로젝트 기능이 없는 조립에서는 문지기가 없고 화면이 단독으로 동작한다", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => [mod("m", ["conversations"])]) });
    mountApp(clients, "/chat");
    await waitFor(() => expect(screen.queryByTestId("no-project-state")).toBeNull());
  });

  it("프로젝트가 있으면 채팅 목록 질의에 현재 프로젝트가 실리고 프로젝트 이름 줄이 보인다", async () => {
    const listConversations = vi.fn(async () => []);
    const { clients } = createFakeClients({ listModules: vi.fn(async () => modules), listProjects: vi.fn(async () => views(project("a", { name: "앱" }), project("b", { name: "비" }))), listConversations });
    mountApp(clients, "/chat?prj=b");
    await waitFor(() => expect(listConversations).toHaveBeenCalledWith({ project: "b" }));
    expect(await screen.findByTitle("/w/b")).toBeTruthy();
  });

  it("실행 목록 질의에 현재 프로젝트가 실리고 프로젝트가 바뀌면 다시 묻는다", async () => {
    const listRuns = vi.fn(async () => []);
    const { clients } = createFakeClients({ listModules: vi.fn(async () => modules), listProjects: vi.fn(async () => views(project("a"), project("b"))), listRuns });
    const { router } = mountApp(clients, "/runs?prj=a");
    await waitFor(() => expect(listRuns).toHaveBeenCalledWith(expect.objectContaining({ project: "a" })));
    await router.navigate("/runs?prj=b");
    await waitFor(() => expect(listRuns).toHaveBeenCalledWith(expect.objectContaining({ project: "b" })));
  });

  it("로그 세션 목록 질의에 project=<등록 id>가 실리고 프로젝트 필터 칸이 없다", async () => {
    const listLogSessions = vi.fn(async () => []);
    const { clients } = createFakeClients({ listModules: vi.fn(async () => modules), listProjects: vi.fn(async () => views(project("a"))), listLogSessions });
    mountApp(clients, "/logs/sessions");
    await waitFor(() => expect(listLogSessions).toHaveBeenCalled());
    expect(JSON.stringify(listLogSessions.mock.calls[0])).toContain('"project":"a"');
    expect(screen.queryByRole("button", { name: /^프로젝트$/ })).toBeNull();
  });

  it("프로젝트 칩은 이름과 경로를 가진 버튼이고 누르면 전체 경로·홈·바꾸기가 나온다", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => modules), listProjects: vi.fn(async () => views(project("a", { name: "앱" }))), listRuns: vi.fn(async () => []) });
    mountApp(clients, "/runs");
    const chip = await screen.findByRole("button", { name: "프로젝트 앱, 경로 /w/a" }, { timeout: 5000 });
    fireEvent.click(chip);
    expect(await screen.findByText("프로젝트 폴더")).toBeTruthy();
    expect(screen.getByRole("button", { name: "프로젝트 홈으로" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "프로젝트 바꾸기…" })).toBeTruthy();
  });
});
