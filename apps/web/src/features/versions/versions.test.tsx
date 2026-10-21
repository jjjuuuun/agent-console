import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { agents, resourceTypes } from "../../testing/teamFixtures";

afterEach(cleanup);
configure({ asyncUtilTimeout: 10_000 });
vi.setConfig({ testTimeout: 40_000 });

const NOW = Math.floor(Date.now() / 1000);
const versions = [
  { kind: "k", id: "ag1", version_hash: "cur00000aaaa", saved_at: NOW - 60, message: "방금 저장" },
  { kind: "k", id: "ag1", version_hash: "prev1111bbbb", saved_at: NOW - 7200, message: "restored from 0123" },
  { kind: "k", id: "ag1", version_hash: "old22222cccc", saved_at: NOW - 86400 * 3 },
];
const diff = {
  kind: "k",
  id: "ag1",
  from_hash: "prev1111bbbb",
  to_hash: "cur00000aaaa",
  changes: [
    { op: "replace", path: "/items/0/label", before: "옛 이름", after: "새 이름" },
    { op: "add", path: "/items/1", after: { label: "추가된 것", n: 1 } },
    { op: "replace", path: "/env/TOKEN", before: "***", after: "***", secret: true },
    { op: "remove", path: "/gone", before: "지워짐" },
  ],
  content_changes: [],
};
const docs: Record<string, unknown> = {
  prev1111bbbb: { kind: "k", id: "ag1", items: [{ label: "옛 이름" }], gone: "지워짐" },
  cur00000aaaa: { kind: "k", id: "ag1", items: [{ label: "새 이름" }, { label: "추가된 것", n: 1 }] },
};

function clients(extra: Record<string, unknown> = {}) {
  return createFakeClients({
    listAgents: vi.fn(async () => agents),
    listAgentUsages: vi.fn(async () => []),
    getAgentVersioned: vi.fn(async () => ({ value: agents[0], version_hash: "cur00000aaaa" })),
    getAgentEffectiveSettings: vi.fn(async () => ({ value: {}, provenance: {}, layers: [] })),
    listBackends: vi.fn(async () => []),
    listResourceTypes: vi.fn(async () => resourceTypes),
    listResources: vi.fn(async () => []),
    listDefinitionVersions: vi.fn(async () => versions),
    getDefinitionVersion: vi.fn(async (_b: string, hash: string) => ({ ...versions.find((v) => v.version_hash === hash), content: docs[hash] })),
    diffDefinitionVersions: vi.fn(async () => diff),
    restoreDefinitionVersion: vi.fn(async () => ({ value: { kind: "k", id: "ag1", version_hash: "new99999dddd", saved_at: NOW }, version_hash: "new99999dddd" })),
    ...extra,
  });
}

async function openTab(extra: Record<string, unknown> = {}) {
  const c = clients(extra);
  mountApp(c.clients, "/agents/ag1?tab=versions");
  await screen.findByRole("listbox", { name: "버전 목록" });
  return c;
}

describe("버전 탭: 목록과 비교", () => {
  it("?tab=versions로 열면 버전 탭이 선택되고 목록에 해시 앞 8자·현재 칩·메시지가 보인다", async () => {
    const { rest } = await openTab();
    const options = within(screen.getByRole("listbox", { name: "버전 목록" })).getAllByRole("option");
    expect(options).toHaveLength(3);
    expect(options[0]!.textContent).toContain("cur00000");
    expect(options[0]!.textContent).toContain("현재");
    expect(options[1]!.textContent).toContain("restored from 0123");
    expect(screen.getByRole("tab", { name: "버전" }).getAttribute("aria-selected")).toBe("true");
    expect(rest.listDefinitionVersions).toHaveBeenCalledWith("/agents/ag1");
  });

  it("기본은 직전 버전과 현재를 비교하고(대상 생략), 방향을 헤더에 텍스트로 보인다", async () => {
    const { rest } = await openTab();
    await screen.findByRole("table", { name: "필드 변경 표" });
    expect(rest.diffDefinitionVersions).toHaveBeenCalledWith("/agents/ag1", "prev1111bbbb", undefined);
    expect(screen.getByText("prev1111 → 현재(cur00000)")).toBeTruthy();
    expect(screen.getByText("변경 4 · 본문 0")).toBeTruthy();
  });

  it("경로를 원문 포인터와 함께 읽는 경로(배열 원소 이름)로 보이고, 값 펼치기가 객체 JSON을 보인다", async () => {
    await openTab();
    const table = await screen.findByRole("table", { name: "필드 변경 표" });
    // replace는 이전(from) 문서 기준, add는 이후(to) 문서 기준 포인터라 각 문서로 읽는다
    expect(await within(table).findByText("items “옛 이름” › label")).toBeTruthy();
    expect(within(table).getByText("/items/0/label")).toBeTruthy();
    expect(within(table).getByText("items “추가된 것”")).toBeTruthy();
    fireEvent.click(within(table).getByRole("button", { name: "값 펼치기" }));
    expect(within(table).getByText(/"label": "추가된 것"/)).toBeTruthy();
  });

  it("비밀 행은 서버가 준 ***만 보이고 칩이 붙으며 값으로 검색되지 않는다", async () => {
    await openTab();
    const table = await screen.findByRole("table", { name: "필드 변경 표" });
    const row = within(table).getByRole("row", { name: /비밀 값은 표시하지 않음/ });
    expect(within(row).getAllByText("***").length).toBe(2);
    expect(within(row).getByText(/비밀 값은 표시하지 않음/)).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox", { name: "경로·값 검색" }), { target: { value: "***" } });
    expect(screen.getByText("조건에 맞는 변경이 없습니다")).toBeTruthy();
  });

  it("동작 필터와 검색이 서버 순서를 유지한 채 줄인다", async () => {
    await openTab();
    const table = await screen.findByRole("table", { name: "필드 변경 표" });
    fireEvent.click(screen.getByRole("button", { name: /삭제/, pressed: false }));
    await waitFor(() => expect(within(table).getAllByRole("row")).toHaveLength(2)); // 머리글 + 1
    expect(within(table).getByText("/gone")).toBeTruthy();
  });

  it("두 버전 모드는 체크 2개일 때 오래된 것을 앞에 두고 비교한다", async () => {
    const { rest } = await openTab();
    fireEvent.click(screen.getByRole("radio", { name: "두 버전" }));
    expect(screen.getByText("버전을 2개 고르세요")).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: /prev1111 비교 대상/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /old22222 비교 대상/ }));
    await waitFor(() => expect(rest.diffDefinitionVersions).toHaveBeenCalledWith("/agents/ag1", "old22222cccc", "prev1111bbbb"));
  });

  it("버전이 현재 하나뿐이면 안내만 보인다", async () => {
    const c = clients({ listDefinitionVersions: vi.fn(async () => [versions[0]]) });
    mountApp(c.clients, "/agents/ag1?tab=versions");
    expect(await screen.findByText("이전 버전이 없습니다. 저장할 때마다 버전이 쌓입니다.")).toBeTruthy();
    expect(screen.queryByRole("listbox", { name: "버전 목록" })).toBeNull();
  });

  it("두 버전이 같으면 안내, 비교 실패면 오류 블록과 [다시 시도](목록은 유지)", async () => {
    const same = vi.fn(async () => ({ ...diff, changes: [], content_changes: [] }));
    const { clients: a } = clients({ diffDefinitionVersions: same });
    mountApp(a, "/agents/ag1?tab=versions");
    expect(await screen.findByText("두 버전은 같습니다")).toBeTruthy();
    cleanup();
    const failing = vi.fn(async () => {
      throw new ApiError(404, { code: "not_found", message: "정의가 지워졌습니다" });
    });
    const { clients: b } = clients({ diffDefinitionVersions: failing });
    mountApp(b, "/agents/ag1?tab=versions");
    expect(await screen.findByText("비교하지 못했습니다")).toBeTruthy();
    expect(screen.getByText("정의가 지워졌습니다")).toBeTruthy();
    expect(screen.getByRole("listbox", { name: "버전 목록" })).toBeTruthy();
  });

  it("목록 키보드: ↑↓ 이동, Space 선택, R 되돌리기 열기", async () => {
    await openTab();
    const options = within(screen.getByRole("listbox", { name: "버전 목록" })).getAllByRole("option");
    options[0]!.focus();
    fireEvent.keyDown(options[0]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(options[1]);
    fireEvent.keyDown(options[1]!, { key: "r" });
    expect(await screen.findByRole("dialog", { name: "버전 prev1111로 되돌리기" })).toBeTruthy();
  });
});

describe("버전 탭: 본문 변경", () => {
  const contentDiff = { ...diff, changes: [], content_changes: [{ path: "skills/a/SKILL.md", before_hash: "aaaaaaaa11", after_hash: "bbbbbbbb22" }, { path: "big.md", before_hash: "c1", after_hash: "c2" }, { path: "new.md", after_hash: "d1" }] };
  const files = (hash: string) => [
    { path: "skills/a/SKILL.md", size: 10, sha256: "x", media_type: "text/markdown", hash },
    { path: "big.md", size: 600 * 1024, sha256: "y" },
    { path: "new.md", size: 3, sha256: "z" },
  ];

  it("행의 [텍스트 비교]가 두 쪽 파일을 읽어 TextDiff를 펼치고, 큰 파일은 해시만 비교한다", async () => {
    const readVersionFile = vi.fn(async (_b: string, hash: string) => ({ text: hash.startsWith("prev") ? "옛\n본문" : "새\n본문", contentType: "text/plain", size: 5 }));
    await openTab({
      diffDefinitionVersions: vi.fn(async () => contentDiff),
      listVersionFiles: vi.fn(async (_b: string, hash: string) => files(hash)),
      readVersionFile,
    });
    const section = await screen.findByRole("region", { name: "본문 변경 표" });
    expect(within(section).getByText("추가됨")).toBeTruthy();
    const buttons = within(section).getAllByRole("button", { name: /텍스트 비교/ });
    await waitFor(() => expect((buttons[1] as HTMLButtonElement).disabled).toBe(true));
    expect(within(section).getByText(/텍스트로 비교할 수 없습니다 — 크기 600 KB → 600 KB, 해시만 비교합니다/)).toBeTruthy();
    fireEvent.click(buttons[0]!);
    expect(await within(section).findByRole("group", { name: "비교 보기 방식" }, { timeout: 20_000 })).toBeTruthy();
    expect(readVersionFile).toHaveBeenCalledWith("/agents/ag1", "prev1111bbbb", "skills/a/SKILL.md");
    expect(readVersionFile).toHaveBeenCalledWith("/agents/ag1", "cur00000aaaa", "skills/a/SKILL.md");
  });

  it("텍스트가 아닌 파일은 행 안에 안내하고 읽기 실패는 [다시 시도]를 보인다", async () => {
    const readVersionFile = vi.fn().mockResolvedValueOnce({ text: null, contentType: "application/octet-stream", size: 3 }).mockResolvedValueOnce({ text: "", contentType: "text/plain", size: 0 });
    await openTab({
      diffDefinitionVersions: vi.fn(async () => ({ ...contentDiff, content_changes: [contentDiff.content_changes[0]] })),
      listVersionFiles: vi.fn(async (_b: string, hash: string) => files(hash)),
      readVersionFile,
    });
    const section = await screen.findByRole("region", { name: "본문 변경 표" });
    fireEvent.click(within(section).getByRole("button", { name: /텍스트 비교/ }));
    expect(await within(section).findByText(/텍스트 파일이 아닙니다/)).toBeTruthy();
  });
});

describe("되돌리기", () => {
  async function openRestore(extra: Record<string, unknown> = {}) {
    const c = await openTab(extra);
    fireEvent.click(await screen.findByRole("button", { name: "되돌리기…" }));
    return { ...c, dialog: await screen.findByRole("dialog", { name: "버전 prev1111로 되돌리기" }) };
  }

  it("확인 다이얼로그: 취소가 기본 포커스, 바뀌는 수와 범위 안내를 보인다", async () => {
    const { dialog } = await openRestore();
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "취소" }));
    expect(await within(dialog).findByText("필드 4개 · 본문 0개가 바뀝니다")).toBeTruthy();
    expect(within(dialog).getByText("이 정의만 되돌립니다. 이 정의가 참조하는 다른 정의는 바뀌지 않습니다.")).toBeTruthy();
    expect(within(dialog).getByPlaceholderText("restored from prev1111")).toBeTruthy();
  });

  it("확인하면 현재 해시를 If-Match로 복원 요청하고, 토스트의 [실행 취소]가 직전 해시로 같은 복원을 한다", async () => {
    const restore = vi
      .fn()
      .mockResolvedValueOnce({ value: { kind: "k", id: "ag1", version_hash: "new99999dddd", saved_at: NOW }, version_hash: "new99999dddd" })
      .mockResolvedValueOnce({ value: { kind: "k", id: "ag1", version_hash: "und88888eeee", saved_at: NOW }, version_hash: "und88888eeee" });
    const { dialog } = await openRestore({ restoreDefinitionVersion: restore });
    fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "내 메시지" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "되돌리기" }));
    await waitFor(() => expect(restore).toHaveBeenCalledWith("/agents/ag1", "prev1111bbbb", { message: "내 메시지" }, "cur00000aaaa"));
    expect(await screen.findByText("버전 prev1111로 되돌렸습니다 → 새 버전 new99999")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "실행 취소" }));
    await waitFor(() => expect(restore).toHaveBeenLastCalledWith("/agents/ag1", "cur00000aaaa", {}, "new99999dddd"));
  });

  it("422는 다이얼로그를 닫지 않고 서버 이슈 목록(메시지 그대로)과 안내를 보인다", async () => {
    const restore = vi.fn(async () => {
      throw new ApiError(422, { code: "validation_failed", message: "검증 실패", details: { issues: [{ path: "/env/TOKEN", message: "평문 비밀이 있습니다" }] } });
    });
    const { dialog } = await openRestore({ restoreDefinitionVersion: restore });
    fireEvent.click(within(dialog).getByRole("button", { name: "되돌리기" }));
    expect(await within(dialog).findByText("평문 비밀이 있습니다")).toBeTruthy();
    expect(within(dialog).getByText("/env/TOKEN")).toBeTruthy();
    expect(within(dialog).getByText(/secret:\/\/ 참조로 바꾼 뒤/)).toBeTruthy();
    expect(screen.getByRole("dialog", { name: "버전 prev1111로 되돌리기" })).toBeTruthy();
  });

  it("412는 다이얼로그를 닫고 충돌 배너를 보인다", async () => {
    const restore = vi.fn(async () => {
      throw new ApiError(412, { code: "version_conflict", message: "충돌", details: { current_version_hash: "zzz" } });
    });
    const { dialog } = await openRestore({ restoreDefinitionVersion: restore });
    fireEvent.click(within(dialog).getByRole("button", { name: "되돌리기" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /되돌리기/ })).toBeNull());
    expect(await screen.findByRole("alert", { name: "저장 충돌" })).toBeTruthy();
  });

  it("네트워크 오류는 다이얼로그에 문구를 보이고 입력을 유지한다", async () => {
    const restore = vi.fn(async () => {
      throw new ApiError(0, { code: "network_error", message: "연결 끊김" });
    });
    const { dialog } = await openRestore({ restoreDefinitionVersion: restore });
    fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "keep" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "되돌리기" }));
    expect(await within(dialog).findByText("연결 끊김")).toBeTruthy();
    expect((within(dialog).getByRole("textbox") as HTMLInputElement).value).toBe("keep");
  });
});
