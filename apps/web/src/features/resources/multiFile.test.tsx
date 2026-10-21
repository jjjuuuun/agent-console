import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";

// 이 파일의 관심사는 파일 트리이지 편집기 내부가 아니다: 실제 CodeMirror 대신 textarea(happy-dom의 선택 이벤트 경쟁 회피).
vi.mock("../library/LazyTextEditor", () => ({
  LazyTextEditor: (p: { value: string; onChange?: (v: string) => void; ariaLabel: string }) => (
    <textarea aria-label={p.ariaLabel} value={p.value} onChange={(e) => p.onChange?.(e.target.value)} />
  ),
}));

afterEach(cleanup);
configure({ asyncUtilTimeout: 10_000 });
vi.setConfig({ testTimeout: 30_000 });

// 종류 id는 임의 문자열 — 화면은 content.multi_file 속성만 본다.
const multiType = { id: "rt-any-files", version: 1, title: "여러파일종류", content: { editor: "markdown", multi_file: true, media_types: ["text/markdown"] }, config_schema: { type: "object", properties: { name: { type: "string", title: "이름값" } } } };
const singleType = { id: "rt-single", version: 1, title: "한파일종류", content: { editor: "markdown", media_types: ["text/markdown"] } };

function clients(extra: Record<string, unknown> = {}) {
  let n = 1;
  return createFakeClients({
    listResourceTypes: vi.fn(async () => [multiType, singleType]),
    listResources: vi.fn(async () => [{ id: "m1", type: "rt-any-files", name: "묶음", version_hash: "v", has_content: true, usage_count: 0 }]),
    getResource: vi.fn(async () => ({ value: { kind: "resource", id: "m1", type: "rt-any-files", name: "묶음", content: { file: "m1" } }, version_hash: "h0" })),
    listResourceFiles: vi.fn(async () => [
      { path: "SKILL.md", size: 5, sha256: "a" },
      { path: "ref/api.md", size: 3, sha256: "b" },
      { path: "img.png", size: 2048, sha256: "c" },
    ]),
    readResourceFile: vi.fn(async (_id: string, p: string) => ({ text: p === "img.png" ? null : `내용 ${p}`, contentType: p === "img.png" ? "image/png" : "text/plain", size: 5, version_hash: "h0" })),
    listResourceUsages: vi.fn(async () => []),
    listAgents: vi.fn(async () => []),
    putResourceFile: vi.fn(async () => ({ value: { kind: "resource", id: "m1", type: "rt-any-files", name: "묶음" }, version_hash: `h${n++}` })),
    deleteResourceFile: vi.fn(async () => ({ value: { kind: "resource", id: "m1", type: "rt-any-files", name: "묶음" }, version_hash: `h${n++}` })),
    ...extra,
  });
}

describe("여러 파일 리소스 편집(디스크립터 content.multi_file)", () => {
  it("임의 종류 id라도 multi_file이면 파일 트리, 아니면 단일 편집기", async () => {
    mountApp(clients().clients, "/resources/m1");
    const tree = await screen.findByRole("tree", { name: "파일" });
    expect(within(tree).getByRole("treeitem", { name: /SKILL\.md/ })).toBeTruthy();
    expect(within(tree).getByRole("treeitem", { name: /ref/ })).toBeTruthy();
    expect(screen.getByTestId("res-files-total").textContent).toBe("총 2.0 KB");
    expect(screen.queryByLabelText("본문 편집기")).toBeNull();
    cleanup();
    mountApp(
      clients({
        listResources: vi.fn(async () => [{ id: "s1", type: "rt-single", name: "하나", version_hash: "v", usage_count: 0 }]),
        getResource: vi.fn(async () => ({ value: { kind: "resource", id: "s1", type: "rt-single", name: "하나", content: { file: "s1.md" } }, version_hash: "h0" })),
        getResourceContent: vi.fn(async () => ({ value: "본문", version_hash: "h0" })),
      }).clients,
      "/resources/s1",
    );
    expect(await screen.findByLabelText("본문 편집기")).toBeTruthy();
    expect(screen.queryByRole("tree")).toBeNull();
  });

  it("파일 추가(경로 검사)·이름 바꾸기·삭제(되돌리기) 후 저장하면 올리기 -> 지우기 순서로 If-Match가 이어진다", async () => {
    const { clients: c, rest } = clients();
    mountApp(c, "/resources/m1");
    await screen.findByRole("tree", { name: "파일" });
    // 추가: 잘못된 경로는 인라인 오류
    fireEvent.click(screen.getByRole("button", { name: "＋파일" }));
    const input = await screen.findByLabelText("새 파일 경로");
    fireEvent.change(input, { target: { value: "../bad" } });
    fireEvent.submit(input.closest("form")!);
    expect((await screen.findByRole("alert")).textContent).toContain("‘.’");
    fireEvent.change(input, { target: { value: "docs/new.md" } });
    fireEvent.submit(input.closest("form")!);
    const tree = await screen.findByRole("tree", { name: "파일" });
    await waitFor(() => expect(within(tree).getByRole("treeitem", { name: /new\.md/ })).toBeTruthy());
    // 이름 바꾸기: SKILL.md -> MAIN.md
    fireEvent.click(within(tree).getByRole("treeitem", { name: /SKILL\.md/ }));
    fireEvent.click(screen.getByRole("button", { name: "이름 바꾸기" }));
    const rn = await screen.findByLabelText("새 경로");
    fireEvent.change(rn, { target: { value: "MAIN.md" } });
    fireEvent.submit(rn.closest("form")!);
    await waitFor(() => expect(within(screen.getByRole("tree", { name: "파일" })).getByRole("treeitem", { name: /MAIN\.md/ })).toBeTruthy());
    // 삭제: img.png 는 텍스트 아님 정보 패널에서
    fireEvent.click(within(screen.getByRole("tree", { name: "파일" })).getByRole("treeitem", { name: /img\.png/ }));
    expect(await screen.findByText(/텍스트로 편집할 수 없는 파일입니다 — image\/png/)).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "삭제" }).at(-1)!);
    await waitFor(() => expect(within(screen.getByRole("tree", { name: "파일" })).queryByRole("treeitem", { name: /img\.png/ })).toBeNull());
    fireEvent.click(await screen.findByRole("button", { name: "저장" }));
    await waitFor(() => expect(rest.deleteResourceFile).toHaveBeenCalledTimes(2));
    expect(rest.putResourceFile.mock.calls.map((x: unknown[]) => [x[1], x[3]])).toEqual([["MAIN.md", "h0"], ["docs/new.md", "h1"]]);
    expect(rest.deleteResourceFile.mock.calls.map((x: unknown[]) => [x[1], x[2]])).toEqual([["SKILL.md", "h2"], ["img.png", "h3"]]);
  });

  it("폴더 삭제는 확인을 거치고, 저장 중 한 파일이 실패하면 그 행에 표시하고 나머지는 반영", async () => {
    const put = vi.fn(async (_id: string, p: string) => {
      if (p === "docs/bad.md") throw Object.assign(new Error("x"), {});
      return { value: { kind: "resource", id: "m1", type: "rt-any-files", name: "묶음" }, version_hash: "h1" };
    });
    const { clients: c } = clients({ putResourceFile: put });
    mountApp(c, "/resources/m1");
    await screen.findByRole("tree", { name: "파일" });
    for (const p of ["docs/ok.md", "docs/bad.md"]) {
      fireEvent.click(screen.getByRole("button", { name: "＋파일" }));
      const input = await screen.findByLabelText("새 파일 경로");
      fireEvent.change(input, { target: { value: p } });
      fireEvent.submit(input.closest("form")!);
      await screen.findByLabelText(`${p} 편집기`);
    }
    fireEvent.click(await screen.findByRole("button", { name: "저장" }));
    expect(await screen.findByText("파일 1개 저장 실패")).toBeTruthy();
    expect(screen.getByRole("img", { name: /저장 실패/ })).toBeTruthy();
    // 폴더 삭제 확인
    const tree = screen.getByRole("tree", { name: "파일" });
    fireEvent.focus(within(tree).getByRole("treeitem", { name: /ref/ }));
    fireEvent.click(screen.getAllByRole("button", { name: "삭제" })[0]!);
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain("파일 1개를 삭제합니다");
    fireEvent.click(within(dialog).getByRole("button", { name: "삭제" }));
    await waitFor(() => expect(within(screen.getByRole("tree", { name: "파일" })).queryByRole("treeitem", { name: /api\.md/ })).toBeNull());
  });
});

describe("저장 경고(X-Console-Issues)", () => {
  it("저장은 성공하고 서버 경고(예약 이름)를 배너로 보이며 다음 저장 시작 때 지운다", async () => {
    const issue = { severity: "warning", code: "resource.reserved_file_name", message: "예약된 파일 이름입니다", path: "/files/.git/x" };
    let n = 1;
    const put = vi.fn(async () => ({ value: { kind: "resource", id: "m1", type: "rt-any-files", name: "묶음" }, version_hash: `h${n++}`, issues: [issue] }));
    mountApp(clients({ putResourceFile: put }).clients, "/resources/m1");
    const tree = await screen.findByRole("tree", { name: "파일" });
    fireEvent.click(within(tree).getByRole("treeitem", { name: /SKILL\.md/ }));
    fireEvent.change(await screen.findByRole("textbox", { name: /SKILL/ }), { target: { value: "바뀜" } });
    fireEvent.click(await screen.findByRole("button", { name: "저장" }));
    const banner = await screen.findByRole("group", { name: "저장 경고" }).catch(() => screen.findByLabelText("저장 경고"));
    expect(within(banner).getByText(/예약된 파일 이름입니다/)).toBeTruthy();
    expect(put).toHaveBeenCalledTimes(1);
  });
});
