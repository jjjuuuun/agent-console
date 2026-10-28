import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import type { ModuleInfo } from "@agent-console/contracts";
import type { MemoryEntry, MemoryEntrySummary, MemoryImportResult, MemoryScopeKindInfo, MemoryScopeSummary } from "@agent-console/contracts/memory";
import { makeEntries, sampleKinds, sampleScopes, SAMPLE_NOW } from "@agent-console/memory-view/testing";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { DEFAULT_ROUTES } from "../../shell/routeConfig";
import { MemoryPage } from "./MemoryPage";

beforeAll(preloadScreens, 120_000);
afterEach(cleanup);

const LONG = { timeout: 15_000 };
// 범위 종류·이름은 모두 임의 값(`memory-view/testing`의 표본)이다. 화면 코드는 이 이름을 모른다.
const mod = (roles: string[]): ModuleInfo => ({ id: "m-any", kind: "k", version: "0.0.1", status: "active", web_roles: roles });
const MEMORY_ROLE_MODULES = async () => [mod(["memory", "projects"])];

const full = (e: MemoryEntrySummary, content = `본문 ${e.key}`): MemoryEntry => ({ ...e, content }) as MemoryEntry;

interface Fixture {
  kinds?: MemoryScopeKindInfo[];
  scopes?: MemoryScopeSummary[];
  entries?: MemoryEntrySummary[];
  rest?: Record<string, unknown>;
  projects?: { id: string; name: string }[];
}

function setup(path: string, f: Fixture = {}) {
  const entries = f.entries ?? makeEntries(3);
  const { clients, ws, rest } = createFakeClients(
    {
      listModules: vi.fn(MEMORY_ROLE_MODULES),
      listMemoryScopeKinds: vi.fn(async () => ({ kinds: f.kinds ?? sampleKinds(), include_defaults: false })),
      listMemoryScopes: vi.fn(async () => f.scopes ?? sampleScopes()),
      listMemoryEntries: vi.fn(async () => ({ items: entries, next_cursor: null, total: entries.length })),
      listMemoryTags: vi.fn(async () => ({ tags: [{ tag: "t1", entries: 4 }, { tag: "t2", entries: 2 }], truncated: false })),
      getMemoryEntry: vi.fn(async (id: string) => {
        const e = entries.find((x) => x.id === id);
        if (e === undefined) throw new ApiError(404, { code: "not_found", message: "없음" });
        return full(e);
      }),
      getModuleOptions: vi.fn(async () => ({ module_id: "m-any", values: { max_entry_bytes: 65_536 } })),
      ...f.rest,
    },
    { listProjects: vi.fn(async () => (f.projects ?? []).map((p) => ({ ...p }))) },
  );
  const view = mountApp(clients, path);
  return { ...view, clients, ws, rest };
}

const grid = () => screen.findByRole("grid", { name: "메모리 항목 표" }, LONG);
const rowNames = () => screen.getAllByRole("row").slice(1).map((r) => r.getAttribute("aria-label") ?? "");

describe("메모리 화면: 역할·배치", () => {
  it("역할이 없으면 사이드바 항목이 없고 주소로 들어가면 꺼진 기능 안내가 나온다. 있으면 항목과 화면이 있다", async () => {
    const off = createFakeClients({ listModules: vi.fn(async () => [{ ...mod(["memory"]), status: "disabled" }]) });
    mountApp(off.clients, "/memory");
    expect(await screen.findByRole("heading", { name: "이 기능은 꺼져 있습니다", level: 1 }, LONG)).toBeTruthy();
    expect(within(screen.getByRole("navigation", { name: "주 메뉴" })).queryByRole("link", { name: "메모리" })).toBeNull();
    expect(off.rest.listMemoryEntries).not.toHaveBeenCalled();
    cleanup();
    setup("/memory");
    await grid();
    expect(within(screen.getByRole("navigation", { name: "주 메뉴" })).getByRole("link", { name: "메모리" })).toBeTruthy();
  });

  it("기본 라우트 데이터에 메모리가 묶음 '실행'의 채팅·실행 기록 다음에 있고 g m 이다", () => {
    const run = DEFAULT_ROUTES.filter((r) => r.group === "run").map((r) => r.id);
    expect(run).toEqual(["chat", "runs", "memory"]);
    expect(DEFAULT_ROUTES.find((r) => r.id === "memory")).toMatchObject({ requires: ["memory"], gotoKey: "m", path: "/memory" });
  });

  it("3칸: 범위 나무는 서버 데이터(임의 이름)로 그려지고, 범위를 고르면 주소와 목록 질의가 따라간다", async () => {
    const { router, rest } = setup("/memory");
    const tree = await screen.findByRole("tree", { name: "메모리 범위 나무" }, LONG);
    expect(await within(tree).findByText("장부", {}, LONG)).toBeTruthy();
    expect(within(tree).getByText("책상")).toBeTruthy();
    await grid();
    expect(rest.listMemoryEntries).toHaveBeenCalledWith(expect.not.objectContaining({ scopes: expect.anything() }));
    fireEvent.click(within(tree).getByRole("treeitem", { name: "g1, 항목 60개" }));
    await waitFor(() => expect(router.state.location.search).toContain("scope=desk%3Ag1"), LONG);
    await waitFor(() => expect(rest.listMemoryEntries).toHaveBeenCalledWith(expect.objectContaining({ scopes: [{ kind: "desk", id: "g1" }] })), LONG);
  });

  it("본문 폭 1180 미만이면 2칸: 나무 칸이 없고 [범위 ▾] 팝오버가 도구줄 맨 앞에 있다", async () => {
    const { clients } = createFakeClients({
      listModules: vi.fn(MEMORY_ROLE_MODULES),
      listMemoryScopeKinds: vi.fn(async () => ({ kinds: sampleKinds() })),
      listMemoryScopes: vi.fn(async () => sampleScopes()),
      listMemoryEntries: vi.fn(async () => ({ items: makeEntries(2), next_cursor: null, total: 2 })),
    });
    const pages = { memory: () => [{ index: true, element: <MemoryPage layoutWidth={976} /> }] };
    const router = createMemoryRouter(buildAppRoutes({ platform: "other", pages: { ...(await import("../../shell/routes")).DEFAULT_PAGES, ...pages } }), { initialEntries: ["/memory"] });
    render(<AppRoot createClients={async () => clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
    await grid();
    expect(screen.queryByRole("tree")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /모든 범위/ }));
    expect(await screen.findByRole("tree", { name: "메모리 범위 나무" })).toBeTruthy();
  });
});

describe("메모리 화면: 목록·검색·정렬", () => {
  it("열 머리를 누르면 서버 정렬을 요청하고(desc→asc→기본), 클라이언트에서 다시 정렬하지 않는다", async () => {
    const { rest, router } = setup("/memory");
    await grid();
    const before = rowNames();
    fireEvent.click(screen.getByRole("button", { name: "키" }));
    await waitFor(() => expect(rest.listMemoryEntries).toHaveBeenCalledWith(expect.objectContaining({ sort: "key", order: "desc" })), LONG);
    expect(router.state.location.search).toContain("sort=key");
    expect(rowNames()).toEqual(before);
    fireEvent.click(screen.getByRole("button", { name: /^키/ }));
    await waitFor(() => expect(rest.listMemoryEntries).toHaveBeenCalledWith(expect.objectContaining({ sort: "key", order: "asc" })), LONG);
    fireEvent.click(screen.getByRole("button", { name: /^키/ }));
    await waitFor(() => expect(router.state.location.search).not.toContain("sort="), LONG);
  });

  it("검색어는 입력이 멈춘 뒤에 질의하고 주소에 반영한다. 한글 조합 중에는 질의하지 않고 조합이 끝나면 바로 질의한다", async () => {
    const { rest, router } = setup("/memory");
    await grid();
    const box = screen.getByRole("searchbox", { name: "메모리 검색" });
    fireEvent.compositionStart(box);
    fireEvent.change(box, { target: { value: "ㄱ" } });
    await new Promise((r) => setTimeout(r, 450));
    expect(rest.listMemoryEntries).not.toHaveBeenCalledWith(expect.objectContaining({ q: "ㄱ" }));
    fireEvent.compositionEnd(box, { target: { value: "가나" } });
    await waitFor(() => expect(rest.listMemoryEntries).toHaveBeenCalledWith(expect.objectContaining({ q: "가나" })), LONG);
    expect(router.state.location.search).toContain("q=");
    fireEvent.change(box, { target: { value: "x" } });
    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() => expect(rest.listMemoryEntries).toHaveBeenCalledWith(expect.objectContaining({ q: "x" })), LONG);
  });

  it("태그 목록은 서버 태그 질의(현재 범위·보관 포함 인자)로 채워지고 고르면 칩이 생긴다", async () => {
    const { rest, router } = setup("/memory?scope=desk%3Ag1&archived=1");
    await grid();
    fireEvent.click(screen.getByRole("button", { name: /^태그/ }));
    const list = await screen.findByRole("list", { name: "태그 목록" }, LONG);
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["t1 4", "t2 2"]);
    expect(rest.listMemoryTags).toHaveBeenCalledWith({ scopes: [{ kind: "desk", id: "g1" }], includeArchived: true });
    fireEvent.click(within(list).getByRole("checkbox", { name: /t2/ }));
    await waitFor(() => expect(router.state.location.search).toContain("tag=t2"), LONG);
    expect(within(await screen.findByRole("group", { name: "활성 필터" })).getByRole("button", { name: /태그: t2/ })).toBeTruthy();
  });
});

describe("메모리 화면: 상태", () => {
  it("빈 workspace: 이점 3줄과 가져오기가 있고 범위 이름은 없다(머리의 [새 항목]만 새로 만들기)", async () => {
    setup("/memory", { scopes: [], entries: [] });
    expect(await screen.findByRole("heading", { name: "아직 저장된 메모리가 없습니다" }, LONG)).toBeTruthy();
    expect(screen.getAllByRole("listitem").filter((li) => li.closest(".mem-benefits"))).toHaveLength(3);
    expect(screen.getAllByRole("button", { name: "새 항목" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "가져오기…" }).length).toBeGreaterThan(0);
  });

  it("켜진 범위 종류가 0개면 안내와 [설정 열기]", async () => {
    setup("/memory", { kinds: [{ ...sampleKinds()[0]!, disabled: true }], scopes: [], entries: [] });
    expect(await screen.findByRole("heading", { name: "범위 종류가 없습니다" }, LONG)).toBeTruthy();
    expect(screen.getByRole("button", { name: "설정 열기" })).toBeTruthy();
  });

  it("필터 결과가 0건이면 [필터 지우기]", async () => {
    const { router } = setup("/memory?tag=zz", { entries: [] });
    expect(await screen.findByText("조건에 맞는 항목이 없습니다.", {}, LONG)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "필터 지우기" }));
    await waitFor(() => expect(router.state.location.search).not.toContain("tag="), LONG);
  });

  it("목록 요청이 실패하면 오류 블록과 [다시 시도], 나무는 정상", async () => {
    let fail = true;
    setup("/memory", { rest: { listMemoryEntries: vi.fn(async () => (fail ? Promise.reject(new ApiError(500, { code: "x", message: "서버 오류입니다" })) : { items: [], next_cursor: null })) } });
    expect(await screen.findByRole("heading", { name: "메모리 목록을 불러오지 못했습니다" }, LONG)).toBeTruthy();
    expect(screen.getByRole("tree", { name: "메모리 범위 나무" })).toBeTruthy();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "메모리 목록을 불러오지 못했습니다" })).toBeNull(), LONG);
  });

  it("서버 경고(저장소 임시 모드)는 접을 수 없는 띠와 [내보내기]로 알린다", async () => {
    setup("/memory", {
      rest: { getServerInfo: vi.fn(async () => ({ server_version: "1", contracts_version: "1", plugins: [], attributes: {}, warnings: [{ code: "memory.storage_memory", message: "원문", severity: "warning" }] })) },
    });
    expect(await screen.findByText(/저장 파일 없이 임시로 동작합니다/, {}, LONG)).toBeTruthy();
  });
});

describe("메모리 화면: 프로젝트 전환기", () => {
  it("프로젝트를 고르면 그 프로젝트·보이는 팀 구성의 범위만 나무에 남고 숨긴 수가 나온다", async () => {
    setup("/memory?prj=P1", {
      projects: [{ id: "P1", name: "프로젝트 하나" }, { id: "P2", name: "프로젝트 둘" }],
      rest: { listGraphs: vi.fn(async () => [{ id: "g1", name: "팀 하나", project: "P1" }, { id: "g2", name: "팀 둘", project: "P2" }]), listModules: vi.fn(async () => [mod(["memory", "projects", "definitions:graph"])]) },
    });
    const tree = await screen.findByRole("tree", { name: "메모리 범위 나무" }, LONG);
    expect(await screen.findByText("다른 프로젝트 범위 6개 숨김", {}, LONG)).toBeTruthy();
    expect(within(tree).getAllByText("팀 하나").length).toBeGreaterThan(0);
    expect(within(tree).queryAllByText("팀 둘")).toHaveLength(0);
    const chips = screen.getByRole("group", { name: "활성 필터" });
    expect(within(chips).getByRole("button", { name: /프로젝트: 프로젝트 하나/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "모두 보기" }));
    await waitFor(() => expect(screen.queryByText(/다른 프로젝트 범위/)).toBeNull(), LONG);
    expect(within(tree).getAllByText("팀 둘").length).toBeGreaterThan(0);
    expect(within(screen.getByRole("group", { name: "활성 필터" })).getByRole("button", { name: /프로젝트 필터 해제됨/ })).toBeTruthy();
  });

  it("프로젝트 기능이 없으면 거르지 않는다", async () => {
    setup("/memory", { rest: { listModules: vi.fn(async () => [mod(["memory"])]) } });
    const tree = await screen.findByRole("tree", { name: "메모리 범위 나무" }, LONG);
    expect(await within(tree).findByText("서랍", {}, LONG)).toBeTruthy();
    expect(screen.queryByText(/다른 프로젝트 범위/)).toBeNull();
  });
});

describe("메모리 화면: 상세·저장·충돌", () => {
  it("행을 고르면 상세가 열리고 주소에 entry가 남는다. 저장은 If-Match(열었을 때 버전)로 보낸다", async () => {
    const entries = makeEntries(3);
    const updated = { ...full(entries[1]!), tags: ["새태그"], version: entries[1]!.version + 1 } as MemoryEntry;
    const { router, rest } = setup("/memory", { entries, rest: { updateMemoryEntry: vi.fn(async () => updated) } });
    await grid();
    fireEvent.click(screen.getByRole("row", { name: /entry-1,/ }));
    await waitFor(() => expect(router.state.location.search).toContain("entry=e1"), LONG);
    expect(await screen.findByRole("heading", { name: "a/b/entry-1" }, LONG)).toBeTruthy();
    fireEvent.click(screen.getByText("정보"));
    const tagInput = await screen.findByRole("textbox", { name: "태그 추가" }, LONG);
    fireEvent.change(tagInput, { target: { value: "새태그" } });
    fireEvent.keyDown(tagInput, { key: "Enter" });
    expect((await screen.findAllByText("저장 안 됨")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(rest.updateMemoryEntry).toHaveBeenCalledWith("e1", { tags: ["새태그"] }, entries[1]!.version), LONG);
    await waitFor(() => expect(screen.getAllByText("저장됨").length).toBeGreaterThan(0), LONG);
  });

  it("버전 충돌(412)이면 서버 최신 본문과 비교하는 대화상자가 뜨고, [내 변경을 저장]은 서버 최신 버전으로 다시 보낸다", async () => {
    const entries = makeEntries(2);
    const base = entries[1]!;
    const newer = { ...full(base, "서버가 먼저 바꾼 본문"), version: base.version + 2, updated_by: { kind: "user", label: "다른 사람" } } as MemoryEntry;
    let calls = 0;
    const update = vi.fn(async (_id: string, _body: unknown, version: number) => {
      calls += 1;
      if (calls === 1) throw new ApiError(412, { code: "version_conflict", message: "달라짐", details: { current_version: newer.version } });
      return { ...newer, version: version + 1, tags: ["내태그"] } as MemoryEntry;
    });
    let served = false;
    setup("/memory?entry=e1", {
      entries,
      rest: {
        updateMemoryEntry: update,
        getMemoryEntry: vi.fn(async (id: string) => (id === "e1" && served ? newer : full(entries.find((x) => x.id === id)!))),
      },
    });
    fireEvent.click(await screen.findByText("정보", {}, LONG));
    const tagInput = await screen.findByRole("textbox", { name: "태그 추가" }, LONG);
    fireEvent.change(tagInput, { target: { value: "내태그" } });
    fireEvent.keyDown(tagInput, { key: "Enter" });
    served = true;
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    const dialog = await screen.findByRole("dialog", { name: "다른 쪽이 먼저 고쳤습니다" }, LONG);
    expect(dialog.textContent).toContain(`서버 v${newer.version}`);
    expect(dialog.textContent).toContain("기록에 남아 언제든 되돌릴 수 있습니다");
    fireEvent.click(within(dialog).getByRole("button", { name: `내 변경을 v${newer.version + 1}으로 저장` }));
    await waitFor(() => expect(update).toHaveBeenLastCalledWith("e1", { tags: ["내태그"] }, newer.version), LONG);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "다른 쪽이 먼저 고쳤습니다" })).toBeNull(), LONG);
  });

  it("비밀 거부(422)는 위치만 알리고 값은 어디에도 없다. 그래도 저장하는 버튼이 없고 편집 내용은 남는다", async () => {
    const entries = makeEntries(2);
    const secret = "SUPER-SECRET-VALUE-123";
    const update = vi.fn(async () => {
      throw new ApiError(422, { code: "memory.secret_rejected", message: `거부: ${secret}`, details: { field: "tags", rules: ["rule-aws"] } });
    });
    setup("/memory?entry=e1", { entries, rest: { updateMemoryEntry: update } });
    fireEvent.click(await screen.findByText("정보", {}, LONG));
    const tagInput = await screen.findByRole("textbox", { name: "태그 추가" }, LONG);
    fireEvent.change(tagInput, { target: { value: secret } });
    fireEvent.keyDown(tagInput, { key: "Enter" });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    const alert = await screen.findByText("비밀 값으로 보이는 내용이 있어 저장하지 않았습니다.", {}, LONG);
    const band = alert.closest("[role='alert']") as HTMLElement;
    expect(band.textContent).toContain("태그에 비밀로 보이는 값이 있습니다");
    expect(document.body.textContent).not.toContain("rule-aws");
    expect(band.textContent).not.toContain(secret);
    expect(screen.queryByRole("button", { name: /그래도|가리고/ })).toBeNull();
    expect(screen.getAllByText("저장 실패").length).toBeGreaterThan(0);
    expect(screen.getByText(secret)).toBeTruthy(); // 입력한 태그 칩은 그대로 남는다(버리지 않는다)
  });

  it("저장하지 않은 변경이 있으면 다른 행을 고를 때 확인 창이 뜨고 기본 포커스는 [취소]다", async () => {
    const entries = makeEntries(3);
    const { router } = setup("/memory?entry=e1", { entries });
    fireEvent.click(await screen.findByText("정보", {}, LONG));
    const tagInput = await screen.findByRole("textbox", { name: "태그 추가" }, LONG);
    fireEvent.change(tagInput, { target: { value: "임시" } });
    fireEvent.keyDown(tagInput, { key: "Enter" });
    fireEvent.click(screen.getByRole("row", { name: /entry-2,/ }));
    const dialog = await screen.findByRole("dialog", { name: "저장하지 않은 변경이 있습니다." });
    expect(document.activeElement?.textContent).toBe("취소");
    expect(router.state.location.search).toContain("entry=e1");
    fireEvent.click(within(dialog).getByRole("button", { name: "버리고 이동" }));
    await waitFor(() => expect(router.state.location.search).toContain("entry=e2"), LONG);
  });

  it("지운 항목은 읽기 전용이고 [복원]이 있다", async () => {
    const entries = makeEntries(2);
    const deleted = { ...full(entries[1]!), deleted_at: SAMPLE_NOW - 5 } as MemoryEntry;
    const restore = vi.fn(async () => ({ ...deleted, deleted_at: null }) as MemoryEntry);
    setup("/memory?entry=e1&deleted=1", { entries: [entries[0]!, { ...entries[1]!, deleted_at: SAMPLE_NOW - 5 }], rest: { getMemoryEntry: vi.fn(async () => deleted), restoreMemoryEntry: restore } });
    expect(await screen.findByText("지운 항목입니다.", {}, LONG)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "복원" }));
    await waitFor(() => expect(restore).toHaveBeenCalledWith("e1"), LONG);
  });

  it("항목이 없으면(404) 찾을 수 없다는 안내와 [목록으로]", async () => {
    setup("/memory?entry=zzz");
    expect(await screen.findByRole("heading", { name: "항목을 찾을 수 없습니다" }, LONG)).toBeTruthy();
  });
});

describe("메모리 화면: 완전 삭제·가져오기·내보내기", () => {
  it("완전 삭제는 체크를 해야 켜지고 기본 포커스는 [취소], 확인하면 purge(204)를 호출한다", async () => {
    const entries = makeEntries(3);
    const purge = vi.fn(async () => undefined);
    const { router } = setup("/memory?entry=e1", { entries, rest: { purgeMemoryEntry: purge } });
    await grid();
    const row = screen.getByRole("row", { name: /entry-1,/ });
    row.focus();
    fireEvent.keyDown(row, { key: "Delete", shiftKey: true });
    const dialog = await screen.findByRole("dialog", { name: "완전 삭제" });
    expect(document.activeElement?.textContent).toBe("취소");
    const submit = within(dialog).getByRole("button", { name: "완전 삭제" });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "되돌릴 수 없음을 확인했습니다" }));
    fireEvent.click(submit);
    await waitFor(() => expect(purge).toHaveBeenCalledWith("e1"), LONG);
    await waitFor(() => expect(router.state.location.search).not.toContain("entry=e1"), LONG);
  });

  it("가져오기: 미리보기는 dry_run으로 수만 세고 쓰지 않으며, 정책을 바꾸면 흐려진다. 가져오기는 zip 바이트를 그대로 보낸다", async () => {
    const preview: MemoryImportResult = { dry_run: true, created: 4, overwritten: 2, renamed: 0, skipped: 1, errors: [{ path: "a/b.md", code: "memory.secret_rejected", message: "SECRET-BODY-TEXT" }] };
    const done: MemoryImportResult = { dry_run: false, created: 4, overwritten: 2, renamed: 0, skipped: 1, errors: [preview.errors![0]!] };
    const importMemory = vi.fn(async (_b: Uint8Array, o?: { dryRun?: boolean }) => (o?.dryRun === true ? preview : done));
    setup("/memory", { rest: { importMemory } });
    await grid();
    fireEvent.click(screen.getByRole("button", { name: "가져오기…" }));
    const dialog = await screen.findByRole("dialog", { name: "메모리 가져오기" });
    const input = dialog.querySelector("input[type=file]") as HTMLInputElement;
    const file = new File([new Uint8Array([80, 75, 3, 4])], "memory.zip", { type: "application/zip" });
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(await within(dialog).findByRole("button", { name: "미리보기" }));
    await within(dialog).findByText("만들어질 항목 4", {}, LONG);
    expect(importMemory).toHaveBeenCalledWith(expect.any(Uint8Array), { policy: "skip", dryRun: true });
    expect(within(dialog).getByText("기존 본문 2개가 바뀝니다")).toBeTruthy();
    expect(dialog.textContent).not.toContain("SECRET-BODY-TEXT");
    expect(dialog.textContent).toContain("비밀로 보이는 내용이 있어 건너뜀");
    fireEvent.click(within(dialog).getByRole("radio", { name: /덮어쓰기/ }));
    expect(within(dialog).getByText("정책이 바뀌었습니다. 다시 미리보기하세요")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "가져오기" }));
    await within(dialog).findByText("일부를 가져오지 못했습니다", {}, LONG);
    expect(importMemory).toHaveBeenLastCalledWith(expect.any(Uint8Array), { policy: "overwrite", dryRun: false });
    expect(within(dialog).getByText("비밀 거부 1")).toBeTruthy();
  });

  it("내보내기: 범위를 고르지 않으면 [현재 범위]가 꺼져 있고, 항목이 0개면 메뉴 자체가 꺼진다", async () => {
    setup("/memory");
    await grid();
    fireEvent.click(screen.getByRole("button", { name: /^내보내기/ }));
    const menu = await screen.findByRole("menu", { name: "내보내기 메뉴" });
    expect((within(menu).getByRole("menuitem", { name: "현재 범위 내보내기" }) as HTMLButtonElement).disabled).toBe(true);
    expect((within(menu).getByRole("menuitem", { name: "모든 범위 내보내기" }) as HTMLButtonElement).disabled).toBe(false);
    cleanup();
    setup("/memory", { scopes: [], entries: [] });
    await screen.findByRole("heading", { name: "아직 저장된 메모리가 없습니다" }, LONG);
    expect((screen.getByRole("button", { name: /^내보내기/ }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("메모리 화면: 실시간", () => {
  it("memory.changed를 받으면 500ms 안의 알림을 모아 목록을 한 번 다시 읽는다", async () => {
    const { ws, rest } = setup("/memory");
    await grid();
    const calls = () => (rest.listMemoryEntries as ReturnType<typeof vi.fn>).mock.calls.length;
    const first = calls();
    const change = { scope: { kind: "desk", id: "g1" }, key: "k", entry_id: "e1", version: 3, op: "update", author_kind: "agent" } as const;
    act(() => {
      ws.emitMemory(change);
      ws.emitMemory({ ...change, entry_id: "e2" });
      ws.emitMemory({ ...change, entry_id: "e3" });
    });
    await waitFor(() => expect(calls()).toBeGreaterThan(first), LONG);
    await new Promise((r) => setTimeout(r, 700));
    expect(calls()).toBe(first + 1);
  });

  it("검색어가 있으면 행을 움직이지 않고 '새 변경' 칩만 띄운다. 칩을 누르면 다시 읽는다", async () => {
    const { ws, rest } = setup("/memory?q=abc");
    await grid();
    const first = (rest.listMemoryEntries as ReturnType<typeof vi.fn>).mock.calls.length;
    act(() => ws.emitMemory({ scope: { kind: "desk", id: "g1" }, key: "k", entry_id: "e9", version: 1, op: "create", author_kind: "agent" }));
    const chip = await screen.findByRole("button", { name: /새 변경 1건/ }, LONG);
    await new Promise((r) => setTimeout(r, 200));
    expect((rest.listMemoryEntries as ReturnType<typeof vi.fn>).mock.calls.length).toBe(first);
    fireEvent.click(chip);
    await waitFor(() => expect((rest.listMemoryEntries as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(first), LONG);
    expect(screen.queryByRole("button", { name: /새 변경/ })).toBeNull();
  });

  it("편집 중인 항목이 서버에서 바뀌면 덮어쓰지 않고 '새 버전 있음' 띠를 띄운다", async () => {
    const entries = makeEntries(2);
    const base = entries[1]!;
    let latest = full(base);
    const { ws } = setup("/memory?entry=e1", { entries, rest: { getMemoryEntry: vi.fn(async () => latest) } });
    fireEvent.click(await screen.findByText("정보", {}, LONG));
    const tagInput = await screen.findByRole("textbox", { name: "태그 추가" }, LONG);
    fireEvent.change(tagInput, { target: { value: "내것" } });
    fireEvent.keyDown(tagInput, { key: "Enter" });
    latest = { ...latest, version: base.version + 1, updated_by: { kind: "user", label: "다른 사람" } } as MemoryEntry;
    act(() => ws.emitMemory({ scope: base.scope, key: base.key, entry_id: "e1", version: base.version + 1, op: "update", author_kind: "user" }));
    expect(await screen.findByText(new RegExp(`다른 곳에서 v${base.version + 1}으로 바뀌었습니다`), {}, LONG)).toBeTruthy();
    expect(screen.getByText("내것")).toBeTruthy();
    expect(screen.getByRole("button", { name: "비교" })).toBeTruthy();
  });
});
