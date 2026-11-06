import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectView } from "@agent-console/contracts/projects";
import { mountApp } from "../../testing/screenHarness";
import { createFakeClients, createFakeRest } from "../../testing/fakes";
import { DEFINITION_KINDS } from "../library";
import { MAX_VISIBLE_BANNERS, problemBanners, manifestPath, mergeActivity, relativeTime } from "./projectHomeLib";

afterEach(cleanup);

const mod = (id: string, roles: string[]) => ({ id, kind: "k", version: "0.0.1", status: "active", web_roles: roles });
const MODULES = [mod("m-1", ["conversations", "runs", "projects", "logs", "memory"])];
const view = (id: string, over: Partial<ProjectView> = {}, project: Partial<ProjectView["project"]> = {}): ProjectView =>
  ({
    project: { id, name: `프로젝트 ${id}`, folder: `/home/me/work/${id}`, description: "", ...project },
    status: "ready",
    config_writable: true,
    kinds: [DEFINITION_KINDS.agent],
    config_dir: ".cfg-dir",
    records_state: "ready",
    records_writable: true,
    version_hash: "h1",
    ...over,
  }) as ProjectView;

/** 사이드바 영역(펼침이면 항목 버튼, 레일이면 팝오버 메뉴 항목)에서 프로젝트 행을 찾는다. */
async function findRow(name: RegExp): Promise<HTMLElement> {
  const region = await screen.findByRole("region", { name: "프로젝트" });
  await waitFor(() => expect(region.querySelector(".prj-rail-btn, .prj-row")).not.toBeNull());
  const rail = region.querySelector<HTMLElement>(".prj-rail-btn");
  if (rail !== null) {
    fireEvent.click(rail);
    return screen.findByRole("menuitemradio", { name });
  }
  return within(region).findByRole("button", { name });
}
/** [폴더 추가]를 누른다(레일이면 팝오버 메뉴 항목). */
async function clickAddFolder() {
  const region = await screen.findByRole("region", { name: "프로젝트" });
  const rail = region.querySelector<HTMLElement>(".prj-rail-btn");
  if (rail !== null) {
    fireEvent.click(rail);
    fireEvent.click(await screen.findByRole("menuitem", { name: "폴더 추가" }));
    return;
  }
  fireEvent.click(within(region).getByRole("button", { name: "폴더 추가" }));
}

function mount(views: ProjectView[], path: string, extra: Record<string, unknown> = {}) {
  const made = createFakeClients({ listModules: vi.fn(async () => MODULES), listProjects: vi.fn(async () => views), ...extra });
  made.space.mockReturnValue(createFakeRest({ listAgents: vi.fn(async () => [{ id: "pl", name: "기획 에이전트" }]) }) as never);
  const app = mountApp(made.clients, path);
  return { ...made, ...app };
}

describe("projectHomeLib", () => {
  it("배너 순서: 폴더 문제 → 기록 → 설정 파일 → 읽기 전용 → 안내, 같은 원인의 기록 배너는 접는다", () => {
    const v = view("a", { status: "folder_missing", records_state: "unavailable", records_issue: { severity: "error", code: "x", message: "m", details: { reason: "folder_missing" } } });
    expect(problemBanners(v, "구성").map((b) => b.kind)).toEqual(["folder"]);
    const bad = view("a", { status: "manifest_invalid", records_state: "newer", issues: [{ severity: "info", code: "project.gitignore_outdated", message: "g" }, { severity: "info", code: "project.network_fs", message: "n" }] });
    expect(problemBanners(bad, "구성").map((b) => b.kind)).toEqual(["records", "manifest", "gitignore", "network"]);
    expect(MAX_VISIBLE_BANNERS).toBe(3);
  });
  it("모르는 status는 일반 경고 하나, 보관은 안내 한 줄", () => {
    const u = problemBanners(view("a", { status: "weird" as never, status_detail: "이유" }), "구성");
    expect(u).toHaveLength(1);
    expect(u[0]).toMatchObject({ tone: "warning", title: "프로젝트 상태: weird", body: "이유" });
    expect(problemBanners(view("a", {}, { archived: true }), "구성").map((b) => b.kind)).toEqual(["archived"]);
  });
  it("읽기 전용 폴더 배너는 ready + config_writable=false에서만", () => {
    expect(problemBanners(view("a", { config_writable: false }), "구성").map((b) => b.kind)).toEqual(["readonly"]);
    expect(problemBanners(view("a"), "구성")).toEqual([]);
  });
  it("설정 파일 경로·상대 시간·활동 합치기", () => {
    expect(manifestPath(view("a"))).toBe("/home/me/work/a/.cfg-dir/project.yaml");
    expect(manifestPath(view("a", { config_dir: null }))).toBeNull();
    const now = 1_000_000 * 1000;
    expect(relativeTime(now, 1_000_000 - 10)).toBe("방금");
    expect(relativeTime(now, 1_000_000 - 300)).toBe("5분 전");
    expect(relativeTime(now, 1_000_000 - 7200)).toBe("2시간 전");
    const rows = mergeActivity(
      [{ id: "c1", title: "논의", updated_at: 10, created_at: 1, graph_id: "g" }] as never,
      Array.from({ length: 9 }, (_, i) => ({ id: `r${i}`, graph_id: "g", status: "completed", created_at: 20 + i })) as never,
    );
    expect(rows).toHaveLength(8);
    expect(rows[0]?.id).toBe("r8");
    expect(rows.some((r) => r.origin === "chat")).toBe(false);
  });
});

describe("프로젝트 홈 /projects/:id", () => {
  it("정상: 이름·전체 경로·구성 표·최근 활동이 보이고 카드는 구성·최근 활동 둘(+머리)", async () => {
    mount([view("a")], "/projects/a", { listConversations: vi.fn(async () => [{ id: "c1", graph_id: "g", title: "결제 논의", created_at: 1, updated_at: 5 }]), listRuns: vi.fn(async () => []) });
    expect(await screen.findByRole("heading", { level: 1, name: /프로젝트 a/ })).toBeTruthy();
    expect(screen.getByTestId("project-path").textContent).toBe("/home/me/work/a");
    const config = screen.getByTestId("project-config-card");
    expect(await within(config).findByRole("link", { name: "기획 에이전트" })).toBeTruthy();
    expect((within(config).getByRole("link", { name: "기획 에이전트" }) as HTMLAnchorElement).getAttribute("href")).toContain("prj=a");
    const act3 = screen.getByTestId("project-activity-card");
    expect(await within(act3).findByText("결제 논의")).toBeTruthy();
    expect(screen.queryByTestId("project-banners")).toBeNull();
    // 채팅 시작은 활성
    expect(screen.getByRole("link", { name: "채팅 시작" }).getAttribute("aria-disabled")).toBeNull();
  });

  it("이 화면을 열면 현재 프로젝트가 되고, 없는 id는 안내 + 첫 프로젝트로", async () => {
    const { router } = mount([view("a"), view("b")], "/projects/ghost");
    expect(await screen.findByText("프로젝트를 찾을 수 없습니다")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "첫 프로젝트로" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/a"));
  });

  it("폴더 없음: danger 배너, 시작은 aria-disabled + 이유, 구성 표는 안내로 대체, [경로 다시 지정]이 대화상자를 연다", async () => {
    mount([view("a", { status: "folder_missing" })], "/projects/a");
    const banners = await screen.findByTestId("project-banners");
    expect(within(banners).getByRole("region", { name: "폴더를 찾을 수 없습니다" })).toBeTruthy();
    const start = screen.getByRole("link", { name: "채팅 시작" });
    expect(start.getAttribute("aria-disabled")).toBe("true");
    expect(start.getAttribute("title")).toBe("폴더를 쓸 수 없어 새 채팅을 시작할 수 없습니다");
    expect(screen.getByText("폴더를 찾을 수 없어 구성을 읽을 수 없습니다")).toBeTruthy();
    fireEvent.click(within(banners).getByRole("button", { name: "경로 다시 지정" }));
    expect(await screen.findByRole("dialog", { name: "경로 다시 지정 — 프로젝트 a" })).toBeTruthy();
  });

  it("읽기 전용 폴더: 칩 + 배너, 시작이 막히고 구성 가져오기도 막힌다", async () => {
    mount([view("a", { config_writable: false, records_writable: false })], "/projects/a");
    expect(await screen.findByRole("region", { name: "읽기 전용 폴더입니다" })).toBeTruthy();
    expect(screen.getAllByText("읽기 전용 폴더").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "채팅 시작" }).getAttribute("aria-disabled")).toBe("true");
    const imp = await screen.findByRole("button", { name: "공용에서 가져오기…" });
    expect(imp.getAttribute("aria-disabled")).toBe("true");
  });

  it("설정 파일 오류: 배너에 [설정 파일 다시 만들기…], 대화상자에서 이름·설명을 보내고 백업 경로를 토스트로 알린다", async () => {
    const reset = vi.fn(async () => ({ project: view("a"), backup_path: "/home/me/work/a/.cfg-dir/.state/backups/project-1.yaml" }));
    mount([view("a", { status: "manifest_invalid", status_detail: "줄 3" })], "/projects/a", { resetProjectManifest: reset });
    const banner = await screen.findByRole("region", { name: "프로젝트 설정 파일을 읽을 수 없습니다" });
    expect(banner.textContent).toContain("줄 3");
    fireEvent.click(within(banner).getByRole("button", { name: "설정 파일 다시 만들기…" }));
    const dlg = await screen.findByRole("dialog", { name: "설정 파일 다시 만들기" });
    expect(document.activeElement).toBe(within(dlg).getByRole("button", { name: "취소" }));
    fireEvent.change(within(dlg).getByLabelText(/^이름/), { target: { value: "새 이름" } });
    await act(async () => {
      fireEvent.click(within(dlg).getByRole("button", { name: "다시 만들기" }));
    });
    await waitFor(() => expect(reset).toHaveBeenCalledWith("a", { name: "새 이름" }));
    expect(await screen.findByText(/project-1\.yaml에 보관했습니다/)).toBeTruthy();
  });

  it("정상 폴더에는 설정 파일 다시 만들기 버튼이 없다", async () => {
    mount([view("a")], "/projects/a");
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByRole("button", { name: "설정 파일 다시 만들기…" })).toBeNull();
  });

  it(".gitignore 안내 줄의 [덧붙이기]가 서버 호출을 한다", async () => {
    const append = vi.fn(async () => view("a"));
    mount([view("a", { issues: [{ severity: "info", code: "project.gitignore_outdated", message: "g" }] })], "/projects/a", { appendProjectGitignore: append });
    fireEvent.click(await screen.findByRole("button", { name: ".gitignore 덧붙이기" }));
    await waitFor(() => expect(append).toHaveBeenCalledWith("a"));
  });

  it("보관된 프로젝트는 읽기 전용 안내와 [다시 등록]만 있다", async () => {
    const update = vi.fn(async () => ({ value: view("a"), version_hash: "h" }));
    mount([view("a", {}, { archived: true })], "/projects/a", { updateProject: update });
    expect(await screen.findByText("등록 해제된 프로젝트입니다. 기록은 읽기만 가능합니다.")).toBeTruthy();
    expect(screen.queryByTestId("project-config-card")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "다시 등록" }));
    await waitFor(() => expect(update).toHaveBeenCalledWith("a", { archived: false }));
  });

  it("목록 조회 실패는 0개로 단정하지 않고 [다시 시도]를 보인다", async () => {
    mount([], "/projects/a", { listProjects: vi.fn(async () => { throw new Error("boom"); }) });
    expect(await screen.findByText("프로젝트를 불러오지 못했습니다")).toBeTruthy();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeTruthy();
  });
});

describe("사이드바 항목 → 홈, 우클릭 메뉴", () => {
  it("항목을 누르면 현재 프로젝트가 바뀌고 홈(/projects/:id)으로 간다", async () => {
    const { router } = mount([view("a"), view("b")], "/chat");
    fireEvent.click(await findRow(/^프로젝트 b/));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/b"));
    expect(router.state.location.search).toContain("prj=b");
  });

  it("우클릭 메뉴: 홈 열기 / 경로 복사 / 경로 다시 지정 / 등록 해제, Esc로 닫으면 항목으로 돌아온다", async () => {
    mount([view("a")], "/chat");
    const row = await findRow(/^프로젝트 a/);
    fireEvent.contextMenu(row);
    const menu = await screen.findByRole("menu", { name: "프로젝트 a 메뉴" });
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["프로젝트 홈 열기", "경로 복사", "cd 명령 복사", "경로 다시 지정…", "등록 해제…"]);
    fireEvent.keyDown(menu, { key: "Escape" });
    expect(screen.queryByRole("menu", { name: "프로젝트 a 메뉴" })).toBeNull();
    expect(document.activeElement).toBe(row);
  });

  it("등록 해제는 확인 후 서버에서 보관(DELETE)하고 되돌리기를 준다. 기본 포커스는 [취소]", async () => {
    const unregister = vi.fn(async () => undefined);
    mount([view("a")], "/chat", { unregisterProject: unregister });
    fireEvent.contextMenu(await findRow(/^프로젝트 a/));
    fireEvent.click(await screen.findByRole("menuitem", { name: "등록 해제…" }));
    const dlg = await screen.findByRole("dialog", { name: "‘프로젝트 a’ 등록 해제" });
    expect(document.activeElement).toBe(within(dlg).getByRole("button", { name: "취소" }));
    expect(dlg.textContent).toContain("/home/me/work/a");
    await act(async () => {
      fireEvent.click(within(dlg).getByRole("button", { name: "등록 해제" }));
    });
    await waitFor(() => expect(unregister).toHaveBeenCalledWith("a", "h1"));
    expect(await screen.findByRole("button", { name: "되돌리기" })).toBeTruthy();
  });

  it("문제 상태 항목은 아이콘 색조와 sr-only 상태 글자를 가진다(사이드바는 경고를 더 하지 않는다)", async () => {
    mount([view("a", { status: "folder_missing" })], "/chat");
    const row = await findRow(/^프로젝트 a/);
    expect(row.getAttribute("data-tone")).toBe("danger");
    expect(row.textContent).toContain("폴더 없음");
  });
});

describe("폴더 추가 진입점", () => {
  it("[폴더 추가]는 새 대화상자를 열고 첫 포커스는 [폴더 선택…]이다", async () => {
    mount([], "/chat");
    await clickAddFolder();
    const dlg = await screen.findByRole("dialog", { name: "프로젝트 폴더 추가" });
    await waitFor(() => expect(document.activeElement).toBe(within(dlg).getByRole("button", { name: "폴더 선택…" })));
  });
});

describe("프로젝트 홈: 공용에서 가져오기·행 메뉴 (33o)", () => {
  it("[공용에서 가져오기…]가 복사 계획 대화상자를 고르기 단계로 열고, 구성 표 행 메뉴에 [공용에 저장…]이 있다", async () => {
    const { space } = mount([view("a")], "/projects/a", { listConversations: vi.fn(async () => []), listRuns: vi.fn(async () => []) });
    space.mockImplementation(((id: string | null) => createFakeRest({ listAgents: vi.fn(async () => (id === null ? [{ id: "lib-agent", name: "공용 에이전트" }] : [{ id: "pl", name: "기획 에이전트" }])) })) as never);
    const config = await screen.findByTestId("project-config-card");
    await within(config).findByRole("link", { name: "기획 에이전트" });
    fireEvent.click(within(config).getByRole("button", { name: "공용에서 가져오기…" }));
    const dialog = await screen.findByRole("dialog", { name: "공용에서 가져오기 — 프로젝트 a" });
    expect(await within(dialog).findByRole("checkbox", { name: "공용 에이전트" })).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "취소" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /공용에서 가져오기/ })).toBeNull());
    fireEvent.click(within(config).getByRole("button", { name: "기획 에이전트 작업" }));
    expect(await screen.findByRole("menuitem", { name: "공용에 저장…" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "삭제" })).toBeTruthy();
  });

  it("읽기 전용 폴더에서는 [공용에 저장…]을 제외한 쓰기 동작이 막히고(삭제 비활성), 가져오기 버튼은 aria-disabled", async () => {
    mount([view("a", { config_writable: false })], "/projects/a", { listConversations: vi.fn(async () => []), listRuns: vi.fn(async () => []) });
    const config = await screen.findByTestId("project-config-card");
    await within(config).findByRole("link", { name: "기획 에이전트" });
    expect(within(config).getByRole("button", { name: "공용에서 가져오기…" }).getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(within(config).getByRole("button", { name: "기획 에이전트 작업" }));
    expect((await screen.findByRole("menuitem", { name: "삭제" })).hasAttribute("disabled") || (await screen.findByRole("menuitem", { name: "삭제" })).getAttribute("aria-disabled") === "true").toBe(true);
  });

  it("[채팅 시작]은 새 대화 대화상자를 여는 주소(?new=1)로 간다", async () => {
    mount([view("a")], "/projects/a", { listConversations: vi.fn(async () => []), listRuns: vi.fn(async () => []) });
    const link = await screen.findByRole("link", { name: "채팅 시작" });
    expect(link.getAttribute("href")).toMatch(/new=1/);
    expect(link.getAttribute("href")).toMatch(/prj=a/);
  });
});

