import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, type SddClient } from "@agent-console/api-client";
import type { ModuleInfo, Project, ProjectView } from "@agent-console/contracts";
import type { EffectiveSyntax, ParsedTask, SddInfo, SpecView, TaskAction, TraceMatrix } from "@agent-console/contracts/sdd";
import { createFakeClients } from "../../testing/fakes";
import { createSafeStorage, type SafeStorage } from "../../app/storage";
import { mountApp } from "../../testing/screenHarness";

// 계획 그래프(@xyflow/react)는 레이아웃 API가 필요해 자리표시로 바꾼다. 글 목록(PlanBundles)은 진짜를 쓴다.
vi.mock("@agent-console/sdd-view", async (orig) => ({
  ...(await orig<typeof import("@agent-console/sdd-view")>()),
  PlanGraph: ({ tasks }: { tasks: readonly ParsedTask[] }) => <div data-testid="plan-graph-stub">{tasks.length}</div>,
}));

afterEach(cleanup);

const LONG = { timeout: 15_000 };
// 상태·문서·연동·프로필 이름은 모두 임의 값이다. 화면 코드는 이 이름을 모른다.
const mod = (roles: string[], extra: Partial<ModuleInfo> = {}): ModuleInfo => ({ id: "m-any", kind: "k", version: "0.0.1", status: "active", web_roles: roles, ...extra });
const project = (id: string): Project => ({ id, name: id.toUpperCase(), folder: `/w/${id}` }) as Project;
const projectView = (p: Project, over: Partial<ProjectView> = {}): ProjectView => ({ project: p, status: "ready", config_writable: true, kinds: [], records_writable: true, config_dir: ".cfg", ...over }) as ProjectView;

const INFO: SddInfo = { spec_root: ".cfg/specs", limits: { max_bulk_start: 10 }, capabilities: { runs: true, templates: true, import_export: true, verification: true, automation: true }, writable: true } as SddInfo;
const STATUSES = [
  { id: "s-open", label: "열림", tone: "neutral" },
  { id: "s-end", label: "끝남", tone: "success", done: true },
];
const task = (key: string, status = "s-open", extra: Partial<ParsedTask> = {}): ParsedTask => ({ key, id: key, title: `작업 ${key}`, status, document: "d-tasks", line: 4, line_hash: `h-${key}`, ready: true, ...extra });
const specView = (over: Partial<SpecView> = {}): SpecView => ({
  spec: { kind: "k-x", id: "sp1", name: "결제", documents: [{ id: "d-req", title: "요구", file: "req.md", roles: ["requirements"] }, { id: "d-tasks", title: "작업표", file: "tasks.md", roles: ["tasks"] }], rules: {} },
  index: { tasks: [task("T1"), task("T2", "s-open", { ready: false, dependencies: ["T1"] }), task("T3", "s-end")], stages: [] },
  version_hash: "v1",
  directory: ".cfg/specs/sp1",
  task_statuses: STATUSES,
  document_states: [],
  issues: [],
  ...over,
});
const SYNTAX: EffectiveSyntax = { empty: false, statuses: STATUSES, sources: {} } as EffectiveSyntax;
const ACTION_A: TaskAction = { integration: "i-x", id: "a-1", label: "임의 프로필 실행" };
const ACTION_B: TaskAction = { integration: "i-x", id: "a-2", label: "막힌 프로필", disabled: { severity: "error", code: "g.code", message: "서버가 준 이유" } };

interface Fixture {
  info?: SddInfo;
  view?: SpecView;
  projects?: ProjectView[];
  sdd?: Record<string, unknown>;
}

function setup(path: string, f: Fixture = {}, storage?: SafeStorage) {
  const view = f.view ?? specView();
  const projects = f.projects ?? [projectView(project("p1"))];
  const { clients, sddClient, rest } = createFakeClients(
    { listModules: vi.fn(async () => [mod(["sdd", "projects", "settings", "runs"])]), listProjects: vi.fn(async () => projects) },
    {},
    {
      getSddInfo: vi.fn(async () => f.info ?? INFO),
      listSpecs: vi.fn(async () => []),
      listSpecTemplates: vi.fn(async () => []),
      getSpec: vi.fn(async () => ({ value: view, version_hash: view.version_hash })),
      getSpecSyntax: vi.fn(async () => SYNTAX),
      listSpecTasks: vi.fn(async () => view.index?.tasks ?? []),
      listTaskActions: vi.fn(async () => [ACTION_A, ACTION_B]),
      ...f.sdd,
    },
  );
  const mounted = mountApp(clients, path, storage === undefined ? {} : { storage });
  return { ...mounted, sdd: sddClient as unknown as { [K in keyof SddClient]: ReturnType<typeof vi.fn> }, rest };
}

const openMenu = async (key = "T1") => {
  fireEvent.click(await screen.findByRole("button", { name: `${key} 실행` }, LONG));
  return screen.findByTestId("sdd-actions-menu", {}, LONG);
};

describe("작업 탭: 실행 동작", () => {
  it("실행 연동이 꺼지면 [실행 ▾]·[준비된 작업 시작…]·실행 열이 없고 꺼짐 안내가 있다. 동작 목록도 묻지 않는다", async () => {
    const info = { ...INFO, capabilities: { ...INFO.capabilities, runs: false } } as SddInfo;
    const { sdd } = setup("/specs/sp1?prj=p1&tab=tasks", { info });
    expect(await screen.findByTestId("sdd-runs-off", {}, LONG)).toBeTruthy();
    await screen.findByRole("button", { name: /^작업 T1의 상태 바꾸기/ }, LONG);
    expect(screen.queryByRole("button", { name: /T1 실행/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "준비된 작업 시작…" })).toBeNull();
    expect(sdd.listTaskActions).not.toHaveBeenCalled();
  });

  it("메뉴를 열 때 동작 목록을 읽고 라벨은 서버 값 그대로이며, 막힌 동작은 aria-disabled + 이유가 보인다", async () => {
    const { sdd } = setup("/specs/sp1?prj=p1&tab=tasks");
    const menu = await openMenu();
    expect(sdd.listTaskActions).toHaveBeenCalledWith("sp1", "T1");
    const ok = await within(menu).findByRole("menuitem", { name: /임의 프로필 실행/ }, LONG);
    const blocked = within(menu).getByRole("menuitem", { name: /막힌 프로필/ });
    expect(ok.getAttribute("aria-disabled")).toBeNull();
    expect(blocked.getAttribute("aria-disabled")).toBe("true");
    expect(within(menu).getByText("서버가 준 이유")).toBeTruthy();
  });

  it("동작이 0개면 안내 문구가 나온다", async () => {
    setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { listTaskActions: vi.fn(async () => []) } });
    const menu = await openMenu();
    expect(await within(menu).findByText("이 작업에서 할 수 있는 동작이 없습니다", {}, LONG)).toBeTruthy();
  });

  it("동작을 고르면 연동·동작 id로 실행하고, 시작하면 토스트에 [열기]가 있다", async () => {
    const run = vi.fn(async () => ({ task_key: "T1", status: "started", run_id: "r-9" }));
    const { sdd, router } = setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { runTaskAction: run } });
    const menu = await openMenu();
    fireEvent.click(await within(menu).findByRole("menuitem", { name: /임의 프로필 실행/ }, LONG));
    await waitFor(() => expect(sdd.runTaskAction).toHaveBeenCalledWith("sp1", "T1", "i-x", "a-1"), LONG);
    expect(await screen.findByText("‘작업 T1’ 실행을 시작했습니다", {}, LONG)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "열기" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/runs/r-9"), LONG);
  });

  it("관문에 막히면(422 gate_blocked) 서버 문구가 관문 안내로 나오고 [문서 열기]가 문서 탭으로 간다", async () => {
    const blocked = new ApiError(422, { code: "sdd.gate_blocked", message: "x", details: { gate_id: "g1", message: "승인 문서가 먼저입니다", document_ids: ["d-req"] } });
    const { router } = setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { runTaskAction: vi.fn(async () => { throw blocked; }) } });
    const menu = await openMenu();
    fireEvent.click(await within(menu).findByRole("menuitem", { name: /임의 프로필 실행/ }, LONG));
    const alert = await screen.findByText("승인 문서가 먼저입니다", {}, LONG);
    expect(alert).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /요구/ }));
    await waitFor(() => expect(router.state.location.search).toContain("doc=d-req"), LONG);
  });

  it("200 응답의 blocked 결과도 관문 안내로 보인다", async () => {
    const run = vi.fn(async () => ({ task_key: "T1", status: "blocked", issue: { severity: "error", code: "sdd.gate_blocked", message: "결과로 온 관문 문구", details: { gate_id: "g2" } } }));
    setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { runTaskAction: run } });
    const menu = await openMenu();
    fireEvent.click(await within(menu).findByRole("menuitem", { name: /임의 프로필 실행/ }, LONG));
    expect(await screen.findByText("결과로 온 관문 문구", {}, LONG)).toBeTruthy();
  });

  it("공용에만 있는 구성이면(project.not_imported, in_library) 오류 배너에 [가져와서 실행]이 나온다", async () => {
    const err = new ApiError(422, { code: "project.not_imported", message: "x", details: { project_id: "p1", kind: "k-graph", id: "g-any", in_library: true } });
    setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { runTaskAction: vi.fn(async () => { throw err; }) } });
    const menu = await openMenu();
    fireEvent.click(await within(menu).findByRole("menuitem", { name: /임의 프로필 실행/ }, LONG));
    const banner = await screen.findByTestId("sdd-run-error", {}, LONG);
    expect(within(banner).getByRole("button", { name: "가져와서 실행" })).toBeTruthy();
  });

  it("줄이 바뀌었으면(409 task_changed) 알림을 내고 작업 목록을 다시 읽는다", async () => {
    const changed = new ApiError(409, { code: "sdd.task_changed", message: "바뀜", details: { task_key: "T1", line_hash: "h-new", line: 4, text: "- [ ] T1 새 줄" } });
    const { sdd } = setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { runTaskAction: vi.fn(async () => { throw changed; }) } });
    const menu = await openMenu();
    fireEvent.click(await within(menu).findByRole("menuitem", { name: /임의 프로필 실행/ }, LONG));
    expect(await screen.findByText("‘작업 T1’ 줄이 다른 곳에서 바뀌어 상태를 바꾸지 못했습니다", {}, LONG)).toBeTruthy();
    await waitFor(() => expect(sdd.listSpecTasks.mock.calls.length).toBeGreaterThan(1), LONG);
  });
});

describe("작업 탭: 준비된 작업 한꺼번에 시작", () => {
  const bulkActions = vi.fn(async () => ({ actions: [ACTION_A], per_task: { T1: [{ integration: "i-x", id: "a-1" }] } }));

  it("준비된 작업만 목록에 나오고, 동작을 골라 시작하면 모두 시작될 때 닫히며 토스트가 나온다", async () => {
    const start = vi.fn(async () => ({ items: [{ task_key: "T1", status: "started", run_id: "r1" }] }));
    const { sdd } = setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { listBulkActions: bulkActions, bulkStartTasks: start } });
    fireEvent.click(await screen.findByRole("checkbox", { name: "작업 T1 선택" }, LONG));
    fireEvent.click(await screen.findByRole("button", { name: "준비된 작업 시작…" }, LONG));
    const dialog = await screen.findByRole("dialog", {}, LONG);
    expect(within(dialog).getAllByRole("checkbox")).toHaveLength(1);
    fireEvent.click(await within(dialog).findByRole("button", { name: "시작 (1)" }, LONG));
    await waitFor(() => expect(sdd.bulkStartTasks).toHaveBeenCalledWith("sp1", { task_keys: ["T1"], action: { integration: "i-x", id: "a-1" } }), LONG);
    expect(await screen.findByText("작업 1개를 시작했습니다", {}, LONG)).toBeTruthy();
  });

  it("일부가 막히거나 실패하면 닫지 않고 작업별 이유를 보인다", async () => {
    const start = vi.fn(async () => ({ items: [{ task_key: "T1", status: "failed", issue: { severity: "error", code: "x", message: "이 작업은 조건이 맞지 않습니다" } }] }));
    setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { listBulkActions: bulkActions, bulkStartTasks: start } });
    fireEvent.click(await screen.findByRole("checkbox", { name: "작업 T1 선택" }, LONG));
    fireEvent.click(await screen.findByRole("button", { name: "준비된 작업 시작…" }, LONG));
    const dialog = await screen.findByRole("dialog", {}, LONG);
    fireEvent.click(await within(dialog).findByRole("button", { name: "시작 (1)" }, LONG));
    expect(await within(dialog).findByText("이 작업은 조건이 맞지 않습니다", {}, LONG)).toBeTruthy();
    expect(within(dialog).getByText("1개 중 0개를 시작했습니다")).toBeTruthy();
  });

  it("준비된 작업이 없으면 버튼이 aria-disabled이다", async () => {
    const view = specView({ index: { tasks: [task("T1", "s-open", { ready: false })], stages: [] } });
    setup("/specs/sp1?prj=p1&tab=tasks", { view });
    const btn = await screen.findByRole("button", { name: "준비된 작업 시작…" }, LONG);
    expect(btn.getAttribute("aria-disabled")).toBe("true");
  });
});

describe("작업 탭: 표 선택과 한꺼번에 시작 (6R.20i)", () => {
  const bulkActions = vi.fn(async () => ({ actions: [ACTION_A], per_task: {} }));

  it("선택이 없으면 버튼이 aria-disabled(준비된 작업을 선택하세요)이고, 준비 안 된 작업만 골라도 같다", async () => {
    setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { listBulkActions: bulkActions } });
    const btn = await screen.findByRole("button", { name: "준비된 작업 시작…" }, LONG);
    expect(btn.getAttribute("aria-disabled")).toBe("true");
    expect(btn.getAttribute("title")).toBe("준비된 작업을 선택하세요");
    fireEvent.click(await screen.findByRole("checkbox", { name: "작업 T2 선택" }, LONG));
    expect(screen.getByRole("button", { name: "준비된 작업 시작…" }).getAttribute("aria-disabled")).toBe("true");
  });

  it("머리 체크박스는 보이는 준비된 작업만 고르고, '{n}개 선택'과 [선택 해제]가 있다", async () => {
    setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { listBulkActions: bulkActions } });
    fireEvent.click(await screen.findByRole("checkbox", { name: "보이는 준비된 작업 모두 선택" }, LONG));
    expect((screen.getByRole("checkbox", { name: "작업 T1 선택" }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("checkbox", { name: "작업 T2 선택" }) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByRole("checkbox", { name: "작업 T3 선택" }) as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText("1개 선택")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "선택 해제" }));
    expect(screen.queryByText("1개 선택")).toBeNull();
  });

  it("준비 안 된 작업이 섞이면 대화상자에 건너뜀으로 나오고 제출에서 빠진다", async () => {
    const start = vi.fn(async () => ({ items: [{ task_key: "T1", status: "started", run_id: "r1" }] }));
    const { sdd } = setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { listBulkActions: bulkActions, bulkStartTasks: start } });
    fireEvent.click(await screen.findByRole("checkbox", { name: "작업 T1 선택" }, LONG));
    fireEvent.click(screen.getByRole("checkbox", { name: "작업 T2 선택" }));
    fireEvent.click(screen.getByRole("button", { name: "준비된 작업 시작…" }));
    const dialog = await screen.findByRole("dialog", {}, LONG);
    expect(within(dialog).getByText("준비되지 않아 건너뜁니다")).toBeTruthy();
    expect(within(dialog).getByText("선택한 작업 2개 중 1개를 시작합니다")).toBeTruthy();
    fireEvent.click(await within(dialog).findByRole("button", { name: "시작 (1)" }, LONG));
    await waitFor(() => expect(sdd.bulkStartTasks).toHaveBeenCalledWith("sp1", expect.objectContaining({ task_keys: ["T1"] })), LONG);
  });
});

describe("작업 탭: 필드 거르기·단축키·인라인 안내 (6R.20i)", () => {
  const withFields = () => specView({ index: { tasks: [task("T1", "s-open", { fields: { owner: "pl", team: "a" } }), task("T2", "s-open", { fields: { owner: "dev" } }), task("T3", "s-open", { fields: { owner: "pl" } })], stages: [] } });

  it("필드 메뉴는 작업에 나온 키·값에서 만들고, 고르면 field=키=값으로 서버에 묻고 주소·칩에 남는다", async () => {
    const { sdd, router } = setup("/specs/sp1?prj=p1&tab=tasks", { view: withFields() });
    fireEvent.click(await screen.findByRole("button", { name: /^필드/ }, LONG));
    fireEvent.click(await screen.findByRole("button", { name: "owner ›" }, LONG));
    fireEvent.click(screen.getByRole("checkbox", { name: /pl/ }));
    await waitFor(() => expect(sdd.listSpecTasks).toHaveBeenLastCalledWith("sp1", expect.objectContaining({ field: ["owner=pl"] })), LONG);
    expect(decodeURIComponent(router.state.location.search)).toContain("field=owner=pl");
    const chips = await screen.findByTestId("sdd-field-chips", {}, LONG);
    fireEvent.click(within(chips).getByRole("button", { name: "owner: pl 조건 지우기" }));
    await waitFor(() => expect(router.state.location.search).not.toContain("field="), LONG);
  });

  it("주소의 field 조건이 처음부터 서버 질의와 칩에 반영된다", async () => {
    const { sdd } = setup("/specs/sp1?prj=p1&tab=tasks&field=owner%3Ddev", { view: withFields() });
    await waitFor(() => expect(sdd.listSpecTasks).toHaveBeenCalledWith("sp1", expect.objectContaining({ field: ["owner=dev"] })), LONG);
    expect(await screen.findByRole("button", { name: "owner: dev 조건 지우기" }, LONG)).toBeTruthy();
  });

  it("행에 포커스가 있으면 S는 상태 메뉴, O는 문서에서 열기를 한다(입력창 밖)", async () => {
    const { router } = setup("/specs/sp1?prj=p1&tab=tasks");
    const row = await screen.findByRole("button", { name: /^작업 T1, 상태/ }, LONG);
    row.focus();
    fireEvent.keyDown(row, { key: "s" });
    expect(await screen.findByRole("menu", {}, LONG)).toBeTruthy();
    cleanup();
    const second = setup("/specs/sp1?prj=p1&tab=tasks");
    const r2 = await screen.findByRole("button", { name: /^작업 T1, 상태/ }, LONG);
    r2.focus();
    fireEvent.keyDown(r2, { key: "o" });
    await waitFor(() => expect(second.router.state.location.search).toContain("tab=documents"), LONG);
    void router;
  });

  it("Shift+F10은 행 컨텍스트 메뉴(상태·실행·문서에서 열기·키 복사)를 연다", async () => {
    setup("/specs/sp1?prj=p1&tab=tasks");
    const row = await screen.findByRole("button", { name: /^작업 T1, 상태/ }, LONG);
    row.focus();
    fireEvent.keyDown(row, { key: "F10", shiftKey: true });
    const menu = await screen.findByRole("menu", { name: "작업 T1 메뉴" }, LONG);
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["상태 바꾸기", "실행", "문서에서 열기", "작업 키 복사"]);
  });

  it("관문 안내는 그 작업의 행 아래에 보인다(탭 머리가 아니다)", async () => {
    const blocked = new ApiError(422, { code: "sdd.gate_blocked", message: "x", details: { gate_id: "g1", message: "승인 문서가 먼저입니다" } });
    setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { runTaskAction: vi.fn(async () => { throw blocked; }) } });
    const menu = await openMenu();
    fireEvent.click(await within(menu).findByRole("menuitem", { name: /임의 프로필 실행/ }, LONG));
    const text = await screen.findByText("승인 문서가 먼저입니다", {}, LONG);
    expect(text.closest('[data-sdd-task-key="T1"]')).not.toBeNull();
  });

  it("단계 접힘은 저장되고 다시 열면 복원된다(모두 끝난 단계는 처음부터 접힘)", async () => {
    const store = new Map<string, string>();
    const storage = createSafeStorage({ getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k), clear: () => store.clear(), key: () => null, length: 0 });
    const view = specView({
      index: { tasks: [task("T1", "s-open", { stage: { id: "g1", title: "단계 하나" } as ParsedTask["stage"] }), task("T3", "s-end", { stage: { id: "g2", title: "단계 둘" } as ParsedTask["stage"] })], stages: [{ id: "g1", title: "단계 하나", document: "d-tasks", line: 1 }, { id: "g2", title: "단계 둘", document: "d-tasks", line: 3 }] },
    });
    setup("/specs/sp1?prj=p1&tab=tasks", { view }, storage);
    await screen.findByRole("button", { name: /^작업 T1, 상태/ }, LONG);
    expect(screen.queryByRole("button", { name: /^작업 T3, 상태/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /단계 하나 단계 접기·펼치기/ }));
    expect(screen.queryByRole("button", { name: /^작업 T1, 상태/ })).toBeNull();
    expect(JSON.parse(store.get("ac.sdd.stage.sp1") ?? "{}")).toEqual({ g1: true });
    // 다시 열면 복원된다
    cleanup();
    setup("/specs/sp1?prj=p1&tab=tasks", { view }, storage);
    await screen.findByRole("button", { name: /단계 하나 단계 접기·펼치기/ }, LONG);
    expect(screen.queryByRole("button", { name: /^작업 T1, 상태/ })).toBeNull();
  });
});

describe("계획 탭", () => {
  const plan = { ready: ["T1"], layers: [["T1"], ["T2"]], critical_path: ["T1", "T2"], blocked: ["T2"], cycles: [] };

  it("서버 계획을 그래프 자리와 글 목록(병목·준비·막힌 이유)으로 보인다", async () => {
    const { sdd } = setup("/specs/sp1?prj=p1&tab=plan", { sdd: { getSpecPlan: vi.fn(async () => plan) } });
    expect(await screen.findByTestId("plan-graph-stub", {}, LONG)).toBeTruthy();
    expect(sdd.getSpecPlan).toHaveBeenCalledWith("sp1");
    expect((await screen.findByTestId("sdd-plan-critical", {}, LONG)).textContent).toBe("병목: T1 → T2 (2단계)");
    expect(screen.getByText("막힌 이유: T1")).toBeTruthy();
  });

  it("순환이 있으면 띠가 나온다", async () => {
    setup("/specs/sp1?prj=p1&tab=plan", { sdd: { getSpecPlan: vi.fn(async () => ({ ...plan, cycles: [["T1", "T2", "T1"]] })) } });
    expect((await screen.findByTestId("sdd-plan-cycles", {}, LONG)).textContent).toBe("의존이 순환하는 작업이 2건 있습니다");
  });

  it("남은 작업이 없으면 안내만 나온다", async () => {
    const view = specView({ index: { tasks: [task("T3", "s-end")], stages: [] } });
    setup("/specs/sp1?prj=p1&tab=plan", { view, sdd: { getSpecPlan: vi.fn(async () => ({})) } });
    expect(await screen.findByText("남은 작업이 없습니다", {}, LONG)).toBeTruthy();
    expect(screen.queryByTestId("plan-graph-stub")).toBeNull();
  });
});

describe("추적 탭", () => {
  const matrix = (): TraceMatrix => ({
    rows: [
      { id: "R1", title: "첫 요구", document: "d-req", line: 2, tasks: ["T1"], runs: [], gaps: [] },
      { id: "R2", title: "둘째 요구", document: "d-req", line: 3, tasks: [], runs: [], gaps: ["no_task", "모르는_코드"] },
    ],
    orphans: { tasks_without_requirements: ["T2"] },
  });

  it("빈 곳은 표시 데이터의 문구·톤으로, 모르는 코드는 원문으로 보이고 [빈 곳만]이 거른다", async () => {
    const { sdd } = setup("/specs/sp1?prj=p1&tab=trace", { sdd: { getSpecTrace: vi.fn(async () => matrix()) } });
    expect(await screen.findByText("둘째 요구", {}, LONG)).toBeTruthy();
    expect(sdd.getSpecTrace).toHaveBeenCalledWith("sp1");
    expect(screen.getByText("작업 없음")).toBeTruthy();
    expect(screen.getByText("모르는_코드")).toBeTruthy();
    expect((await screen.findByTestId("sdd-trace-summary")).textContent).toContain("요구 2 · 빈 곳 2건");
    fireEvent.click(screen.getAllByRole("switch", { name: "빈 곳만" })[0] as HTMLElement);
    await waitFor(() => expect(screen.queryByText("첫 요구")).toBeNull(), LONG);
    expect(screen.getByText("둘째 요구")).toBeTruthy();
  });

  it("작업 칩은 작업 탭으로, 요구는 상세로 이동한다", async () => {
    const { router } = setup("/specs/sp1?prj=p1&tab=trace", { sdd: { getSpecTrace: vi.fn(async () => matrix()) } });
    fireEvent.click(await screen.findByRole("button", { name: "T1 작업 열기" }, LONG));
    await waitFor(() => expect(router.state.location.search).toContain("task=T1"), LONG);
    expect(router.state.location.search).toContain("tab=tasks");
  });

  it("주소의 req가 있으면 그 요구의 상세(위치·빈 곳 설명)가 보인다", async () => {
    setup("/specs/sp1?prj=p1&tab=trace&req=R2", { sdd: { getSpecTrace: vi.fn(async () => matrix()) } });
    const detail = await screen.findByTestId("sdd-trace-detail", {}, LONG);
    expect(within(detail).getByText("이 요구를 구현하는 작업이 없습니다.")).toBeTruthy();
    expect(within(detail).getByText("요구:3")).toBeTruthy();
  });

  it("요구가 0개면 안내와 [요구 문서 열기]가 나온다", async () => {
    setup("/specs/sp1?prj=p1&tab=trace", { sdd: { getSpecTrace: vi.fn(async () => ({ rows: [] })) } });
    expect(await screen.findByTestId("sdd-trace-empty", {}, LONG)).toBeTruthy();
    expect(screen.getByRole("button", { name: "요구 문서 열기" })).toBeTruthy();
  });

  it("실행 연동이 꺼져도 요구↔작업 표는 정상이다", async () => {
    const info = { ...INFO, capabilities: { ...INFO.capabilities, runs: false, verification: false } } as SddInfo;
    setup("/specs/sp1?prj=p1&tab=trace", { info, sdd: { getSpecTrace: vi.fn(async () => matrix()) } });
    expect(await screen.findByText("첫 요구", {}, LONG)).toBeTruthy();
  });
});

describe("규칙 탭: 자동 진행", () => {
  const automationView = (state: object) => specView({ spec: { ...specView().spec, rules: { automation: { enabled: true, max_parallel: 2, max_failures: 3 } } }, automation_state: state as never });

  it("켜져 있으면 상태 줄이 나오고 [멈춤]이 stop을 보낸다. 멈춘 상태는 이유와 [다시 시작]이 나온다", async () => {
    const ctl = vi.fn(async () => ({ enabled: true, running: false }));
    const { sdd } = setup("/specs/sp1?prj=p1&tab=rules", { view: automationView({ enabled: true, running: true, active_runs: ["r1"], skipped_keys: [] }), sdd: { controlAutomation: ctl } });
    const bar = await screen.findByTestId("sdd-automation", {}, LONG);
    expect(bar.textContent).toContain("진행 중 실행 1개");
    fireEvent.click(within(bar).getByRole("button", { name: "멈춤" }));
    await waitFor(() => expect(sdd.controlAutomation).toHaveBeenCalledWith("sp1", "stop"), LONG);
    cleanup();
    setup("/specs/sp1?prj=p1&tab=rules", { view: automationView({ enabled: true, running: false, stopped_reason: "failures" }), sdd: { controlAutomation: ctl } });
    const stopped = await screen.findByTestId("sdd-automation", {}, LONG);
    expect(stopped.textContent).toContain("멈춤 — 연속 실패 상한에 도달");
    expect(within(stopped).getByRole("button", { name: "다시 시작" })).toBeTruthy();
  });

  it("모르는 멈춤 이유는 원문으로 보인다", async () => {
    setup("/specs/sp1?prj=p1&tab=rules", { view: automationView({ enabled: true, running: false, stopped_reason: "내가_만든_이유" }) });
    expect((await screen.findByTestId("sdd-automation", {}, LONG)).textContent).toContain("멈춤 — 내가_만든_이유");
  });

  it("작업 탭 도구줄에 자동 진행 칩이 있고 누르면 규칙 탭으로 간다", async () => {
    const { router } = setup("/specs/sp1?prj=p1&tab=tasks", { view: automationView({ enabled: true, running: true }) });
    fireEvent.click(await screen.findByTestId("sdd-auto-chip", {}, LONG));
    await waitFor(() => expect(router.state.location.search).toContain("tab=rules"), LONG);
  });
});
