import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModuleInfo, Project, ProjectView } from "@agent-console/contracts";
import type { SddInfo, SpecTemplate, SpecTemplateSummary } from "@agent-console/contracts/sdd";
import { createFakeClients, versionConflict } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";

afterEach(cleanup);

const LONG = { timeout: 15_000 };
// 틀·문서·프로필 이름은 모두 임의 값이다. 화면 코드는 이 이름을 모른다.
const mod = (roles: string[]): ModuleInfo => ({ id: "m-any", kind: "k", version: "0.0.1", status: "active", web_roles: roles });
const project = (id: string, over: Partial<Project> = {}): Project => ({ id, name: id.toUpperCase(), folder: `/w/${id}`, ...over }) as Project;
const projectView = (p: Project, over: Partial<ProjectView> = {}): ProjectView => ({ project: p, status: "ready", config_writable: true, kinds: [], records_writable: true, config_dir: ".cfg", ...over }) as ProjectView;
const INFO: SddInfo = { spec_root: ".cfg/specs", limits: { max_bulk_start: 10 }, capabilities: { runs: true, templates: true, import_export: true, verification: false, automation: false }, writable: true } as SddInfo;

const summary = (id: string, name: string): SpecTemplateSummary => ({ id, name, documents: [{ id: "d1", title: "문서가", file: "a.md" }], run_profiles: [] }) as SpecTemplateSummary;
const full = (id: string, name: string): SpecTemplate => ({ kind: "k-x", id, name, documents: [{ id: "d1", title: "문서가", file: "a.md" }, { id: "d2", title: "문서나", file: "b.md" }], rules: {} }) as unknown as SpecTemplate;

interface Fixture {
  info?: SddInfo;
  list?: SpecTemplateSummary[];
  projects?: ProjectView[];
  sdd?: Record<string, unknown>;
  rest?: Record<string, unknown>;
}

function setup(path: string, f: Fixture = {}) {
  const projects = f.projects ?? [projectView(project("p1", { name: "결제앱" }))];
  const made = createFakeClients(
    { listModules: vi.fn(async () => [mod(["sdd", "projects", "settings"])]), listProjects: vi.fn(async () => projects), listDefinitionVersions: vi.fn(async () => []), ...f.rest },
    {},
    {
      getSddInfo: vi.fn(async () => f.info ?? INFO),
      listSpecs: vi.fn(async () => []),
      listSpecTemplates: vi.fn(async () => f.list ?? [summary("t1", "임의 틀"), summary("t2", "다른 틀")]),
      getSpecTemplate: vi.fn(async (id: string) => ({ value: full(id, id === "t1" ? "임의 틀" : "다른 틀"), version_hash: "h1" })),
      listSpecTemplateFiles: vi.fn(async () => [{ path: "a.md", size: 3, media_type: "text/markdown" }]),
      readSpecTemplateFile: vi.fn(async () => ({ text: "# a", contentType: "text/markdown", size: 3, version_hash: "h1" })),
      checkTemplate: vi.fn(async () => ({ issues: [{ code: "x", severity: "error", message: "서버가 준 문장", path: "/rules" }] })),
      ...f.sdd,
    },
  );
  return { ...made, ...mountApp(made.clients, path) };
}

describe("문서 틀 편집 화면", () => {
  it("목록에서 틀을 고르면 편집기와 탭 3개가 열리고 그 틀의 원문을 읽는다(공간은 ?prj)", async () => {
    const { sdd, sddClient } = setup("/spec-templates?prj=p1");
    fireEvent.click(await screen.findByRole("button", { name: /임의 틀/ }, LONG));
    expect(await screen.findByTestId("sdd-template-editor", {}, LONG)).toBeTruthy();
    const tabs = within(screen.getByRole("tablist", { name: "문서 틀 탭" }));
    expect(["규칙", "뼈대 파일", "버전"].every((n) => tabs.getByRole("tab", { name: n }) !== null)).toBe(true);
    expect((sddClient as unknown as { getSpecTemplate: ReturnType<typeof vi.fn> }).getSpecTemplate).toHaveBeenCalledWith("t1");
    expect(sdd).toHaveBeenCalledWith("p1");
  });

  it("빈 목록: 안내가 나오고 머리의 [새 문서 틀]이 주 진입이다. 만들면 편집기가 열린다", async () => {
    const created = full("made", "새로운 틀");
    const { sddClient, router } = setup("/spec-templates?prj=p1", {
      list: [],
      sdd: { createSpecTemplate: vi.fn(async () => ({ value: created, version_hash: "h0" })) },
    });
    expect(await screen.findByTestId("sdd-templates-empty", {}, LONG)).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "새 문서 틀" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "새 문서 틀" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "만들기" }));
    expect(await within(dialog).findByText("이름을 입력하세요")).toBeTruthy();
    fireEvent.change(within(dialog).getByRole("textbox", { name: /이름/ }), { target: { value: "새로운 틀" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "만들기" }));
    await waitFor(() => expect((sddClient as unknown as { createSpecTemplate: ReturnType<typeof vi.fn> }).createSpecTemplate).toHaveBeenCalledWith({ name: "새로운 틀" }));
    await waitFor(() => expect(router.state.location.search).toContain("template=made"), LONG);
  });

  it("[검사]는 서버 메시지를 그대로 보이고 칩에 건수가 나온다", async () => {
    setup("/spec-templates?prj=p1&template=t1");
    fireEvent.click(await screen.findByRole("button", { name: "검사" }, LONG));
    expect((await screen.findByTestId("sdd-template-check", {}, LONG)).textContent).toBe("검사 이슈 1건");
    fireEvent.click(screen.getByText("검사 이슈 1건", { selector: "summary, summary *" }));
    expect(await screen.findByText("서버가 준 문장")).toBeTruthy();
  });

  it("고치면 저장 안 됨, 저장은 If-Match(정의 버전)로 보낸다. 낡았으면 충돌 배너가 나온다", async () => {
    const put = vi.fn().mockRejectedValueOnce(versionConflict()).mockResolvedValue({ value: full("t1", "고침"), version_hash: "h2" });
    const { sddClient } = setup("/spec-templates?prj=p1&template=t1", { sdd: { putSpecTemplate: put } });
    const form = await waitFor(() => {
      const el = document.querySelector<HTMLInputElement>(".sdd-rules-form input[type=text], .sdd-rules-form input:not([type])");
      if (el === null) throw new Error("폼 없음");
      return el;
    }, LONG);
    fireEvent.change(form, { target: { value: "고침" } });
    expect(await screen.findByText("저장 안 됨")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(await screen.findByTestId("sdd-template-conflict", {}, LONG)).toBeTruthy();
    expect(put).toHaveBeenCalledWith("t1", expect.objectContaining({ name: "고침" }), "h1");
    // 덮어쓰기: 최신 버전을 읽어 다시 보낸다
    (sddClient as unknown as { getSpecTemplate: ReturnType<typeof vi.fn> }).getSpecTemplate.mockResolvedValue({ value: full("t1", "남이 고침"), version_hash: "h7" });
    fireEvent.click(screen.getByRole("button", { name: "내 변경으로 덮어쓰기" }));
    await waitFor(() => expect(put).toHaveBeenLastCalledWith("t1", expect.objectContaining({ name: "고침" }), "h7"));
  });

  it("저장하지 않은 변경이 있을 때 다른 틀을 고르면 확인을 받는다", async () => {
    setup("/spec-templates?prj=p1&template=t1");
    const form = await waitFor(() => {
      const el = document.querySelector<HTMLInputElement>(".sdd-rules-form input[type=text], .sdd-rules-form input:not([type])");
      if (el === null) throw new Error("폼 없음");
      return el;
    }, LONG);
    fireEvent.change(form, { target: { value: "고침" } });
    fireEvent.click(await screen.findByRole("button", { name: /^다른 틀/ }));
    expect(await screen.findByText("저장하지 않은 변경이 있습니다")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "머무르기" }));
    expect(screen.queryByText("저장하지 않은 변경이 있습니다")).toBeNull();
  });

  it("뼈대 파일 탭: 파일 없는 문서에 [만들기]가 있고 만들면 초안이 된다", async () => {
    setup("/spec-templates?prj=p1&template=t1&tab=files");
    expect(await screen.findByText("파일 없음", {}, LONG)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "b.md 만들기" }));
    expect(await screen.findByText("저장 안 됨")).toBeTruthy();
    expect(screen.queryByText("파일 없음")).toBeNull();
  });

  it("읽기 전용 사본: 경고 띠와 aria-disabled 저장·새 문서 틀", async () => {
    setup("/spec-templates?prj=p1&template=t1", { projects: [projectView(project("p1"), { config_writable: false })] });
    expect(await screen.findByTestId("sdd-template-readonly", {}, LONG)).toBeTruthy();
    expect(screen.getByRole("button", { name: "저장" }).getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByRole("button", { name: "새 문서 틀" }).getAttribute("aria-disabled")).toBe("true");
  });

  it("정의 모듈이 꺼져 능력(templates)이 없으면 꺼짐 안내만 있고 [새 문서 틀]이 없다", async () => {
    setup("/spec-templates?prj=p1", { info: { ...INFO, capabilities: { ...INFO.capabilities, templates: false } } as SddInfo });
    expect(await screen.findByTestId("sdd-templates-off", {}, LONG)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "새 문서 틀" })).toBeNull();
  });

  it("목록을 읽는 동안 로딩 표시가 있다", async () => {
    setup("/spec-templates?prj=p1", { sdd: { listSpecTemplates: vi.fn(() => new Promise(() => {})) } });
    expect(await screen.findByRole("status", { name: "불러오는 중…" }, LONG)).toBeTruthy();
  });

  it("프로젝트 사본에서는 행마다 [공용에 저장…] 보조 버튼이 있다", async () => {
    setup("/spec-templates?prj=p1");
    expect(await screen.findByRole("button", { name: /공용에 저장.*임의 틀/ }, LONG)).toBeTruthy();
  });
});

describe("새 스펙 대화상자: 공용에서 가져오기 (6R.20c)", () => {
  it("공용 문서 틀 종류(틀 원문의 kind)만 고르기 목록에 나오고, 그 밖의 복사 종류는 나오지 않는다", async () => {
    const { rest } = setup("/specs?prj=p1", {
      rest: {
        listCopyKinds: vi.fn(async () => [{ kind: "k-x", library: true, portable: true }, { kind: "zz-other", library: true, portable: true }]),
        listCopyItems: vi.fn(async (_p: string | null, kind?: string) => (kind === "k-x" ? [{ kind: "k-x", id: "lib-tpl", name: "공용 틀" }] : [{ kind: "zz-other", id: "o1", name: "다른 종류 항목" }])),
      },
    });
    fireEvent.click(await screen.findByRole("button", { name: "새 스펙…" }, LONG));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: /공용에서 가져오기/ }, LONG));
    const copy = await screen.findByRole("dialog", { name: /공용에서 가져오기 —/ }, LONG);
    expect(await within(copy).findByRole("checkbox", { name: "공용 틀" }, LONG)).toBeTruthy();
    expect(within(copy).queryByRole("checkbox", { name: "다른 종류 항목" })).toBeNull();
    expect((rest as unknown as { listCopyKinds: ReturnType<typeof vi.fn> }).listCopyKinds).toHaveBeenCalledWith(null);
  });
});
