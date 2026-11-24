import { cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectView } from "@agent-console/contracts/projects";
import { ApiError } from "@agent-console/api-client";
import { mountApp } from "../../testing/screenHarness";
import { createFakeClients } from "../../testing/fakes";

afterEach(cleanup);

const mod = (id: string, roles: string[]) => ({ id, kind: "k", version: "0.0.1", status: "active", web_roles: roles });
const MODULES = [mod("m-1", ["conversations", "runs", "projects"])];
const view = (over: Partial<ProjectView>): ProjectView =>
  ({ project: { id: "a", name: "프로젝트 a", folder: "/home/me/work/a", description: "" }, status: "ready", config_writable: true, kinds: [], config_dir: ".cfg-dir", records_state: "ready", records_writable: true, version_hash: "h1", ...over }) as ProjectView;
const RAW = "records db unavailable: folder_missing";
const unavailable = view({ records_state: "unavailable", records_issue: { severity: "error", code: "project.records_unavailable", message: "m", details: { reason: "folder_missing" } } });
const newer = view({ records_state: "newer", records_writable: false });
const fail = () => { throw new ApiError(409, { code: "project.records_unavailable", message: RAW, details: { reason: "folder_missing" } }); };

function mount(v: ProjectView, path: string, extra: Record<string, unknown>) {
  const made = createFakeClients({ listModules: vi.fn(async () => MODULES), listProjects: vi.fn(async () => [v]), ...extra });
  return mountApp(made.clients, path);
}

describe("채팅·실행 목록의 기록 상태 띠", () => {
  it("기록 DB를 못 쓰는 프로젝트의 실행 목록은 서버 영문 원문 대신 홈과 같은 한국어 안내와 [경로 다시 지정]을 보인다", async () => {
    mount(unavailable, "/runs?prj=a", { listRuns: vi.fn(async () => fail()) });
    expect(await screen.findByRole("button", { name: "경로 다시 지정" })).toBeTruthy();
    await waitFor(() => expect(screen.queryByText(RAW)).toBeNull());
  });

  it("기록 DB를 못 쓰는 프로젝트의 채팅 목록도 원문을 보이지 않고 안내를 띄운다", async () => {
    mount(unavailable, "/chat?prj=a", { listConversations: vi.fn(async () => fail()) });
    expect(await screen.findByRole("button", { name: "경로 다시 지정" })).toBeTruthy();
    await waitFor(() => expect(screen.queryByText(RAW)).toBeNull());
  });

  it("더 새 리비전 기록 DB는 실행·채팅 목록에도 '앱을 업데이트하세요' 띠를 보인다", async () => {
    mount(newer, "/runs?prj=a", {});
    expect(await screen.findByRole("region", { name: /새 버전/ })).toBeTruthy();
    cleanup();
    mount(newer, "/chat?prj=a", {});
    expect(await screen.findByRole("region", { name: /새 버전/ })).toBeTruthy();
  });

  it("기록을 쓸 수 없는 프로젝트의 채팅 [새 대화]는 aria-disabled와 이유를 가진다", async () => {
    mount(newer, "/chat?prj=a", {});
    const btn = await screen.findByRole("button", { name: /새 대화$/ });
    expect(btn.getAttribute("aria-disabled")).toBe("true");
    expect(btn.getAttribute("title")).toMatch(/저장할 수 없습니다/);
  });

  it("읽기 전용 프로젝트는 대화가 0건이어도 목록 열을 접지 않고 안내·비활성 시작 단추와 이유를 보인다", async () => {
    mount(view({ config_writable: false, records_writable: false }), "/chat?prj=a", { listConversations: vi.fn(async () => []) });
    expect(await screen.findByRole("region", { name: /읽기 전용/ })).toBeTruthy();
    const screenEl = document.querySelector(".chat-screen");
    expect(screenEl?.getAttribute("data-empty")).toBeNull();
    const btn = await screen.findByRole("button", { name: /새 대화$/ });
    expect(btn.getAttribute("aria-disabled")).toBe("true");
    expect(btn.getAttribute("title")).toBeTruthy();
    // 시작하기 카드: 가져오기 단추는 이유와 함께 비활성, 전제가 안 끝난 [대화 시작]은 버튼 자체가 없다
    const imp = await screen.findByRole("button", { name: "공용에서 가져오기…" });
    expect(imp.getAttribute("aria-disabled")).toBe("true");
    expect(imp.getAttribute("title")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "대화 시작" })).toBeNull();
  });
});
