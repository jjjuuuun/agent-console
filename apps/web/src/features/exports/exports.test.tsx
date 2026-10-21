import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { agents, resourceTypes } from "../../testing/teamFixtures";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
configure({ asyncUtilTimeout: 10_000 });
vi.setConfig({ testTimeout: 40_000 });

// 형식·종류·옵션은 모두 임의 이름이다(앱은 어느 것도 모른다).
const exporters = [
  {
    id: "fmt-a",
    title: "형식 에이",
    description: "에이 형식 설명",
    kinds: ["agent", "graph"],
    config_schema: { type: "object", properties: { flavor: { type: "string", title: "맛", enum: ["x", "y"], default: "x" }, main: { type: "string", title: "주 항목" } } },
  },
  { id: "fmt-b", title: "형식 비", description: "옵션 없음", kinds: ["graph"], config_schema: { type: "object", properties: {} } },
];
const planFiles = [
  { path: "dir/one.md", size: 1500, media_type: "text/markdown", action: "create" },
  { path: "two.json", size: 20, media_type: "application/json", action: "conflict" },
  { path: "dir/sub/three.txt", size: 5, action: "skip" },
];

function clients(extra: Record<string, unknown> = {}) {
  return createFakeClients({
    listAgents: vi.fn(async () => agents),
    listAgentUsages: vi.fn(async () => []),
    getAgentVersioned: vi.fn(async () => ({ value: agents[0], version_hash: "ah1" })),
    getAgentEffectiveSettings: vi.fn(async () => ({ value: {}, provenance: {}, layers: [] })),
    listBackends: vi.fn(async () => []),
    listResourceTypes: vi.fn(async () => resourceTypes),
    listResources: vi.fn(async () => []),
    listGraphs: vi.fn(async () => []),
    listExporters: vi.fn(async () => exporters),
    listExportRoots: vi.fn(async () => []),
    planExport: vi.fn(async () => ({ files: planFiles, warnings: [] })),
    ...extra,
  });
}

async function openDialog(extra: Record<string, unknown> = {}) {
  const c = clients(extra);
  mountApp(c.clients, "/agents/ag1");
  fireEvent.click(await screen.findByRole("button", { name: /메뉴/ }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "내보내기…" }));
  const dialog = await screen.findByRole("dialog", { name: "내보내기" });
  return { ...c, dialog };
}

async function toStep(dialog: HTMLElement, stepName: string) {
  const order = ["항목·옵션", "미리보기", "내보낼 곳"];
  for (const name of order) {
    const next = within(dialog).getByRole("button", { name: /^다음$/ });
    await waitFor(() => expect((next as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(next);
    await waitFor(() => expect(within(dialog).getByRole("listitem", { current: "step" }).textContent).toContain(name));
    if (name === stepName) return;
  }
}

describe("내보내기: 형식·항목·옵션", () => {
  it("① 형식은 GET /exporters 카드로, 고르기 전에는 다음이 막히고 종류 칩은 서버 문자열이다", async () => {
    const { dialog } = await openDialog();
    const group = await within(dialog).findByRole("radiogroup", { name: "내보내기 형식" });
    expect(within(group).getAllByRole("radio")).toHaveLength(2);
    expect(within(group).getByText("에이 형식 설명")).toBeTruthy();
    expect((within(dialog).getByRole("button", { name: /^다음$/ }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(within(group).getByRole("radio", { name: /형식 에이/ }));
    expect((within(dialog).getByRole("button", { name: /^다음$/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("카드가 1개면 미리 선택되지만 단계를 건너뛰지 않는다", async () => {
    const { dialog } = await openDialog({ listExporters: vi.fn(async () => [exporters[0]]) });
    const radio = await within(dialog).findByRole("radio", { name: /형식 에이/ });
    expect(radio.getAttribute("aria-checked")).toBe("true");
    expect(within(dialog).getByRole("listitem", { current: "step" }).textContent).toContain("형식");
  });

  it("형식이 하나도 없으면 플러그인 안내, 목록 오류면 오류 블록과 다시 시도", async () => {
    const empty = await openDialog({ listExporters: vi.fn(async () => []) });
    expect(await within(empty.dialog).findByText(/내보내기 형식이 설치되어 있지 않습니다/)).toBeTruthy();
    cleanup();
    const failing = vi.fn().mockRejectedValueOnce(new ApiError(500, { code: "boom", message: "서버 오류" })).mockResolvedValue(exporters);
    const { dialog } = await openDialog({ listExporters: failing });
    expect(await within(dialog).findByText("형식 목록을 불러오지 못했습니다")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "다시 시도" }));
    expect(await within(dialog).findByRole("radiogroup", { name: "내보내기 형식" })).toBeTruthy();
  });

  it("② 현재 항목이 미리 담기고, 형식이 지원하지 않는 종류는 사유와 제외 버튼, 옵션은 바꾼 값만 담긴다", async () => {
    const { dialog, rest } = await openDialog({ listExporters: vi.fn(async () => [exporters[1], exporters[0]]) });
    fireEvent.click(await within(dialog).findByRole("radio", { name: /형식 비/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: /^다음$/ }));
    const items = await within(dialog).findByRole("region", { name: "내보낼 정의" });
    expect(within(items).getByText("첫째 에이전트")).toBeTruthy();
    expect(within(items).getByText("이 형식이 지원하지 않는 종류")).toBeTruthy();
    expect((within(dialog).getByRole("button", { name: /^다음$/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(items).getByRole("button", { name: /제외/ })).toBeTruthy();
    fireEvent.click(within(items).getByRole("button", { name: /제외/ }));
    expect(within(items).getByText("내보낼 항목을 하나 이상 고르세요")).toBeTruthy();
    expect(within(dialog).getByText("이 형식에는 옵션이 없습니다")).toBeTruthy();
    expect(rest.planExport).not.toHaveBeenCalled();
  });

  it("옵션 폼은 스키마로 그리고 사용자가 만진 키만 미리보기 요청 options에 담는다", async () => {
    const { dialog, rest } = await openDialog();
    fireEvent.click(await within(dialog).findByRole("radio", { name: /형식 에이/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: /^다음$/ }));
    const main = await within(dialog).findByLabelText("주 항목");
    fireEvent.change(main, { target: { value: "n1" } });
    fireEvent.blur(main);
    fireEvent.click(within(dialog).getByRole("button", { name: /^다음$/ }));
    await waitFor(() => expect(rest.planExport).toHaveBeenCalled());
    expect(rest.planExport).toHaveBeenLastCalledWith({ exporter: "fmt-a", items: [{ kind: "agent", id: "ag1" }], options: { main: "n1" } });
  });
});

describe("내보내기: 미리보기", () => {
  async function toPreview(extra: Record<string, unknown> = {}) {
    const c = await openDialog(extra);
    fireEvent.click(await within(c.dialog).findByRole("radio", { name: /형식 에이/ }));
    await toStep(c.dialog, "미리보기");
    return c;
  }

  it("파일 트리에 경로·크기·동작 배지(아이콘+텍스트)와 요약이 보이고 평면 보기로 바꿀 수 있다", async () => {
    const { dialog } = await toPreview();
    const tree = await within(dialog).findByRole("tree", { name: "내보낼 파일" });
    expect(within(tree).getAllByRole("treeitem").length).toBeGreaterThanOrEqual(5);
    expect(within(dialog).getByText(/파일 3개 · 합계 1\.5 KB · 새로 만듦 1 · 건너뜀 1 · 충돌 1/)).toBeTruthy();
    expect(within(tree).getByText("충돌")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "평면" }));
    expect(within(dialog).getByText("dir/sub/three.txt")).toBeTruthy();
  });

  it("경고는 서버 메시지 그대로 보이고 차단하지 않지만 severity=error면 다음이 막힌다", async () => {
    const warn = { severity: "warning", code: "export.some_code", message: "서버가 준 경고 문장" };
    const warned = await toPreview({ planExport: vi.fn(async () => ({ files: planFiles, warnings: [warn] })) });
    const region = await within(warned.dialog).findByRole("status", { name: "경고" });
    expect(within(region).getByText("서버가 준 경고 문장")).toBeTruthy();
    expect(within(region).getByText("export.some_code")).toBeTruthy();
    expect((within(warned.dialog).getByRole("button", { name: /^다음$/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("severity=error 경고가 있으면 다음이 막히고 이유가 보인다", async () => {
    const err = { severity: "error", code: "export.some_error", message: "주 항목이 없습니다" };
    const { dialog } = await toPreview({ planExport: vi.fn(async () => ({ files: planFiles, warnings: [err] })) });
    await within(dialog).findByText("주 항목이 없습니다");
    const next = within(dialog).getByRole("button", { name: /^다음$/ }) as HTMLButtonElement;
    expect(next.disabled).toBe(true);
    expect(next.title).toContain("내보낼 수 없다고 한 항목");
  });

  it("빈 플랜은 안내와 옵션으로 돌아가는 버튼을 보인다", async () => {
    const { dialog } = await toPreview({ planExport: vi.fn(async () => ({ files: [], warnings: [] })) });
    expect(await within(dialog).findByText("내보낼 파일이 없습니다. 항목이나 옵션을 바꿔 보세요.")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: /옵션으로/ }));
    await waitFor(() => expect(within(dialog).getByRole("listitem", { current: "step" }).textContent).toContain("항목·옵션"));
  });

  it("서버 422(옵션 위치)면 ②로 돌아가 필드에 오류를 붙인다", async () => {
    const bad = vi.fn(async () => {
      throw new ApiError(422, { code: "validation_failed", message: "검증", details: { issues: [{ path: "/options/main", message: "없는 항목입니다" }] } });
    });
    const c = await openDialog({ planExport: bad });
    fireEvent.click(await within(c.dialog).findByRole("radio", { name: /형식 에이/ }));
    fireEvent.click(within(c.dialog).getByRole("button", { name: /^다음$/ }));
    fireEvent.click(await within(c.dialog).findByRole("button", { name: /^다음$/ }));
    await waitFor(() => expect(within(c.dialog).getByRole("listitem", { current: "step" }).textContent).toContain("항목·옵션"));
    expect(await within(c.dialog).findByText(/없는 항목입니다/)).toBeTruthy();
    expect(within(c.dialog).getByText(/이전 단계로 돌아왔습니다/)).toBeTruthy();
  });
});

describe("내보내기: 내보낼 곳", () => {
  async function toDest(extra: Record<string, unknown> = {}) {
    const c = await openDialog(extra);
    fireEvent.click(await within(c.dialog).findByRole("radio", { name: /형식 에이/ }));
    await toStep(c.dialog, "내보낼 곳");
    return c;
  }

  it("루트가 없으면 폴더 쓰기 선택지를 그리지 않는다(보관 파일만)", async () => {
    const { dialog } = await toDest();
    expect(await within(dialog).findByRole("radio", { name: /보관 파일\(zip\) 받기/ })).toBeTruthy();
    expect(within(dialog).queryByRole("radio", { name: /폴더에 쓰기/ })).toBeNull();
  });

  it("보관 파일은 fetch -> Blob 다운로드이며 파일 이름은 응답에서 온다(링크 직접 이동 없음)", async () => {
    const create = vi.fn(() => "blob:x");
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const download = vi.fn(async () => ({ blob: new Blob(["PK"]), filename: "서버가-준.zip" }));
    const { dialog, rest } = await toDest({ downloadExportArchive: download });
    fireEvent.click(within(dialog).getByRole("button", { name: "내보내기" }));
    expect(await within(dialog).findByText(/보관 파일 서버가-준\.zip/)).toBeTruthy();
    expect(rest.downloadExportArchive).toHaveBeenCalledWith({ exporter: "fmt-a", items: [{ kind: "agent", id: "ag1" }], options: {} });
    expect(create).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
  });

  it("폴더 쓰기: 기본 충돌 처리는 fail, 하위 폴더 즉시 검사, 목적지를 싣고 다시 계산, 결과 화면", async () => {
    const roots = [{ id: "r1", label: "작업 폴더", path: "/srv/out" }, { id: "r2", label: "", path: "" }];
    const write = vi.fn(async () => ({ files: [{ path: "dir/one.md", size: 1500, action: "create" }, { path: "two.json", size: 20, action: "skip" }], warnings: [] }));
    const { dialog, rest } = await toDest({ listExportRoots: vi.fn(async () => roots), writeExport: write });
    fireEvent.click(await within(dialog).findByRole("radio", { name: /폴더에 쓰기/ }));
    expect((within(dialog).getByRole("radio", { name: /충돌하면 멈춤/ }) as HTMLInputElement).checked).toBe(true);
    const sub = within(dialog).getByLabelText("하위 폴더");
    fireEvent.change(sub, { target: { value: "../escape" } });
    expect(within(dialog).getByText("`..`은 쓸 수 없습니다")).toBeTruthy();
    expect((within(dialog).getByRole("button", { name: "내보내기" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(sub, { target: { value: "sub/dir" } });
    await waitFor(() => expect(rest.planExport).toHaveBeenLastCalledWith({ exporter: "fmt-a", items: [{ kind: "agent", id: "ag1" }], options: {}, root: "r1", subdir: "sub/dir" }));
    expect(await within(dialog).findByText("지금 충돌하는 파일 1개")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "내보내기" }));
    await waitFor(() => expect(write).toHaveBeenCalledWith({ exporter: "fmt-a", items: [{ kind: "agent", id: "ag1" }], options: {}, root: "r1", subdir: "sub/dir", on_conflict: "fail" }));
    expect(await within(dialog).findByText("쓴 파일 1개 · 건너뜀 1개")).toBeTruthy();
    expect(within(dialog).getByText(/작업 폴더 \(\/srv\/out\)/)).toBeTruthy();
  });

  it("덮어쓰기는 개수가 담긴 확인(기본 포커스 취소)을 거치고, 취소하면 쓰지 않는다", async () => {
    const write = vi.fn(async () => ({ files: [], warnings: [] }));
    const { dialog } = await toDest({ listExportRoots: vi.fn(async () => [{ id: "r1", label: "루트", path: "/p" }]), writeExport: write });
    fireEvent.click(await within(dialog).findByRole("radio", { name: /폴더에 쓰기/ }));
    fireEvent.click(within(dialog).getByRole("radio", { name: /덮어쓰기/ }));
    await waitFor(() => expect((within(dialog).getByRole("button", { name: "내보내기" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(within(dialog).getByRole("button", { name: "내보내기" }));
    const confirm = await screen.findByRole("dialog", { name: "덮어쓰기 확인" });
    expect(within(confirm).getByText("기존 파일 1개를 덮어씁니다. 되돌릴 수 없습니다.")).toBeTruthy();
    expect(document.activeElement).toBe(within(confirm).getByRole("button", { name: "취소" }));
    fireEvent.click(within(confirm).getByRole("button", { name: "취소" }));
    expect(write).not.toHaveBeenCalled();
  });

  it("409 충돌은 서버 메시지와 충돌 경로를 보이고 입력을 유지한다, 422 /subdir는 필드 오류", async () => {
    const write = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(409, { code: "already_exists", message: "이미 있습니다", details: { paths: ["two.json"] } }))
      .mockRejectedValueOnce(new ApiError(422, { code: "validation_failed", message: "거부", details: { issues: [{ path: "/subdir", message: "링크를 통과할 수 없습니다" }] } }));
    const { dialog } = await toDest({ listExportRoots: vi.fn(async () => [{ id: "r1", label: "루트", path: "/p" }]), writeExport: write });
    fireEvent.click(await within(dialog).findByRole("radio", { name: /폴더에 쓰기/ }));
    fireEvent.change(within(dialog).getByLabelText("하위 폴더"), { target: { value: "keep" } });
    await waitFor(() => expect((within(dialog).getByRole("button", { name: "내보내기" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(within(dialog).getByRole("button", { name: "내보내기" }));
    const alert = await within(dialog).findByRole("alert");
    expect(within(alert).getByText("이미 있습니다")).toBeTruthy();
    expect(within(alert).getByText("two.json")).toBeTruthy();
    expect((within(dialog).getByLabelText("하위 폴더") as HTMLInputElement).value).toBe("keep");
    fireEvent.click(within(dialog).getByRole("button", { name: "내보내기" }));
    expect(await within(dialog).findByText("링크를 통과할 수 없습니다")).toBeTruthy();
  });
});

describe("내보내기: 진입점과 키보드", () => {
  beforeEach(() => {
    localStorage.clear();
  });
  it("마지막으로 고른 형식을 기억하고 Ctrl+Enter로 다음 단계, Esc로 닫는다", async () => {
    const first = await openDialog();
    fireEvent.click(await within(first.dialog).findByRole("radio", { name: /형식 비/ }));
    fireEvent.keyDown(within(first.dialog).getByRole("radiogroup"), { key: "Enter", ctrlKey: true });
    await waitFor(() => expect(within(first.dialog).getByRole("listitem", { current: "step" }).textContent).toContain("항목·옵션"));
    fireEvent.keyDown(within(first.dialog).getByRole("region", { name: "내보낼 정의" }), { key: "Enter", ctrlKey: true, shiftKey: true });
    await waitFor(() => expect(within(first.dialog).getByRole("listitem", { current: "step" }).textContent).toContain("형식"));
    fireEvent.keyDown(first.dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "내보내기" })).toBeNull());
  });

  it("저장 안 된 변경이 있으면 안내와 [먼저 저장]이 보인다", async () => {
    const { dialog } = await (async () => {
      const c = clients();
      mountApp(c.clients, "/agents/ag1");
      fireEvent.change(await screen.findByLabelText("역할", { selector: "input" }), { target: { value: "바꿈" } });
      fireEvent.click(await screen.findByRole("button", { name: /메뉴/ }));
      fireEvent.click(await screen.findByRole("menuitem", { name: "내보내기…" }));
      return { dialog: await screen.findByRole("dialog", { name: "내보내기" }) };
    })();
    expect(within(dialog).getByText(/저장된 버전을 내보냅니다/)).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "먼저 저장" })).toBeTruthy();
  });
});
