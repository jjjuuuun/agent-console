import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { useImperativeHandle } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { createSafeStorage } from "../../app/storage";
import { LONG, setup } from "./sddTestSetup";

const goToLine = vi.hoisted(() => vi.fn(() => true));

// CodeMirror는 DOM 입력을 흉내 내기 어려워 글상자로 바꾼다(편집기 자체는 text-editor 패키지 시험이 확인).
vi.mock("@agent-console/text-editor", async (orig) => {
  const actual = await orig<typeof import("@agent-console/text-editor")>();
  return {
    ...actual,
    TextEditor: (p: { value: string; onChange?: (v: string) => void; ariaLabel: string; handleRef?: React.Ref<{ isComposing(): boolean; goToLine(n: number): boolean }> }) => {
      useImperativeHandle(p.handleRef, () => ({ isComposing: () => false, goToLine }), []);
      return <textarea aria-label={p.ariaLabel} value={p.value} onChange={(e) => p.onChange?.(e.target.value)} />;
    },
    TextDiff: (p: { before: string; after: string; ariaLabel: string }) => <div role="group" aria-label={p.ariaLabel} data-testid="diff">{`${p.before}=>${p.after}`}</div>,
  };
});

beforeEach(() => {
  goToLine.mockClear();
});
afterEach(cleanup);

const DOCS = "/specs/sp1?prj=p1&tab=documents";
const editor = async () => screen.findByRole("textbox", { name: /문서 본문 편집기: 요구/ }, LONG);
const conflictError = () => new ApiError(412, { code: "version_conflict", message: "충돌", details: {} });

describe("문서 탭: 변경 비교·충돌", () => {
  it("저장 안 된 편집이 있으면 [변경 비교]로 저장된 내용 ↔ 편집본을 본다", async () => {
    setup(DOCS);
    const box = await editor();
    expect(screen.queryByRole("button", { name: "변경 비교" })).toBeNull();
    fireEvent.change(box, { target: { value: "# d-req 고침" } });
    fireEvent.click(await screen.findByRole("button", { name: "변경 비교" }));
    expect((await screen.findByTestId("diff")).textContent).toBe("# d-req=># d-req 고침");
    expect(screen.getByRole("region", { name: "변경 비교" }).textContent).toContain("저장된 내용");
  });

  it("저장이 충돌(412)이면 서버 본문 ↔ 내 편집본을 비교하고 [내 변경 복사]는 클립보드에 내 본문을 넣는다", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    let served = "# d-req";
    const { sdd } = setup(DOCS, {
      sdd: {
        getSpecDocument: vi.fn(async (_i: string, doc: string) => ({ value: { document_id: doc, file: "x.md", content: served, content_hash: served, issues: [] }, version_hash: served })),
        putSpecDocument: vi.fn(async () => { throw conflictError(); }),
      },
    });
    const box = await editor();
    fireEvent.change(box, { target: { value: "내 본문" } });
    served = "서버 본문";
    fireEvent.click(await screen.findByRole("button", { name: "저장" }));
    const banner = await screen.findByRole("alert", {}, LONG);
    expect(within(banner).getByRole("button", { name: "서버 버전 불러오기" })).toBeTruthy();
    fireEvent.click(within(banner).getByRole("button", { name: "변경 비교" }));
    await waitFor(() => expect(screen.getByTestId("diff").textContent).toBe("서버 본문=>내 본문"), LONG);
    expect(screen.getByRole("region", { name: "변경 비교" }).textContent).toContain("서버 버전");
    fireEvent.click(within(banner).getByRole("button", { name: "내 변경 복사" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("내 본문"), LONG);
    expect(sdd.putSpecDocument).toHaveBeenCalledTimes(1);
  });

  it("[서버 버전 불러오기]·[내 변경으로 덮어쓰기]는 확인을 거치고, 취소하면 아무것도 바뀌지 않는다", async () => {
    const put = vi.fn(async () => { throw conflictError(); });
    const { sdd } = setup(DOCS, { sdd: { putSpecDocument: put } });
    fireEvent.change(await editor(), { target: { value: "내 본문" } });
    fireEvent.click(await screen.findByRole("button", { name: "저장" }));
    const banner = await screen.findByRole("alert", {}, LONG);
    fireEvent.click(within(banner).getByRole("button", { name: "내 변경으로 덮어쓰기" }));
    const dialog = await screen.findByRole("dialog", {}, LONG);
    expect(within(dialog).getByText("서버 버전을 덮어씁니다")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "취소" }));
    expect(put).toHaveBeenCalledTimes(1);
    fireEvent.click(within(banner).getByRole("button", { name: "서버 버전 불러오기" }));
    const dialog2 = await screen.findByRole("dialog", {}, LONG);
    const reads = sdd.getSpecDocument.mock.calls.length;
    fireEvent.click(within(dialog2).getByRole("button", { name: "서버 버전 불러오기" }));
    await waitFor(() => expect(sdd.getSpecDocument.mock.calls.length).toBeGreaterThan(reads), LONG);
    await waitFor(() => expect((screen.getByRole("textbox", { name: /문서 본문 편집기: 요구/ }) as HTMLTextAreaElement).value).toBe("# d-req"), LONG);
  });
});

describe("문서 탭: 단축키·줄 이동", () => {
  it("Alt+P/Alt+E는 보기 방식을 바꾸고 선택을 저장한다", async () => {
    const backing = new Map<string, string>();
    const storage = createSafeStorage({ getItem: (k) => backing.get(k) ?? null, setItem: (k, v) => void backing.set(k, v), removeItem: (k) => void backing.delete(k), key: () => null, length: 0, clear: () => backing.clear() });
    setup(DOCS, { storage });
    await editor();
    fireEvent.keyDown(window, { key: "p", altKey: true });
    await waitFor(() => expect(screen.getByRole("button", { name: "미리보기" }).getAttribute("aria-pressed")).toBe("true"), LONG);
    expect(backing.get("ac.sdd.docview")).toBe("preview");
    fireEvent.keyDown(window, { key: "e", altKey: true });
    await waitFor(() => expect(screen.getByRole("button", { name: "편집" }).getAttribute("aria-pressed")).toBe("true"), LONG);
    expect(backing.get("ac.sdd.docview")).toBe("edit");
  });

  it("Ctrl+Alt+↓/↑는 다음·이전 문서로 옮기고 주소 ?doc가 따라간다", async () => {
    const { router } = setup(DOCS);
    await editor();
    fireEvent.keyDown(window, { key: "ArrowDown", ctrlKey: true, altKey: true });
    await waitFor(() => expect(router.state.location.search).toContain("doc=d-tasks"), LONG);
    fireEvent.keyDown(window, { key: "ArrowUp", ctrlKey: true, altKey: true });
    await waitFor(() => expect(router.state.location.search).toContain("doc=d-req"), LONG);
  });

  it("IME 조합 중 키는 무시한다", async () => {
    setup(DOCS);
    await editor();
    fireEvent.keyDown(window, { key: "p", altKey: true, isComposing: true });
    expect(screen.getByRole("button", { name: "미리보기" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("Ctrl+G는 줄 이동 입력칸을 열고 이동하면 편집기 핸들로 그 줄을 요청한다", async () => {
    const content = Array.from({ length: 12 }, (_, i) => `줄 ${i + 1}`).join("\n");
    setup(DOCS, { sdd: { getSpecDocument: vi.fn(async (_i: string, doc: string) => ({ value: { document_id: doc, file: "x.md", content, content_hash: "c", issues: [] }, version_hash: "c" })) } });
    await editor();
    fireEvent.keyDown(window, { key: "g", ctrlKey: true });
    const input = await screen.findByLabelText("줄 번호", {}, LONG);
    fireEvent.change(input, { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "이동" }));
    expect(goToLine).toHaveBeenCalledWith(7);
  });

  it("주소의 ?line=은 열 때 그 줄로 이동한다", async () => {
    setup(`${DOCS}&line=4`);
    await editor();
    await waitFor(() => expect(goToLine).toHaveBeenCalledWith(4), LONG);
  });
});
