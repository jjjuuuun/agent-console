import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import type { PortDef } from "@agent-console/contracts";
import type { ProjectView } from "@agent-console/contracts/projects";
import { mountApp } from "../../testing/screenHarness";
import { createFakeClients, createFakeRest } from "../../testing/fakes";
import { DEFINITION_KINDS } from "../library";
import { buildRunInput, initialInputValues, inputIssues, portKind, portRequired } from "./runInputLib";

afterEach(cleanup);

const MODULES = [{ id: "m-1", kind: "k", version: "0.0.1", status: "active", web_roles: ["conversations", "runs", "projects", "definitions:graph"] }];
const view = (id: string, over: Partial<ProjectView> = {}): ProjectView =>
  ({
    project: { id, name: `프로젝트 ${id}`, folder: `/home/me/work/${id}`, description: "" },
    status: "ready",
    config_writable: true,
    kinds: [DEFINITION_KINDS.graph],
    config_dir: ".cfg-dir",
    records_state: "ready",
    records_writable: true,
    version_hash: "h1",
    ...over,
  }) as ProjectView;
const graph = (id: string, name = id) => ({ id, name, version_hash: "v", node_count: 3, edge_count: 2, entry_labels: ["입구"], validation: null });

function mount(path: string, opts: { views?: ProjectView[]; inputs?: PortDef[]; createRun?: (b: unknown) => Promise<unknown> } = {}) {
  const createRun = vi.fn(opts.createRun ?? (async () => ({ id: "r-new", graph_id: "g1", graph_version: "v", status: "queued", input: {}, origin: "web", created_at: 1 })));
  const made = createFakeClients({
    listModules: vi.fn(async () => MODULES),
    listProjects: vi.fn(async () => opts.views ?? [view("a")]),
    listRuns: vi.fn(async () => []),
    listConversations: vi.fn(async () => []),
    createRun,
  });
  made.space.mockImplementation((() =>
    createFakeRest({
      listGraphs: vi.fn(async () => [graph("g1", "리뷰 팀"), graph("g2", "문서 팀")]),
      getGraph: vi.fn(async (id: string) => ({ graph: { id, name: id, nodes: [], edges: [], ...(opts.inputs === undefined ? {} : { inputs: opts.inputs }) }, version_hash: "v" })),
    })) as never);
  return { ...made, createRun, ...mountApp(made.clients, path) };
}

describe("입력 칸 규칙(runInputLib)", () => {
  const free: PortDef = { name: "foo" };
  const withDefault: PortDef = { name: "n", schema: { type: "integer", default: 3 } };
  const noDefault: PortDef = { name: "s", schema: { type: "string" } };
  const odd: PortDef = { name: "x", schema: { description: "모양 없음" } };
  it("종류와 필수 판정은 한 표", () => {
    expect([free, withDefault, noDefault, odd].map(portKind)).toEqual(["text", "schema", "schema", "json"]);
    expect([free, withDefault, noDefault, odd].map(portRequired)).toEqual([true, false, true, true]);
  });
  it("포트 0개 → input {}, 임의 이름 foo로 만든다, 기본값은 선택", () => {
    expect(buildRunInput([], {})).toEqual({});
    expect(inputIssues([free, withDefault], initialInputValues([free, withDefault]))).toEqual({ foo: { kind: "required" } });
    expect(buildRunInput([free, withDefault], initialInputValues([free, withDefault], { foo: "hi" }))).toEqual({ foo: "hi", n: 3 });
    expect(inputIssues([odd], { x: "{bad" })).toEqual({ x: { kind: "json" } });
    expect(buildRunInput([odd], { x: "{\"a\":1}" })).toEqual({ x: { a: 1 } });
  });
});

describe("새 실행 대화상자(프로젝트 홈의 [실행…] → /runs?new=1)", () => {
  it("스키마 없는 포트: 멀티라인 필수 → 비면 막히고, 채우면 origin web + project_id로 시작해 상세로 이동", async () => {
    const { createRun, router } = mount("/runs?prj=a&new=1", { inputs: [{ name: "foo", label: "요청", description: "무엇을 할지" }] });
    const dialog = await screen.findByRole("dialog", { name: "새 실행" });
    const box = await within(dialog).findByRole("textbox", { name: /요청/ });
    const start = within(dialog).getByRole("button", { name: "실행 시작" });
    await waitFor(() => expect(start.getAttribute("aria-disabled")).toBe("true"));
    fireEvent.click(start);
    expect(createRun).not.toHaveBeenCalled();
    fireEvent.change(box, { target: { value: "로그인 만들기" } });
    await waitFor(() => expect(start.getAttribute("aria-disabled")).toBeNull());
    fireEvent.click(start);
    await waitFor(() => expect(createRun).toHaveBeenCalled());
    expect(createRun.mock.calls[0]?.[0]).toEqual({ graph_id: "g1", input: { foo: "로그인 만들기" }, project_id: "a", origin: "web" });
    await waitFor(() => expect(router.state.location.pathname).toBe("/runs/r-new"));
  });

  it("포트 0개: 안내 문구 + input {} 로 바로 시작", async () => {
    const { createRun } = mount("/runs?prj=a&new=1", { inputs: [] });
    const dialog = await screen.findByRole("dialog", { name: "새 실행" });
    expect(await within(dialog).findByText("이 구성은 입력을 받지 않습니다.")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "실행 시작" }));
    await waitFor(() => expect(createRun).toHaveBeenCalled());
    expect(createRun.mock.calls[0]?.[0]).toMatchObject({ input: {}, project_id: "a", origin: "web" });
  });

  it("?new=1은 한 번 읽고 지운다", async () => {
    const { router } = mount("/runs?prj=a&new=1", { inputs: [] });
    await screen.findByRole("dialog", { name: "새 실행" });
    await waitFor(() => expect(router.state.location.search).not.toContain("new="));
  });

  it("기록을 쓸 수 없는 폴더는 [실행 시작]이 aria-disabled + 이유이고 POST /runs가 나가지 않는다", async () => {
    const { createRun } = mount("/runs?prj=a&new=1", { views: [view("a", { records_writable: false })], inputs: [] });
    const dialog = await screen.findByRole("dialog", { name: "새 실행" });
    const start = within(dialog).getByRole("button", { name: "실행 시작" });
    expect(start.getAttribute("aria-disabled")).toBe("true");
    expect((await within(dialog).findAllByText("이 폴더에 쓸 수 없어 대화·실행 기록을 저장할 수 없습니다")).length).toBeGreaterThan(0);
    fireEvent.click(start);
    expect(createRun).not.toHaveBeenCalled();
  });

  it("서버 422 not_imported(in_library) → [가져와서 실행] 배너, 입력은 유지된다", async () => {
    const err = new ApiError(422, { code: "project.not_imported", message: "m", details: { project_id: "a", kind: DEFINITION_KINDS.graph, id: "g1", in_library: true } });
    mount("/runs?prj=a&new=1", { inputs: [{ name: "foo", label: "요청" }], createRun: async () => { throw err; } });
    const dialog = await screen.findByRole("dialog", { name: "새 실행" });
    const box = await within(dialog).findByRole("textbox", { name: /요청/ });
    fireEvent.change(box, { target: { value: "유지" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "실행 시작" }));
    expect(await within(dialog).findByRole("button", { name: "가져와서 실행" })).toBeTruthy();
    expect((within(dialog).getByRole("textbox", { name: /요청/ }) as HTMLTextAreaElement).value).toBe("유지");
  });

  it("서버 입력 오류(포트 이름 기준)는 같은 칸에 붙는다", async () => {
    const err = new ApiError(422, { code: "validation_failed", message: "m", details: { issues: [{ field: "foo", message: "너무 짧습니다" }] } });
    mount("/runs?prj=a&new=1", { inputs: [{ name: "foo", label: "요청" }], createRun: async () => { throw err; } });
    const dialog = await screen.findByRole("dialog", { name: "새 실행" });
    fireEvent.change(await within(dialog).findByRole("textbox", { name: /요청/ }), { target: { value: "x" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "실행 시작" }));
    expect(await within(dialog).findByText("너무 짧습니다")).toBeTruthy();
  });
});

describe("실행 기록 머리", () => {
  it("[새 실행] primary와 새로 고침 아이콘 버튼이 있고 글자 버튼 '새로 고침'은 없다", async () => {
    mount("/runs?prj=a", { inputs: [] });
    expect(await screen.findByRole("button", { name: "새 실행" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "새로 고침" })).toBeTruthy();
    expect(screen.queryByText("새로 고침", { selector: "button" })).toBeNull();
  });
});
