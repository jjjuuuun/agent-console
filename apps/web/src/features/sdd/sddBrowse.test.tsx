import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import type { ModuleInfo, Project, ProjectView } from "@agent-console/contracts";
import type { ImportFileListing, SddInfo, SpecSummary, SpecView } from "@agent-console/contracts/sdd";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { SpecExportDialog } from "./SpecExportDialog";
import { SpecImportDialog } from "./SpecImportDialog";
import { filterSpecs, parseSort } from "./SpecListScreen";

afterEach(cleanup);
const LONG = { timeout: 15_000 };

/** 임의 이름 트리(루트 = 빈 문자열). 폴더·파일 이름은 데이터다. */
const TREE: Record<string, { dirs: string[]; files: string[] }> = {
  "": { dirs: ["공통", "문서"], files: ["root.md"] },
  문서: { dirs: ["하위"], files: ["a.md", "b.md"] },
  "문서/하위": { dirs: [], files: ["c.md"] },
  공통: { dirs: [], files: [] },
};
const listing = (path: string): ImportFileListing => ({
  path,
  dirs: (TREE[path]?.dirs ?? []).map((name) => ({ name })),
  files: (TREE[path]?.files ?? []).map((name) => ({ name, size: 10 })),
});
const settle = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });

describe("SpecImportDialog: 트리 고르기", () => {
  it("열면 루트 폴더 목록·파일을 보이고, 폴더로 들어가면 그 폴더 파일로 바뀌며 제출 경로가 상대 경로다", async () => {
    const loadFiles = vi.fn(async (p: string) => listing(p));
    const onSubmit = vi.fn(async () => undefined);
    render(<SpecImportDialog open onClose={() => undefined} loadFiles={loadFiles} onSubmit={onSubmit} />);
    await settle();
    expect(loadFiles).toHaveBeenCalledWith("");
    expect(screen.getByText("root.md")).toBeTruthy();
    const tree = screen.getByRole("listbox", { name: /./ });
    fireEvent.keyDown(tree, { key: "ArrowDown" });
    fireEvent.keyDown(tree, { key: "Enter" });
    await settle();
    expect(loadFiles).toHaveBeenLastCalledWith("문서");
    expect(screen.getByText("b.md")).toBeTruthy();
    expect(screen.queryByText("root.md")).toBeNull();
    expect((screen.getByLabelText("경로를 직접 입력") as HTMLInputElement).value).toBe("문서");
    fireEvent.change(screen.getByLabelText(/이름/, { selector: "input[aria-required]" }), { target: { value: "새 스펙" } });
    fireEvent.click(screen.getByRole("button", { name: "가져오기" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ name: "새 스펙", files: ["문서/a.md", "문서/b.md"] }));
  });

  it("루트에서는 위로 갈 수 없다(←는 아무 일도 없다)", async () => {
    const loadFiles = vi.fn(async (p: string) => listing(p));
    render(<SpecImportDialog open onClose={() => undefined} loadFiles={loadFiles} onSubmit={async () => undefined} />);
    await settle();
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "ArrowLeft" });
    await settle();
    expect(loadFiles).toHaveBeenCalledTimes(1);
  });

  it("직접 입력한 경로를 [목록 불러오기]로 열고, 서버 거절(422 folders.invalid_path)은 폴더 칸 아래에 보인다", async () => {
    const loadFiles = vi.fn(async (p: string) => {
      if (p === "../밖") throw new ApiError(422, { code: "folders.invalid_path", message: "폴더 밖입니다", details: { reason: "outside" } });
      return listing(p);
    });
    render(<SpecImportDialog open onClose={() => undefined} loadFiles={loadFiles} onSubmit={async () => undefined} />);
    await settle();
    const input = screen.getByLabelText("경로를 직접 입력");
    fireEvent.change(input, { target: { value: "문서/하위" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await settle();
    expect(screen.getByText("c.md")).toBeTruthy();
    fireEvent.change(input, { target: { value: "../밖" } });
    fireEvent.click(screen.getByRole("button", { name: "목록 불러오기" }));
    await settle();
    expect((await screen.findAllByRole("alert")).some((a) => a.textContent !== "")).toBe(true);
    expect(screen.queryByText("c.md")).toBeNull();
  });

  it("한글 조합 중 Enter는 불러오기를 시작하지 않는다", async () => {
    const loadFiles = vi.fn(async (p: string) => listing(p));
    render(<SpecImportDialog open onClose={() => undefined} loadFiles={loadFiles} onSubmit={async () => undefined} />);
    await settle();
    const input = screen.getByLabelText("경로를 직접 입력");
    fireEvent.change(input, { target: { value: "문" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    await settle();
    expect(loadFiles).toHaveBeenCalledTimes(1);
  });
});

describe("SpecExportDialog: 대상 폴더 트리", () => {
  it("폴더로 들어가면 대상 경로가 채워지고 그 경로로 제출한다", async () => {
    const loadDirs = vi.fn(async (p: string) => listing(p));
    const onSubmit = vi.fn(async () => ({ to_dir: "문서", written: ["a.md"], skipped: [] }));
    render(<SpecExportDialog open onClose={() => undefined} loadDirs={loadDirs} onSubmit={onSubmit} />);
    await settle();
    expect(screen.getByRole("button", { name: "내보내기" }).getAttribute("aria-disabled")).toBe("true");
    const tree = screen.getByRole("listbox");
    fireEvent.keyDown(tree, { key: "ArrowDown" });
    fireEvent.keyDown(tree, { key: "Enter" });
    await settle();
    expect((screen.getByLabelText("경로를 직접 입력") as HTMLInputElement).value).toBe("문서");
    fireEvent.click(screen.getByRole("button", { name: "내보내기" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ to_dir: "문서", overwrite: false }));
  });

  it("loadDirs가 없으면 트리 없이 입력만 쓴다", () => {
    render(<SpecExportDialog open onClose={() => undefined} onSubmit={async () => ({ to_dir: "x", written: [], skipped: [] })} />);
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByLabelText(/대상 폴더/)).toBeTruthy();
  });
});

describe("스펙 목록 정렬 순수 함수", () => {
  const specs: SpecSummary[] = [
    { id: "a", name: "다", updated_at: 1 },
    { id: "b", name: "가", updated_at: 3 },
    { id: "c", name: "나", updated_at: 2 },
  ];
  it("기본은 갱신 내림차순, 이름 오름·내림", () => {
    expect(filterSpecs(specs, "", new Set(), false).map((s) => s.id)).toEqual(["b", "c", "a"]);
    expect(filterSpecs(specs, "", new Set(), false, { id: "name", direction: "asc" }).map((s) => s.id)).toEqual(["b", "c", "a"]);
    expect(filterSpecs(specs, "", new Set(), false, { id: "name", direction: "desc" }).map((s) => s.id)).toEqual(["a", "c", "b"]);
    expect(filterSpecs(specs, "", new Set(), false, { id: "updated", direction: "asc" }).map((s) => s.id)).toEqual(["a", "c", "b"]);
  });
  it("주소 값 해석: 모르는 열·방향은 기본으로", () => {
    expect(parseSort("name:asc")).toEqual({ id: "name", direction: "asc" });
    expect(parseSort("zzz:asc")).toEqual({ id: "updated", direction: "desc" });
    expect(parseSort("name:up")).toEqual({ id: "updated", direction: "desc" });
    expect(parseSort(null)).toEqual({ id: "updated", direction: "desc" });
  });
});

describe("스펙 목록 화면: 열 머리 정렬·행 메뉴", () => {
  const mod = (roles: string[]): ModuleInfo => ({ id: "m-any", kind: "k", version: "0.0.1", status: "active", web_roles: roles });
  const project: Project = { id: "p1", name: "P1", folder: "/w/p1" } as Project;
  const pv = { project, status: "ready", config_writable: true, kinds: [], records_writable: true, config_dir: ".cfg" } as unknown as ProjectView;
  const INFO = { spec_root: ".cfg/specs", limits: { max_bulk_start: 10 }, capabilities: { runs: true, templates: true, import_export: true, verification: false, automation: false }, writable: true } as SddInfo;
  const sum = (id: string, name: string, updated: number): SpecSummary => ({ id, name, directory: `.cfg/specs/${id}`, updated_at: updated, documents: [] });
  const view = (id: string, name: string): SpecView => ({ spec: { kind: "k", id, name, documents: [], rules: {} }, index: { tasks: [], stages: [] }, version_hash: "v1", directory: `.cfg/specs/${id}`, task_statuses: [], document_states: [], issues: [] }) as unknown as SpecView;

  function setup(path: string) {
    const { clients, sddClient } = createFakeClients(
      { listModules: vi.fn(async () => [mod(["sdd", "projects"])]), listProjects: vi.fn(async () => [pv]) },
      {},
      {
        getSddInfo: vi.fn(async () => INFO),
        listSpecs: vi.fn(async () => [sum("s1", "다람쥐", 100), sum("s2", "가지", 300), sum("s3", "나비", 200)]),
        getSpec: vi.fn(async (id: string) => ({ value: view(id, "이름"), version_hash: "v1" })),
        deleteSpec: vi.fn(async () => undefined),
        listImportFiles: vi.fn(async (p?: string) => listing(p ?? "")),
      },
    );
    return { ...mountApp(clients, path), sdd: sddClient as unknown as Record<string, ReturnType<typeof vi.fn>> };
  }
  const order = () => screen.getAllByRole("button", { name: /다람쥐|가지|나비/ }).filter((b) => b.className.includes("ac-sdd-spec")).map((b) => b.querySelector(".ac-sdd-spec-name")?.textContent);

  it("열 머리 aria-sort와 URL: 기본 갱신 내림차순, 이름을 누르면 오름차순이 되고 주소에 남는다", async () => {
    const { router } = setup("/specs?prj=p1");
    await screen.findByText("가지", {}, LONG);
    expect(screen.getByRole("columnheader", { name: /갱신/ }).getAttribute("aria-sort")).toBe("descending");
    expect(order()).toEqual(["가지", "나비", "다람쥐"]);
    fireEvent.click(within(screen.getByRole("columnheader", { name: /이름/ })).getByRole("button"));
    await waitFor(() => expect(router.state.location.search).toContain("sort=name%3Aasc"), LONG);
    expect(screen.getByRole("columnheader", { name: /이름/ }).getAttribute("aria-sort")).toBe("ascending");
    expect(order()).toEqual(["가지", "나비", "다람쥐"]);
    fireEvent.click(within(screen.getByRole("columnheader", { name: /이름/ })).getByRole("button"));
    await waitFor(() => expect(screen.getByRole("columnheader", { name: /이름/ }).getAttribute("aria-sort")).toBe("descending"), LONG);
    expect(order()).toEqual(["다람쥐", "나비", "가지"]);
  });

  it("주소의 sort로 처음부터 정렬된다", async () => {
    setup("/specs?prj=p1&sort=updated%3Aasc");
    await screen.findByText("가지", {}, LONG);
    expect(screen.getByRole("columnheader", { name: /갱신/ }).getAttribute("aria-sort")).toBe("ascending");
    expect(order()).toEqual(["다람쥐", "나비", "가지"]);
  });

  it("행 ⋯ 메뉴: 키보드로 열어 삭제를 고르면 확인 후 그 스펙만 삭제한다", async () => {
    const { sdd } = setup("/specs?prj=p1");
    await screen.findByText("가지", {}, LONG);
    const trigger = screen.getByRole("button", { name: /가지 동작/ });
    trigger.focus();
    fireEvent.click(trigger);
    const menu = await screen.findByRole("menu", {}, LONG);
    for (const name of [/열기/, /내보내기/, /이름 바꾸기/, /경로 복사/, /삭제/]) expect(within(menu).getByRole("menuitem", { name })).toBeTruthy();
    fireEvent.click(within(menu).getByRole("menuitem", { name: /삭제/ }));
    const dialog = await screen.findByRole("alertdialog", {}, LONG).catch(() => screen.findByRole("dialog", {}, LONG));
    fireEvent.click(within(dialog).getByRole("button", { name: "삭제" }));
    await waitFor(() => expect(sdd.deleteSpec).toHaveBeenCalledWith("s2", "v1"), LONG);
  });

  it("행 ⋯ 메뉴에서 내보내기를 고르면 트리가 있는 대화상자가 열린다", async () => {
    const { sdd } = setup("/specs?prj=p1");
    await screen.findByText("가지", {}, LONG);
    fireEvent.click(screen.getByRole("button", { name: /나비 동작/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /내보내기/ }, LONG));
    const dialog = await screen.findByRole("dialog", { name: "문서 내보내기" }, LONG);
    expect(await within(dialog).findByRole("listbox", {}, LONG)).toBeTruthy();
    expect(sdd.listImportFiles).toHaveBeenCalledWith("");
  });
});
