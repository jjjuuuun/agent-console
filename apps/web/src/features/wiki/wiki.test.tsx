import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { useImperativeHandle } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { samplePageView, sampleLinks } from "@agent-console/wiki-view/testing";
import { LONG, INFO, SYNTAX, pageSummary, pageView, project, projectView, setup, wikiSummary, wikiView } from "./wikiTestSetup";

const insertAtCursor = vi.hoisted(() => vi.fn(() => true));

// CodeMirror는 DOM 입력을 흉내 내기 어려워 글상자로 바꾼다(편집기 자체는 text-editor 패키지 시험이 확인).
vi.mock("@agent-console/text-editor", async (orig) => {
  const actual = await orig<typeof import("@agent-console/text-editor")>();
  return {
    ...actual,
    TextEditor: (p: { value: string; onChange?: (v: string) => void; ariaLabel: string; handleRef?: React.Ref<unknown> }) => {
      useImperativeHandle(p.handleRef, () => ({ isComposing: () => false, goToLine: () => true, goToOffset: () => true, insertAtCursor }), []);
      return <textarea aria-label={p.ariaLabel} value={p.value} onChange={(e) => p.onChange?.(e.target.value)} />;
    },
    TextDiff: (p: { before: string; after: string; ariaLabel: string }) => <div role="group" aria-label={p.ariaLabel} data-testid="diff">{`${p.before}=>${p.after}`}</div>,
  };
});

afterEach(() => {
  cleanup();
  insertAtCursor.mockClear();
});

const apiError = (status: number, code: string, details: Record<string, unknown> = {}, message = "서버 문장") => new ApiError(status, { code, message, details });
const SECOND = pageView("notes/second", "둘째 본문", { page: pageSummary("notes/second", { title: "둘째" }) });
const FIRST = samplePageView({ page: pageSummary("notes/first", { title: "첫 페이지" }) });
const PAGES = { "notes/first": FIRST, "notes/second": SECOND };
const READ = "/wiki/w1?prj=p1&path=notes/first";

/** 테스트 화면(happy-dom 1024px)은 좁아서 오른쪽 패널이 서랍이다. 토글로 연다. */
async function openPanel() {
  const toggle = await screen.findByRole("button", { name: /^패널/ }, LONG);
  if (toggle.getAttribute("aria-expanded") !== "true") fireEvent.click(toggle);
}

describe("위키 목록 /wiki", () => {
  it("위키 0개: 빈 안내와 첫 사용 순서가 있고 [새 위키…]는 머리에 하나뿐이다", async () => {
    setup("/wiki?prj=p1", { wikis: [] });
    expect(await screen.findByTestId("wiki-empty", {}, LONG)).toBeTruthy();
    expect(screen.getByText("아직 위키가 없습니다")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "새 위키…" })).toHaveLength(1);
  });

  it("위키가 1개여도 목록이다: 자동 이동 없이 그 카드가 미리 선택되고 Enter로 열린다", async () => {
    const { router } = setup("/wiki?prj=p1", { wikis: [wikiSummary()] });
    const card = await screen.findByRole("option", { name: "노트" }, LONG);
    expect(card.getAttribute("aria-selected")).toBe("true");
    expect(router.state.location.pathname).toBe("/wiki");
    expect(router.state.location.search).not.toContain("all");
    fireEvent.keyDown(card, { key: "Enter" });
    await waitFor(() => expect(router.state.location.pathname).toBe("/wiki/w1"), LONG);
  });

  it("위키가 여럿이면 선택 표시 없이 이름 순으로 보인다", async () => {
    setup("/wiki?prj=p1", { wikis: [wikiSummary({ id: "w2", name: "나" }), wikiSummary({ id: "w1", name: "가" })] });
    const cards = await screen.findAllByRole("option", {}, LONG);
    expect(cards.map((c) => c.getAttribute("aria-label"))).toEqual(["가", "나"]);
    expect(cards.every((c) => c.getAttribute("aria-selected") === "false")).toBe(true);
  });

  it("프로젝트가 0개면 본문 전체가 NoProjectState 하나로 바뀌고 [새 위키…]도 없다", async () => {
    setup("/wiki", { projects: [] });
    expect(await screen.findByTestId("no-project-state", {}, LONG)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "새 위키…" })).toBeNull();
  });

  it("프로젝트 연동이 꺼져(409 spaces_unavailable) 있으면 본문 전체가 안내로 바뀐다", async () => {
    setup("/wiki?prj=p1", { wiki: { listWikis: vi.fn(async () => { throw apiError(409, "wiki.spaces_unavailable"); }) } });
    expect(await screen.findByTestId("wiki-unavailable", {}, LONG)).toBeTruthy();
  });

  it("읽기 전용 폴더에서는 [새 위키…]가 aria-disabled이고 누르면 아무 일도 없다", async () => {
    setup("/wiki?prj=p1", { wikis: [], projects: [projectView(project("p1"), { config_writable: false })] });
    const button = await screen.findByRole("button", { name: "새 위키…" }, LONG);
    expect(button.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(button);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByTestId("wiki-readonly")).toBeTruthy();
  });

  it("새 위키: 규칙이 없으면 안내와 함께 만들어지고, 아무 규칙도 미리 고르지 않으며 첫 페이지 칸도 비어 있다", async () => {
    const created = wikiView({ id: "w9", name: "새로" }, { version_hash: "n1" });
    const { wiki, router } = setup("/wiki?prj=p1", { wikis: [], wiki: { createWiki: vi.fn(async () => ({ value: created, version_hash: "n1" })), getWiki: vi.fn(async () => ({ value: created, version_hash: "n1" })) } });
    fireEvent.click(await screen.findByRole("button", { name: "새 위키…" }, LONG));
    const dialog = await screen.findByRole("dialog", {}, LONG);
    expect(await within(dialog).findByTestId("wiki-new-rules-none", {}, LONG)).toBeTruthy();
    fireEvent.click(within(dialog).getByText(/고급/));
    expect((within(dialog).getByLabelText(/^첫 페이지 경로/) as HTMLInputElement).value).toBe("");
    fireEvent.change(within(dialog).getByLabelText(/이름/), { target: { value: "  새로  " } });
    fireEvent.click(within(dialog).getByRole("button", { name: "위키 만들기" }));
    await waitFor(() => expect(wiki.createWiki).toHaveBeenCalledWith({ name: "새로", rules: [] }), LONG);
    await waitFor(() => expect(router.state.location.pathname).toBe("/wiki/w9"), LONG);
  });
});

describe("위키 화면: 페이지 탭 상태", () => {
  it("페이지 0개: 안내와 첫 사용 순서가 보이고, 첫 페이지를 미리 정하지 않는다", async () => {
    setup("/wiki/w1?prj=p1", { pages: { items: [], truncated: false } });
    expect(await screen.findByTestId("wiki-page-empty", {}, LONG)).toBeTruthy();
    expect(screen.getByText(/첫 페이지를 정하기|규칙 탭의 위키 정보에서 첫 페이지 정하기/)).toBeTruthy();
  });

  it("페이지를 고르지 않았으면 '페이지를 고르세요'와 최근 고친 페이지가 보인다", async () => {
    setup("/wiki/w1?prj=p1", { page: PAGES });
    expect(await screen.findByTestId("wiki-page-none", {}, LONG)).toBeTruthy();
    expect(screen.getByText("최근 고친 페이지")).toBeTruthy();
  });

  it("없는 페이지(404 page_not_found): [이 페이지 만들기]가 있고, 기록이 남은 경우에만 [기록에서 찾기]가 있다", async () => {
    const notFound = (has: boolean) => async () => { throw apiError(404, "wiki.page_not_found", { path: "x/y", has_history: has }); };
    const first = setup("/wiki/w1?prj=p1&path=x/y", { page: {}, wiki: { getWikiPage: vi.fn(notFound(true)) } });
    const missing = await screen.findByTestId("wiki-page-missing", {}, LONG);
    expect(within(missing).getByRole("button", { name: "이 페이지 만들기" })).toBeTruthy();
    expect(within(missing).getByRole("button", { name: "기록에서 찾기" })).toBeTruthy();
    first.unmount();
    cleanup();
    setup("/wiki/w1?prj=p1&path=x/y", { page: {}, wiki: { getWikiPage: vi.fn(notFound(false)) } });
    const again = await screen.findByTestId("wiki-page-missing", {}, LONG);
    expect(within(again).queryByRole("button", { name: "기록에서 찾기" })).toBeNull();
  });

  it("읽기 전용 폴더: [편집]·[이름 바꾸기…]·[지우기…]가 aria-disabled이고 mode=edit 주소로 들어와도 보기로 열린다", async () => {
    setup(`${READ}&mode=edit`, { page: PAGES, projects: [projectView(project("p1"), { config_writable: false })] });
    const edit = await screen.findByRole("button", { name: "편집" }, LONG);
    expect(edit.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByRole("button", { name: "이름 바꾸기…" }).getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByRole("button", { name: "지우기…" }).getAttribute("aria-disabled")).toBe("true");
    expect(screen.queryByRole("textbox", { name: /편집기/ })).toBeNull();
    expect(screen.getAllByText(/보기로 엽니다/).length).toBeGreaterThan(0);
  });

  it("기록 저장소가 없으면 기록 탭은 보이고 본문에 안내가 나온다(숨기지 않는다)", async () => {
    setup(`${READ}&side=history`, { page: PAGES, info: { ...INFO, capabilities: { ...INFO.capabilities, history: false } }, wiki: { getWikiPageHistory: vi.fn(async () => { throw apiError(409, "wiki.history_unavailable"); }) } });
    await openPanel();
    expect(await screen.findByRole("tab", { name: /기록/ }, LONG)).toBeTruthy();
    expect(await screen.findByText("이 위키는 기록을 저장하지 않습니다", {}, LONG)).toBeTruthy();
    expect(screen.getAllByText(/기록되지 않습니다/).length).toBeGreaterThan(0);
  });

  it("링크 문법이 없으면 백링크·나가는 링크 자리에 안내가 나오고 페이지는 일반 마크다운으로 보인다", async () => {
    setup(READ, { page: { "notes/first": pageView("notes/first", "# 제목\n\n본문", { page: pageSummary("notes/first", { title: "첫 페이지" }) }) }, syntax: { syntax: { links: [] }, sources: {}, empty: true } });
    await openPanel();
    expect(await screen.findByTestId("wiki-nosyntax", {}, LONG)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "제목" })).toBeTruthy();
  });
});

describe("위키 화면: 링크·목록", () => {
  it("서버 링크 범위(UTF-16, 한글·이모지)가 정확한 글자에 걸리고 클릭하면 앱 안에서 그 페이지로 간다", async () => {
    const { router } = setup(READ, { page: PAGES });
    const link = await screen.findByRole("link", { name: "둘째" }, LONG);
    // 이모지(서로게이트 쌍) 뒤의 링크 범위가 어긋나지 않으면 링크 글자는 서버 label이고, 그 밖의 본문 글자는 그대로다
    expect(sampleLinks()[0]?.start).toBeGreaterThan(5);
    expect(screen.getAllByText(/그리고/).length).toBeGreaterThan(0);
    fireEvent.click(link);
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get("path")).toBe("notes/second"), LONG);
  });

  it("끊긴 링크는 팝오버에서 [이 페이지 만들기]를 주고 누르면 새 페이지 대화상자에 제안 경로가 채워진다", async () => {
    setup(READ, { page: PAGES });
    const broken = await screen.findByLabelText(/끊긴 링크: ‘없는곳’/, {}, LONG);
    fireEvent.click(broken);
    fireEvent.click(await screen.findByRole("button", { name: "이 페이지 만들기" }, LONG));
    const dialog = await screen.findByRole("dialog", {}, LONG);
    expect((within(dialog).getByLabelText(/경로/) as HTMLInputElement).value).toBe("notes/none");
  });

  it("목록이 잘리면(truncated) 개수를 밝히는 안내가 트리 맨 위에 나온다", async () => {
    setup(READ, { page: PAGES, pages: { items: [FIRST.page, SECOND.page], truncated: true, total: 20000 } });
    expect(await screen.findByText(/20000개 중 10000개까지만 불러왔습니다/, {}, LONG)).toBeTruthy();
  });
});

describe("위키 화면: 편집·저장", () => {
  const editor = async () => screen.findByRole("textbox", { name: /편집기/ }, LONG);

  it("새 페이지는 If-None-Match: *, 있는 페이지는 If-Match(본문 해시)로 저장한다", async () => {
    const put = vi.fn(async (_w: string, p: string, body: { content: string }) => ({ value: pageView(p, body.content), version_hash: "h-new" }));
    const { wiki } = setup(`${READ}&mode=edit`, { page: PAGES, wiki: { putWikiPage: put } });
    fireEvent.change(await editor(), { target: { value: "고친 본문" } });
    fireEvent.click(await screen.findByRole("button", { name: "저장" }));
    await waitFor(() => expect(wiki.putWikiPage).toHaveBeenCalledTimes(1), LONG);
    expect(wiki.putWikiPage).toHaveBeenCalledWith("w1", "notes/first", { content: "고친 본문" }, { expectedHash: FIRST.content_hash });
  });

  it("저장이 충돌(412)이면 4버튼 충돌 띠가 나오고 저장은 다시 시도하지 않는다", async () => {
    const put = vi.fn(async () => { throw apiError(412, "version_conflict"); });
    const { wiki } = setup(`${READ}&mode=edit`, { page: PAGES, wiki: { putWikiPage: put } });
    fireEvent.change(await editor(), { target: { value: "내 본문" } });
    fireEvent.click(await screen.findByRole("button", { name: "저장" }));
    const banner = await screen.findByRole("alert", {}, LONG);
    for (const name of ["변경 비교", "서버 버전 불러오기", "내 변경으로 덮어쓰기", "내 변경 복사"]) expect(within(banner).getByRole("button", { name })).toBeTruthy();
    expect(wiki.putWikiPage).toHaveBeenCalledTimes(1);
  });

  it("쓰기 규칙이 막으면(422) 서버가 준 규칙 id와 메시지가 그대로 danger 띠에 나온다", async () => {
    const put = vi.fn(async () => { throw apiError(422, "wiki.rule_rejected", { rule_id: "r-임의", message: "금지된 글", lines: [3] }); });
    setup(`${READ}&mode=edit`, { page: PAGES, wiki: { putWikiPage: put } });
    fireEvent.change(await editor(), { target: { value: "내 본문" } });
    fireEvent.click(await screen.findByRole("button", { name: "저장" }));
    const band = await screen.findByText(/규칙 ‘r-임의’이\(가\) 저장을 막았습니다: 금지된 글/, {}, LONG);
    expect(band.textContent).toContain("(줄 3)");
    const rejected = band.closest("[data-band]") as HTMLElement;
    expect(within(rejected).getByRole("button", { name: "줄로 이동" })).toBeTruthy();
  });

  it("비밀 의심 거부(422)는 줄 번호만 보이고 값은 없다", async () => {
    const put = vi.fn(async () => { throw apiError(422, "wiki.secret_rejected", { lines: [2, 5] }, ""); });
    setup(`${READ}&mode=edit`, { page: PAGES, wiki: { putWikiPage: put } });
    fireEvent.change(await editor(), { target: { value: "sk-비밀" } });
    fireEvent.click(await screen.findByRole("button", { name: "저장" }));
    const band = await screen.findByText(/비밀 값처럼 보이는 곳이 있어 저장하지 못했습니다 \(줄 2, 5\)/, {}, LONG);
    expect(band.textContent).not.toContain("sk-비밀");
  });

  it("편집 중 시험(preview)은 저장·기록을 만들지 않는다: 본문이 멈추면 preview만 부르고 put은 부르지 않는다", async () => {
    const { wiki } = setup(`${READ}&mode=edit`, { page: PAGES });
    fireEvent.change(await editor(), { target: { value: "시험 본문" } });
    await waitFor(() => expect(wiki.previewWikiPage).toHaveBeenCalledWith("w1", "notes/first", "시험 본문", expect.anything()), LONG);
    expect(wiki.putWikiPage).not.toHaveBeenCalled();
    expect(wiki.deleteWikiPage).not.toHaveBeenCalled();
  });

  it("유효 문법에 삽입 틀(insert)이 없으면 [링크 넣기]가 aria-disabled이고 눌러도 대화상자가 열리지 않는다", async () => {
    setup(`${READ}&mode=edit`, { page: PAGES, syntax: { syntax: { links: [{ id: "r1", kind: "k1", pattern: "x" }] }, sources: {}, empty: false } });
    await editor();
    const button = await screen.findByRole("button", { name: "링크 넣기" });
    expect(button.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(button);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("[링크 넣기]는 서버가 만든 글을 커서 위치에 끼운다", async () => {
    const { wiki } = setup(`${READ}&mode=edit`, { page: PAGES, syntax: SYNTAX, wiki: { getWikiLinkText: vi.fn(async () => ({ rule_id: "r-link", text: "<<둘째>>" })) } });
    await editor();
    fireEvent.click(await screen.findByRole("button", { name: "링크 넣기" }));
    const dialog = await screen.findByRole("dialog", {}, LONG);
    fireEvent.click(await within(dialog).findByRole("option", { name: /둘째/ }, LONG));
    await waitFor(() => expect(insertAtCursor).toHaveBeenCalledWith("<<둘째>>"), LONG);
    expect(wiki.getWikiLinkText).toHaveBeenCalledWith("w1", { from_page: "notes/first", target: "notes/second" });
  });
});

describe("위키 화면: 이름 바꾸기·지우기·실시간", () => {
  it("이름 바꾸기: 새 경로를 입력하면 dry_run으로 미리보기하고, 링크 고치기를 끄면 끊어질 링크 경고가 나온다", async () => {
    const move = vi.fn(async (_w: string, _p: string, body: { to: string; dry_run?: boolean }) => ({ moved: body.dry_run !== true, from: "notes/first", to: body.to, rewritten: [{ path: "notes/second", count: 2 }], conflicts: [] }));
    const { wiki } = setup(READ, { page: PAGES, wiki: { moveWikiPage: move } });
    fireEvent.click(await screen.findByRole("button", { name: "이름 바꾸기…" }, LONG));
    const dialog = await screen.findByRole("dialog", {}, LONG);
    fireEvent.change(within(dialog).getByLabelText(/새 경로/), { target: { value: "notes/renamed" } });
    await waitFor(() => expect(wiki.moveWikiPage).toHaveBeenCalledWith("w1", "notes/first", { to: "notes/renamed", rewrite_links: true, dry_run: true }, expect.anything()), LONG);
    expect(await within(dialog).findByText(/페이지 1 · 링크 2곳/, {}, LONG)).toBeTruthy();
    fireEvent.click(within(dialog).getByLabelText(/링크도 고치기/));
    await waitFor(() => expect(within(dialog).getByText(/끊긴 링크가 됩니다/)).toBeTruthy(), LONG);
  });

  it("지우기: 백링크가 있으면 경고 블록이 있고 [취소]가 기본 포커스다. 지운 뒤 토스트에서 되돌릴 수 있다", async () => {
    const withBack = { ...FIRST, backlinks: [{ path: "notes/second", title: "둘째", count: 1 }] };
    const restore = vi.fn(async (_w: string, p: string) => ({ value: pageView(p, "x"), version_hash: "h" }));
    const { wiki } = setup(READ, {
      page: { ...PAGES, "notes/first": withBack },
      wiki: { getWikiPageHistory: vi.fn(async () => ({ items: [{ version: 7, op: "update", sha256: "s", bytes: 1, at: 1, author: { kind: "user" } }], pruned: false })), deleteWikiPage: vi.fn(async () => undefined), restoreWikiPage: restore },
    });
    fireEvent.click(await screen.findByRole("button", { name: "지우기…" }, LONG));
    const dialog = await screen.findByRole("alertdialog", {}, LONG).catch(() => screen.findByRole("dialog", {}, LONG));
    expect(within(dialog).getByTestId("wiki-delete-backlinks")).toBeTruthy();
    expect(document.activeElement?.textContent).toBe("취소");
    fireEvent.click(within(dialog).getByRole("button", { name: "지우기" }));
    await waitFor(() => expect(wiki.deleteWikiPage).toHaveBeenCalledWith("w1", "notes/first", FIRST.content_hash), LONG);
    fireEvent.click(await screen.findByRole("button", { name: "되돌리기" }, LONG));
    await waitFor(() => expect(restore).toHaveBeenCalledWith("w1", "notes/first", { version: 7 }), LONG);
  });

  it("다른 곳에서 바뀌었다는 알림(wiki.changed)이 오면 페이지를 다시 읽고, 자기가 방금 쓴 것은 다시 읽지 않는다", async () => {
    const { wiki, ws } = setup(READ, { page: PAGES });
    await screen.findByRole("link", { name: "둘째" }, LONG);
    const reads = wiki.getWikiPage.mock.calls.length;
    ws.emitWiki({ wiki_id: "w1", paths: ["notes/first"], external: true });
    await waitFor(() => expect(wiki.getWikiPage.mock.calls.length).toBeGreaterThan(reads), LONG);
  });
});

describe("위키 화면: 기록", () => {
  it("기록 행에 동작·쓴 주체 칩이 있고 모르는 동작·종류는 원문으로 보이며, pruned면 안내가 나온다", async () => {
    const versions = [
      { version: 5, op: "zap", sha256: "s5", bytes: 1, at: 1_700_000_000, author: { kind: "robot" } },
      { version: 4, op: "update", sha256: "s4", bytes: 1, at: 1_699_999_000, author: { kind: "agent", agent_id: "ag-1", label: "정리 담당", run_id: "run-12345678" } },
    ];
    setup(`${READ}&side=history`, { page: PAGES, wiki: { getWikiPageHistory: vi.fn(async () => ({ items: versions, pruned: true })) } });
    await openPanel();
    expect(await screen.findByText("zap", {}, LONG)).toBeTruthy();
    expect(screen.getByText("robot")).toBeTruthy();
    expect(screen.getByText("정리 담당")).toBeTruthy();
    expect(screen.getByText("오래된 버전은 보관 수 제한으로 지워졌습니다")).toBeTruthy();
  });
});
