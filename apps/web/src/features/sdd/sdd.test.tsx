import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, type SddClient } from "@agent-console/api-client";
import type { ModuleInfo, Project, ProjectView } from "@agent-console/contracts";
import type { EffectiveSyntax, ParsedTask, SddInfo, SpecSummary, SpecView } from "@agent-console/contracts/sdd";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";

afterEach(cleanup);

const LONG = { timeout: 15_000 };
// 상태·문서·단계 이름은 모두 임의 값이다. 화면 코드는 이 이름을 모른다.
const mod = (roles: string[], extra: Partial<ModuleInfo> = {}): ModuleInfo => ({ id: "m-any", kind: "k", version: "0.0.1", status: "active", web_roles: roles, ...extra });
const MODULES = async () => [mod(["sdd", "projects", "settings", "runs"])];
const project = (id: string, over: Partial<Project> = {}): Project => ({ id, name: id.toUpperCase(), folder: `/w/${id}`, ...over }) as Project;
const projectView = (p: Project, over: Partial<ProjectView> = {}): ProjectView => ({ project: p, status: "ready", config_writable: true, kinds: [], records_writable: true, config_dir: ".cfg", ...over }) as ProjectView;

const INFO: SddInfo = { spec_root: ".cfg/specs", limits: { max_bulk_start: 10 }, capabilities: { runs: true, templates: true, import_export: true, verification: false, automation: false }, writable: true } as SddInfo;
const STATUSES = [
  { id: "s-open", label: "열림", tone: "neutral" },
  { id: "s-end", label: "끝남", tone: "success", done: true },
];
const task = (key: string, status = "s-open", extra: Partial<ParsedTask> = {}): ParsedTask => ({ key, id: key, title: `작업 ${key}`, status, document: "d-tasks", line: 4, line_hash: `h-${key}`, ready: true, ...extra });
const specView = (over: Partial<SpecView> = {}): SpecView => ({
  spec: { kind: "k-x", id: "sp1", name: "결제", documents: [{ id: "d-req", title: "요구", file: "req.md", roles: ["requirements"], state: "g-draft" }, { id: "d-tasks", title: "작업표", file: "tasks.md", roles: ["tasks"] }], rules: {} },
  index: { tasks: [task("T1"), task("T2", "s-end")], stages: [] },
  version_hash: "v1",
  directory: ".cfg/specs/sp1",
  task_statuses: STATUSES,
  document_states: [{ id: "g-draft", label: "초안", tone: "neutral" }],
  issues: [],
  ...over,
});
const summary = (over: Partial<SpecSummary> = {}): SpecSummary => ({ id: "sp1", name: "결제", directory: ".cfg/specs/sp1", tasks_total: 2, tasks_done: 1, ready: 1, updated_at: 1_700_000_000, documents: [{ id: "d-req", title: "요구", state: "g-draft", state_label: "초안", tone: "neutral" }], ...over });
const SYNTAX: EffectiveSyntax = { empty: false, statuses: STATUSES, sources: { "task.list": "default" } } as EffectiveSyntax;

interface Fixture {
  info?: SddInfo;
  specs?: SpecSummary[];
  view?: SpecView;
  syntax?: EffectiveSyntax;
  tasks?: ParsedTask[];
  projects?: ProjectView[];
  modules?: ModuleInfo[];
  sdd?: Record<string, unknown>;
}

function setup(path: string, f: Fixture = {}) {
  const view = f.view ?? specView();
  const projects = f.projects ?? [projectView(project("p1", { name: "결제앱" }))];
  const { clients, ws, sddClient, sdd, rest } = createFakeClients(
    { listModules: vi.fn(async () => f.modules ?? (await MODULES())), listProjects: vi.fn(async () => projects) },
    {},
    {
      getSddInfo: vi.fn(async () => f.info ?? INFO),
      listSpecs: vi.fn(async () => f.specs ?? []),
      listSpecTemplates: vi.fn(async () => []),
      getSpec: vi.fn(async () => ({ value: view, version_hash: view.version_hash })),
      getSpecSyntax: vi.fn(async () => f.syntax ?? SYNTAX),
      listSpecTasks: vi.fn(async () => f.tasks ?? view.index?.tasks ?? []),
      getSpecDocument: vi.fn(async (_id: string, doc: string) => ({ value: { document_id: doc, file: "x.md", content: `# ${doc}`, content_hash: "c1", issues: [] }, version_hash: "c1" })),
      ...f.sdd,
    },
  );
  const mounted = mountApp(clients, path);
  return { ...mounted, clients, ws, sdd: sddClient as unknown as { [K in keyof SddClient]: ReturnType<typeof vi.fn> }, sddFactory: sdd, rest };
}

const nav = () => within(screen.getByRole("navigation", { name: "주 메뉴" }));

describe("스펙 목록: 배치·빈 상태", () => {
  it("역할 sdd가 있으면 사이드바에 '스펙'과 '문서 틀'이 있고, 없으면 둘 다 없고 주소로 들어가면 꺼진 기능 안내가 나온다", async () => {
    setup("/specs?prj=p1");
    expect(await screen.findByRole("heading", { name: "스펙", level: 1 }, LONG)).toBeTruthy();
    expect(nav().getByRole("link", { name: "스펙" })).toBeTruthy();
    expect(nav().getByRole("link", { name: "문서 틀" })).toBeTruthy();
    cleanup();
    const off = createFakeClients({ listModules: vi.fn(async () => [{ ...mod(["sdd"]), status: "disabled" }]) });
    mountApp(off.clients, "/specs");
    expect(await screen.findByRole("heading", { name: "이 기능은 꺼져 있습니다", level: 1 }, LONG)).toBeTruthy();
    expect(nav().queryByRole("link", { name: "스펙" })).toBeNull();
  });

  it("스펙이 0개: 안내 + 머리의 [새 스펙…]이 주 진입이고 본문에는 같은 버튼이 없다", async () => {
    const { sdd } = setup("/specs?prj=p1");
    expect(await screen.findByText("아직 스펙이 없습니다", {}, LONG)).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "새 스펙…" })).toHaveLength(1);
    expect(sdd.listSpecs).toHaveBeenCalled();
  });

  it("스펙 목록은 서버 데이터(임의 이름·문서 상태 라벨)로 그려지고 행을 누르면 상세로 간다", async () => {
    const { router } = setup("/specs?prj=p1", { specs: [summary(), summary({ id: "sp2", name: "배송", updated_at: 1_600_000_000 })] });
    expect(await screen.findByText("결제", {}, LONG)).toBeTruthy();
    expect(screen.getAllByText("초안").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /배송/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/specs/sp2"), LONG);
  });

  it("검색으로 거르고 결과가 없으면 안내와 [검색 지우기]가 나온다", async () => {
    setup("/specs?prj=p1", { specs: [summary()] });
    await screen.findByText("결제", {}, LONG);
    fireEvent.change(screen.getByRole("searchbox", { name: "스펙 검색" }), { target: { value: "없는이름" } });
    expect(await screen.findByText("‘없는이름’와 맞는 스펙이 없습니다", {}, LONG)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "검색 지우기" }));
    expect(await screen.findByText("결제", {}, LONG)).toBeTruthy();
  });

  it("프로젝트가 0개면 본문 전체가 NoProjectState 하나로 바뀌고 [새 스펙…]도 없다", async () => {
    const { sdd } = setup("/specs", { projects: [] });
    expect(await screen.findByTestId("no-project-state", {}, LONG)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "새 스펙…" })).toBeNull();
    expect(sdd.listSpecs).not.toHaveBeenCalled();
  });

  it("프로젝트 연동이 꺼져(409 spaces_unavailable) 있으면 본문 전체가 안내로 바뀐다", async () => {
    setup("/specs?prj=p1", { sdd: { listSpecs: vi.fn(async () => { throw new ApiError(409, { code: "sdd.spaces_unavailable", message: "x" }); }) } });
    expect(await screen.findByTestId("sdd-unavailable", {}, LONG)).toBeTruthy();
    expect(screen.getByText("스펙을 저장할 프로젝트 연동이 꺼져 있습니다")).toBeTruthy();
  });

  it("프로젝트 기능이 없는 조립에서는 공간 없이(단독 루트) 요청하고 화면이 그대로 동작한다", async () => {
    const { sddFactory } = setup("/specs", { modules: [mod(["sdd"])], specs: [summary()] });
    expect(await screen.findByText("결제", {}, LONG)).toBeTruthy();
    expect(sddFactory).toHaveBeenCalledWith(null);
    expect(screen.queryByTestId("no-project-state")).toBeNull();
  });
});

describe("스펙 목록: 읽기 전용·새 스펙", () => {
  const readonlyProject = [projectView(project("p1"), { config_writable: false })];

  it("폴더에 쓸 수 없으면 [새 스펙…]·[폴더에서 가져오기…]가 aria-disabled이고 이유가 보이며 누르면 대화상자가 열리지 않는다", async () => {
    setup("/specs?prj=p1", { projects: readonlyProject, specs: [summary()] });
    const btn = await screen.findByRole("button", { name: "새 스펙…" }, LONG);
    expect(btn.getAttribute("aria-disabled")).toBe("true");
    expect(btn.getAttribute("title")).toContain("폴더를 쓸 수 없어");
    expect(screen.getByTestId("sdd-readonly")).toBeTruthy();
    fireEvent.click(btn);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("틀이 0개: 안내가 나오고 '빈 스펙'만 선택돼 있으며, 이름만으로 만들면 template 없이 요청한다", async () => {
    const created = specView({ spec: { ...specView().spec, id: "new1", name: "새것" } });
    const { sdd, router } = setup("/specs?prj=p1", { specs: [summary()], sdd: { createSpec: vi.fn(async () => ({ value: created, version_hash: "v1" })) } });
    fireEvent.click(await screen.findByRole("button", { name: "새 스펙…" }, LONG));
    const dialog = await screen.findByRole("dialog", { name: "새 스펙" }, LONG);
    expect(await within(dialog).findByTestId("sdd-no-templates", {}, LONG)).toBeTruthy();
    expect((within(dialog).getByRole("radio", { name: /빈 스펙/ }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(within(dialog).getByRole("button", { name: "스펙 만들기" }));
    expect(await within(dialog).findByText("이름을 입력하세요")).toBeTruthy();
    expect(sdd.createSpec).not.toHaveBeenCalled();
    fireEvent.change(within(dialog).getByLabelText(/이름/), { target: { value: "새것" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "스펙 만들기" }));
    await waitFor(() => expect(sdd.createSpec).toHaveBeenCalledWith({ name: "새것" }), LONG);
    await waitFor(() => expect(router.state.location.pathname).toBe("/specs/new1"), LONG);
  });

  it("틀이 있으면 이름 순 라디오로 보이고, 고른 틀 id가 요청에 실린다", async () => {
    const templates = [
      { id: "t-b", name: "나 틀", documents: [{ id: "a", title: "a", file: "a.md" }], run_profiles: [] },
      { id: "t-a", name: "가 틀", documents: [{ id: "a", title: "a", file: "a.md" }, { id: "b", title: "b", file: "b.md" }], run_profiles: [{ id: "p" }] },
    ];
    const { sdd } = setup("/specs?prj=p1", { specs: [summary()], sdd: { listSpecTemplates: vi.fn(async () => templates), createSpec: vi.fn(async () => ({ value: specView(), version_hash: "v1" })) } });
    fireEvent.click(await screen.findByRole("button", { name: "새 스펙…" }, LONG));
    const dialog = await screen.findByRole("dialog", { name: "새 스펙" }, LONG);
    await waitFor(() => expect(within(dialog).getAllByRole("radio")).toHaveLength(3), LONG);
    const radios = within(dialog).getAllByRole("radio");
    expect(radios.map((r) => r.closest("label")?.textContent)).toEqual([expect.stringContaining("가 틀"), expect.stringContaining("나 틀"), expect.stringContaining("빈 스펙")]);
    fireEvent.click(radios[1] as HTMLElement);
    fireEvent.change(within(dialog).getByLabelText(/이름/), { target: { value: "x" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "스펙 만들기" }));
    await waitFor(() => expect(sdd.createSpec).toHaveBeenCalledWith({ name: "x", template: "t-b" }), LONG);
  });
});

describe("스펙 상세: 탭·문서", () => {
  it("탭 줄에는 등록된 탭만 있고(문서·작업·규칙), 주소 ?tab에 따라 본문이 바뀐다", async () => {
    const { router } = setup("/specs/sp1?prj=p1");
    const tablist = await screen.findByRole("tablist", { name: "스펙 탭" }, LONG);
    expect(within(tablist).getAllByRole("tab").map((t) => t.textContent?.replace(/\s*\d+$/, ""))).toEqual(["문서", "작업", "규칙"]);
    fireEvent.click(within(tablist).getByRole("tab", { name: /작업/ }));
    await waitFor(() => expect(router.state.location.search).toContain("tab=tasks"), LONG);
  });

  it("문서 목록·상태 칩은 서버 라벨이고, 본문은 첫 문서 id로 읽는다(저장 헤더는 api-client 시험이 확인)", async () => {
    const { sdd } = setup("/specs/sp1?prj=p1&tab=documents");
    const nav2 = await screen.findByRole("navigation", { name: "문서" }, LONG);
    expect(within(nav2).getByText("요구")).toBeTruthy();
    expect(within(nav2).getAllByText("초안").length).toBeGreaterThan(0);
    await screen.findByRole("textbox", { name: /문서 본문 편집기/ }, LONG);
    expect(sdd.getSpecDocument).toHaveBeenCalledWith("sp1", "d-req");
  });

  it("문서 파일이 없으면(404 document_missing) 만들기 버튼이 있고 If-None-Match 방식으로 만든다", async () => {
    const missing = new ApiError(404, { code: "sdd.document_missing", message: "없음", details: { document_id: "d-req", file: "req.md" } });
    const put = vi.fn(async () => ({ value: { document_id: "d-req", file: "req.md", content: "", content_hash: "c1", issues: [] }, version_hash: "c1" }));
    const { sdd } = setup("/specs/sp1?prj=p1&tab=documents", { sdd: { getSpecDocument: vi.fn(async () => { throw missing; }), putSpecDocument: put } });
    fireEvent.click(await screen.findByRole("button", { name: "빈 파일로 만들기" }, LONG));
    await waitFor(() => expect(sdd.putSpecDocument).toHaveBeenCalledWith("sp1", "d-req", "", { createOnly: true }), LONG);
  });

  it("읽기 전용 폴더: 편집기가 읽기 전용이고 이유가 보이며, 상태 전환 버튼은 aria-disabled이다", async () => {
    const view = specView({ spec: { ...specView().spec, rules: { document_states: [{ id: "g-draft" }, { id: "g-ok", label: "승인" }], transitions: [{ from: "g-draft", to: "g-ok", by: ["human"] }] } }, document_states: [{ id: "g-draft", label: "초안" }, { id: "g-ok", label: "승인" }] });
    setup("/specs/sp1?prj=p1&tab=documents", { view, projects: [projectView(project("p1"), { config_writable: false })] });
    expect(await screen.findByText("읽기 전용", {}, LONG)).toBeTruthy();
    expect(screen.getAllByText(/폴더를 쓸 수 없어/).length).toBeGreaterThan(0);
    const t = await screen.findByRole("button", { name: "→ 승인" }, LONG);
    expect(t.getAttribute("aria-disabled")).toBe("true");
  });

  it("사람이 할 수 있는 전환 버튼만 보이고, 누르면 POST state로 도착 상태를 보낸다", async () => {
    const view = specView({ spec: { ...specView().spec, rules: { document_states: [{ id: "g-draft" }, { id: "g-ok" }], transitions: [{ from: "g-draft", to: "g-ok", by: ["human"] }, { from: "g-draft", to: "g-secret", by: ["run"] }] } }, document_states: [{ id: "g-draft", label: "초안" }, { id: "g-ok", label: "승인" }] });
    const change = vi.fn(async () => ({ value: view, version_hash: "v2" }));
    const { sdd } = setup("/specs/sp1?prj=p1&tab=documents", { view, sdd: { changeDocumentState: change } });
    const btn = await screen.findByRole("button", { name: "→ 승인" }, LONG);
    expect(screen.queryByRole("button", { name: /g-secret/ })).toBeNull();
    fireEvent.click(btn);
    await waitFor(() => expect(sdd.changeDocumentState).toHaveBeenCalledWith("sp1", "d-req", { to: "g-ok" }), LONG);
  });

  it("스펙을 찾을 수 없으면(404 not_found) 안내와 [스펙 목록으로]가 나온다", async () => {
    setup("/specs/nope?prj=p1", { sdd: { getSpec: vi.fn(async () => { throw new ApiError(404, { code: "sdd.not_found", message: "x" }); }) } });
    expect(await screen.findByText("스펙을 찾을 수 없습니다", {}, LONG)).toBeTruthy();
    expect(screen.getByRole("button", { name: "스펙 목록으로" })).toBeTruthy();
  });
});

describe("스펙 상세: 작업 탭", () => {
  it("작업 문법이 없으면(유효 문법 empty) 표 대신 안내와 [규칙 열기]가 나오고 작업 질의를 하지 않는다", async () => {
    const { sdd, router } = setup("/specs/sp1?prj=p1&tab=tasks", { syntax: { empty: true, statuses: [], sources: {} } as EffectiveSyntax });
    expect(await screen.findByTestId("sdd-syntax-missing", {}, LONG)).toBeTruthy();
    expect(screen.getByText("작업 문법이 없습니다")).toBeTruthy();
    expect(sdd.listSpecTasks).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "규칙 열기" }));
    await waitFor(() => expect(router.state.location.search).toContain("tab=rules"), LONG);
  });

  it("작업 역할 문서가 없으면 그 안내가 나온다", async () => {
    const view = specView({ spec: { ...specView().spec, documents: [{ id: "d-req", title: "요구", file: "req.md", roles: ["requirements"] }] } });
    setup("/specs/sp1?prj=p1&tab=tasks", { view });
    expect(await screen.findByTestId("sdd-no-task-doc", {}, LONG)).toBeTruthy();
  });

  it("작업은 서버 상태 라벨로 그려지고, 상태를 바꾸면 줄 해시와 함께 PATCH하며 값을 미리 바꿔 보이지 않는다", async () => {
    const patch = vi.fn(async () => ({ task: task("T1", "s-end"), version_hash: "v2", content_hash: "c2" }));
    const { sdd } = setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { patchSpecTask: patch } });
    const chip = await screen.findByRole("button", { name: /^작업 T1의 상태 바꾸기/ }, LONG);
    expect(chip.textContent).toContain("열림");
    fireEvent.click(chip);
    fireEvent.click(await screen.findByRole("menuitemradio", { name: /끝남/ }, LONG));
    await waitFor(() => expect(sdd.patchSpecTask).toHaveBeenCalledWith("sp1", "T1", { status: "s-end", expected_line_hash: "h-T1" }), LONG);
    expect(screen.getByRole("button", { name: /^작업 T1의 상태 바꾸기/ }).textContent).toContain("열림");
  });

  it("줄이 바뀌었으면(409 task_changed) 최신 줄로 다시 읽고 알림을 낸다", async () => {
    const changed = new ApiError(409, { code: "sdd.task_changed", message: "바뀜", details: { task_key: "T1", line_hash: "h-new", line: 4, text: "- [ ] T1 새 줄" } });
    const { sdd } = setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { patchSpecTask: vi.fn(async () => { throw changed; }) } });
    fireEvent.click(await screen.findByRole("button", { name: /^작업 T1의 상태 바꾸기/ }, LONG));
    fireEvent.click(await screen.findByRole("menuitemradio", { name: /끝남/ }, LONG));
    expect(await screen.findByText("‘작업 T1’ 줄이 다른 곳에서 바뀌어 상태를 바꾸지 못했습니다", {}, LONG)).toBeTruthy();
    await waitFor(() => expect(sdd.listSpecTasks.mock.calls.length).toBeGreaterThan(1), LONG);
  });

  it("관문에 막히면(422 gate_blocked) 서버 문구가 관문 안내로 보인다", async () => {
    const blocked = new ApiError(422, { code: "sdd.gate_blocked", message: "x", details: { gate_id: "g1", message: "설계 승인이 먼저입니다", document_ids: ["d-req"] } });
    setup("/specs/sp1?prj=p1&tab=tasks", { sdd: { patchSpecTask: vi.fn(async () => { throw blocked; }) } });
    fireEvent.click(await screen.findByRole("button", { name: /^작업 T1의 상태 바꾸기/ }, LONG));
    fireEvent.click(await screen.findByRole("menuitemradio", { name: /끝남/ }, LONG));
    expect(await screen.findByText("설계 승인이 먼저입니다", {}, LONG)).toBeTruthy();
  });

  it("읽기 전용 폴더: 상태 칩이 aria-disabled이고 눌러도 PATCH가 없다", async () => {
    const { sdd } = setup("/specs/sp1?prj=p1&tab=tasks", { projects: [projectView(project("p1"), { config_writable: false })] });
    const chip = await screen.findByRole("button", { name: /^작업 T1의 상태 바꾸기/ }, LONG);
    expect(chip.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(chip);
    expect(screen.queryByRole("menuitemradio")).toBeNull();
    expect(sdd.patchSpecTask).not.toHaveBeenCalled();
  });

  it("실행 연동이 꺼지면(capabilities.runs=false) 안내 한 줄이 있고 실행 열·동작이 없다. 거르기는 서버 질의로 간다", async () => {
    const info = { ...INFO, capabilities: { ...INFO.capabilities, runs: false } } as SddInfo;
    const { sdd } = setup("/specs/sp1?prj=p1&tab=tasks", { info });
    expect(await screen.findByTestId("sdd-runs-off", {}, LONG)).toBeTruthy();
    await screen.findByRole("button", { name: /^작업 T1의 상태 바꾸기/ }, LONG);
    fireEvent.click(screen.getByRole("switch", { name: "준비만" }));
    await waitFor(() => expect(sdd.listSpecTasks).toHaveBeenCalledWith("sp1", { ready: true }), LONG);
  });
});

describe("스펙 상세: 규칙 탭", () => {
  it("섹션 목록은 스키마(제목)에서 나오고, 규칙 검사는 현재 값으로 POST한다", async () => {
    const check = vi.fn(async () => ({ issues: [{ severity: "error", code: "x", message: "서버가 준 문장", path: "/rules/gates/0" }] }));
    const { sdd } = setup("/specs/sp1?prj=p1&tab=rules", { sdd: { checkSpec: check } });
    const navEl = await screen.findByRole("navigation", { name: "섹션" }, LONG);
    expect(within(navEl).getAllByRole("button").length).toBeGreaterThan(3);
    fireEvent.click(screen.getByRole("button", { name: "규칙 검사" }));
    await waitFor(() => expect(sdd.checkSpec).toHaveBeenCalled(), LONG);
    expect(await screen.findByTestId("sdd-check-summary", {}, LONG)).toBeTruthy();
  });

  it("읽기 전용 폴더: 맨 위 경고가 있고 [저장]은 aria-disabled이다", async () => {
    setup("/specs/sp1?prj=p1&tab=rules", { projects: [projectView(project("p1"), { config_writable: false })] });
    expect(await screen.findByTestId("sdd-rules-readonly", {}, LONG)).toBeTruthy();
    expect(screen.getByRole("button", { name: "저장" }).getAttribute("aria-disabled")).toBe("true");
  });

  it("틀로 저장은 문서 틀 화면과 능력(templates)이 있을 때만 보인다", async () => {
    const info = { ...INFO, capabilities: { ...INFO.capabilities, templates: false } } as SddInfo;
    setup("/specs/sp1?prj=p1&tab=rules", { info });
    await screen.findByRole("button", { name: "규칙 검사" }, LONG);
    expect(screen.queryByRole("button", { name: "틀로 저장…" })).toBeNull();
  });
});

describe("문서 틀 화면", () => {
  it("공용 문서 틀 목록과 요약을 보인다(읽기 전용 안내 포함)", async () => {
    const { sddFactory } = setup("/spec-templates?prj=p1", { sdd: { listSpecTemplates: vi.fn(async () => [{ id: "t1", name: "임의 틀", description: "설명", documents: [{ id: "a", title: "문서가", file: "a.md" }], run_profiles: [{ id: "p", title: "프로필가" }] }]) } });
    fireEvent.click(await screen.findByRole("button", { name: /임의 틀/ }, LONG));
    expect(await screen.findByText("문서가")).toBeTruthy();
    expect(screen.getByText("프로필가")).toBeTruthy();
    expect(sddFactory).toHaveBeenCalledWith(null);
  });

  it("틀이 0개면 안내가, 능력이 꺼져 있으면 꺼짐 안내가 나온다", async () => {
    setup("/spec-templates?prj=p1");
    expect(await screen.findByTestId("sdd-templates-empty", {}, LONG)).toBeTruthy();
    cleanup();
    setup("/spec-templates?prj=p1", { info: { ...INFO, capabilities: { ...INFO.capabilities, templates: false } } as SddInfo });
    expect(await screen.findByTestId("sdd-templates-off", {}, LONG)).toBeTruthy();
  });
});
