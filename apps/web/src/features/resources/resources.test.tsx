import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createFakeClients, versionConflict } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { resourceTypes } from "../../testing/teamFixtures";

afterEach(cleanup);

const summaries = [
  { id: "d1", type: "rt-doc", name: "문서 하나", description: "설명", version_hash: "v1", has_content: true, usage_count: 2 },
  { id: "c1", type: "rt-cfg", name: "설정 하나", version_hash: "v2", usage_count: 0 },
  { id: "u1", type: "rt-gone", name: "모르는 종류", version_hash: "v3", usage_count: 0 },
];
const docs: Record<string, unknown> = {
  d1: { kind: "resource", id: "d1", type: "rt-doc", name: "문서 하나", description: "설명", content: { file: "d1.md", media_type: "text/markdown" }, attributes: { imported_from: { source: "x", path: "/원본/a.md", sha256: "abcdef1234567890" } } },
  c1: { kind: "resource", id: "c1", type: "rt-cfg", name: "설정 하나", config: { cmd: "run" } },
  u1: { kind: "resource", id: "u1", type: "rt-gone", name: "모르는 종류", config: { a: 1 } },
};

function clients(extra: Record<string, unknown> = {}) {
  return createFakeClients({
    listResourceTypes: vi.fn(async () => resourceTypes),
    listResources: vi.fn(async () => summaries),
    getResource: vi.fn(async (id: string) => ({ value: docs[id], version_hash: "rv1" })),
    getResourceContent: vi.fn(async () => ({ value: "# 제목\n본문", version_hash: "rv1" })),
    updateResource: vi.fn(async (_id: string, r: unknown) => ({ value: r, version_hash: "rv2" })),
    putResourceContent: vi.fn(async () => ({ version_hash: "rv3" })),
    listResourceUsages: vi.fn(async (id: string) => (id === "d1" ? [{ kind: "graph", id: "tm1", name: "임의 팀", node_ids: ["n1"], layer: "team" }] : [])),
    listAgents: vi.fn(async () => []),
    ...extra,
  });
}

configure({ asyncUtilTimeout: 10_000 });
vi.setConfig({ testTimeout: 30_000 });

describe("리소스 목록", () => {
  it("종류 칩은 디스크립터에서 만들고 개수를 보이며 필터가 동작한다(모르는 종류 id도 칩으로)", async () => {
    mountApp(clients().clients, "/resources");
    const group = await screen.findByRole("group", { name: "종류" });
    expect(await within(group).findByRole("button", { name: /문서종류 1/ })).toBeTruthy();
    expect(await within(group).findByRole("button", { name: /설정종류 1/ })).toBeTruthy();
    expect(await within(group).findByRole("button", { name: /rt-gone 1/ })).toBeTruthy();
    fireEvent.click(within(group).getByRole("button", { name: /설정종류/ }));
    const list = await screen.findByRole("listbox", { name: "리소스 목록" });
    await waitFor(() => expect(within(list).getAllByRole("option")).toHaveLength(1));
  });

  it("새 리소스는 종류 카드(디스크립터)를 고른 뒤 이름·id를 받는다", async () => {
    const createResource = vi.fn(async (r: unknown) => ({ value: r, version_hash: "n" }));
    mountApp(clients({ createResource }).clients, "/resources");
    fireEvent.click(await screen.findByRole("button", { name: /새 리소스/ }));
    fireEvent.click(await screen.findByRole("radio", { name: /설정종류/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(await within(dialog).findByLabelText("이름"), { target: { value: "New One" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "만들기" }));
    await waitFor(() => expect(createResource).toHaveBeenCalledWith({ id: "new-one", type: "rt-cfg", name: "New One" }));
  });

  it("본문을 가지는 종류는 디스크립터가 정한 본문 참조(file·media_type)를 함께 보낸다", async () => {
    const createResource = vi.fn(async (r: unknown) => ({ value: r, version_hash: "n" }));
    mountApp(clients({ createResource }).clients, "/resources");
    fireEvent.click(await screen.findByRole("button", { name: /새 리소스/ }));
    fireEvent.click(await screen.findByRole("radio", { name: /문서종류/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(await within(dialog).findByLabelText("이름"), { target: { value: "Ref Doc" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "만들기" }));
    await waitFor(() => expect(createResource).toHaveBeenCalledWith({ id: "ref-doc", type: "rt-doc", name: "Ref Doc", content: { file: "ref-doc.md", media_type: "text/markdown" } }));
  });
});

describe("리소스 상세: 종류(디스크립터)가 탭 구성을 정한다", () => {
  it("문서형은 내용 탭이 첫 탭이고 편집기·미리보기·미디어 타입 선택이 있다", async () => {
    mountApp(clients().clients, "/resources/d1");
    const tabs = await screen.findByRole("tablist", { name: "리소스 상세" });
    await waitFor(() => expect(within(tabs).getAllByRole("tab").map((t) => t.textContent)).toEqual(["내용", "설정", "사용처 1", "버전"]));
    expect(await screen.findByLabelText("본문 편집기")).toBeTruthy();
    expect(await screen.findByLabelText("미디어 타입")).toBeTruthy();
    expect(await screen.findByRole("checkbox", { name: "미리보기" })).toBeTruthy();
    expect(await screen.findByText(/원본: \/원본\/a\.md \(해시 abcdef12\)/)).toBeTruthy();
  });

  it("설정형은 설정 탭이 첫 탭이고 폼 값을 바꿔 저장하면 정의만 If-Match로 보낸다", async () => {
    const { clients: c, rest } = clients();
    mountApp(c, "/resources/c1");
    const cmd = await screen.findByLabelText("명령");
    await waitFor(() => expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["설정", "사용처 0", "버전"]));
    fireEvent.change(cmd, { target: { value: "stop" } });
    fireEvent.click(await screen.findByRole("button", { name: "저장" }));
    await waitFor(() => expect(rest.updateResource).toHaveBeenCalledTimes(1));
    const [id, sent, hash] = rest.updateResource.mock.calls[0]!;
    expect(id).toBe("c1");
    expect(hash).toBe("rv1");
    expect(sent).toMatchObject({ config: { cmd: "stop" } });
    expect(rest.putResourceContent).not.toHaveBeenCalled();
    expect(rest.getResourceContent).not.toHaveBeenCalled();
  });

  it("미디어 타입을 바꾸면 정의가 바뀐 것으로 저장되고 충돌(412)은 배너로", async () => {
    const { clients: c, rest } = clients();
    mountApp(c, "/resources/d1");
    fireEvent.change(await screen.findByLabelText("미디어 타입"), { target: { value: "text/plain" } });
    fireEvent.click(await screen.findByRole("button", { name: "저장" }));
    await waitFor(() => expect(rest.updateResource).toHaveBeenCalled());
    expect(rest.updateResource.mock.calls[0]![1]).toMatchObject({ content: { file: "d1.md", media_type: "text/plain" } });
    cleanup();
    const bad = clients({ updateResource: vi.fn(async () => { throw versionConflict(); }) });
    mountApp(bad.clients, "/resources/d1");
    fireEvent.change(await screen.findByLabelText("미디어 타입"), { target: { value: "text/plain" } });
    fireEvent.click(await screen.findByRole("button", { name: "저장" }));
    expect(await screen.findByText("다른 곳에서 먼저 수정되었습니다")).toBeTruthy();
  });

  it("종류를 모르면 경고 배너와 읽기 전용 JSON(사용처만 탭)", async () => {
    mountApp(clients().clients, "/resources/u1");
    expect(await screen.findByText(/이 리소스 종류\(rt-gone\)를 이 서버가 모릅니다/)).toBeTruthy();
    expect(await screen.findByText(/"a": 1/)).toBeTruthy();
  });

  it("사용처 탭은 붙은 층과 팀 구성 링크를 보인다", async () => {
    mountApp(clients().clients, "/resources/d1");
    fireEvent.click(await screen.findByRole("tab", { name: /사용처/ }));
    const link = await screen.findByRole("link", { name: "임의 팀" });
    expect(link.getAttribute("href")).toBe("/teams/tm1");
    expect(await screen.findByText("team")).toBeTruthy();
  });
});

describe(".claude 가져오기", () => {
  const sources = [
    { id: "src-a", title: "출처 에이", description: "읽기만 합니다", path: "/홈/.x", available: true },
    { id: "src-b", title: "출처 비", description: "", path: "/없음", available: false },
  ];
  const candidates = [
    { id: "c1", path: "a.md", kind: "resource", resource_type: "rt-doc", name: "지침 가", suggested_id: "a", size: 2048, conflict: true, warnings: [] },
    { id: "c2", path: "b.json", kind: "resource", resource_type: "rt-cfg", name: "설정 나", suggested_id: "b", size: 30, warnings: [{ code: "import.secret_suspected", message: "비밀로 보이는 값", keys: ["env.KEY"] }] },
    { id: "c3", path: "agents/x.md", kind: "agent", name: "에이전트 다", suggested_id: "x", size: 10, warnings: [] },
  ];

  it("서버가 준 출처로 시작해 항목을 고르고(충돌 처리·비밀 의심 표시) 결과를 보인다", async () => {
    const previewImport = vi.fn(async () => ({ source: "src-a", root: "/홈/.x", candidates }));
    const importResources = vi.fn(async () => ({ source: "src-a", items: [{ source: "src-a", kind: "resource", id: "c1", target_id: "a-2", action: "renamed" }, { source: "src-a", kind: "resource", id: "c2", target_id: "b", action: "created" }, { source: "src-a", kind: "agent", id: "c3", target_id: "x", action: "failed", error: "쓰기 실패" }] }));
    const { clients: c } = clients({ listImportSources: vi.fn(async () => sources), previewImport, importResources });
    mountApp(c, "/resources");
    fireEvent.click(await screen.findByRole("button", { name: "가져오기…" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/원본 파일은 읽기만 하고 수정하지 않습니다/)).toBeTruthy();
    expect(((await within(dialog).findByRole("radio", { name: /출처 비/ })) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(await within(dialog).findByRole("radio", { name: /출처 에이/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "다음" }));
    await waitFor(() => expect(previewImport).toHaveBeenCalledWith({ source: "src-a" }));
    expect(await within(dialog).findByText("이름 충돌")).toBeTruthy();
    expect(await within(dialog).findByText(/비밀 의심/)).toBeTruthy();
    expect(await within(dialog).findByText("에이전트로 가져옴")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "전체 선택" }));
    fireEvent.change(within(dialog).getByLabelText("지침 가 충돌 처리"), { target: { value: "skip" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /^가져오기/ }));
    await waitFor(() => expect(importResources).toHaveBeenCalledTimes(1));
    expect(importResources).toHaveBeenCalledWith({ source: "src-a", items: [{ candidate_id: "c1", on_conflict: "skip" }, { candidate_id: "c2", on_conflict: "rename" }, { candidate_id: "c3", on_conflict: "rename" }] });
    expect(await within(dialog).findByText("리소스 2개, 에이전트 0개를 가져왔습니다")).toBeTruthy();
    expect(await within(dialog).findByText(/쓰기 실패/)).toBeTruthy();
  });

  it("후보가 없으면 경로와 함께 안내하고 출처를 다시 고르게 한다", async () => {
    const { clients: c } = clients({ listImportSources: vi.fn(async () => sources), previewImport: vi.fn(async () => ({ source: "src-a", root: "/홈/.x", candidates: [] })) });
    mountApp(c, "/resources");
    fireEvent.click(await screen.findByRole("button", { name: "가져오기…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("radio", { name: /출처 에이/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "다음" }));
    expect(await within(dialog).findByText(/가져올 수 있는 항목이 없습니다\. 경로: \/홈\/\.x/)).toBeTruthy();
    expect(await within(dialog).findByRole("button", { name: "다른 출처 고르기" })).toBeTruthy();
  });
});

describe("평문 비밀 경고", () => {
  it("비밀을 받는 설정 필드에 secret://가 아닌 값이 있으면 경고하고 값은 보이지 않는 위치만 알린다", async () => {
    const secretType = { id: "rt-sec", title: "비밀종류", config_schema: { type: "object", properties: { vars: { type: "object", description: "값은 secret://이름 참조만.", additionalProperties: { type: "string" } } } } };
    const { clients: c } = clients({
      listResourceTypes: vi.fn(async () => [secretType]),
      listResources: vi.fn(async () => [{ id: "s1", type: "rt-sec", name: "비밀", version_hash: "v", usage_count: 0 }]),
      getResource: vi.fn(async () => ({ value: { kind: "resource", id: "s1", type: "rt-sec", name: "비밀", config: { vars: { API: "sk-live-123456" } } }, version_hash: "rv1" })),
    });
    mountApp(c, "/resources/s1");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("secret://");
    expect(alert.textContent).toContain("/vars/API");
    expect(alert.textContent).not.toContain("sk-live-123456");
  });
});
