import * as React from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { WikiLink } from "@agent-console/contracts/wiki";
import { AuthorChip, OpChip } from "./Chips";
import { HistoryDiff } from "./HistoryDiff";
import { LinkGraph } from "./LinkGraph";
import { LinkList } from "./LinkList";
import { LintTable } from "./LintTable";
import { MovePageForm } from "./MovePageForm";
import { NewPageForm, folderSuggestions, type NewPageValue } from "./NewPageForm";
import { OutlinksPanel } from "./OutlinksPanel";
import { PageHistory } from "./PageHistory";
import { PageTree } from "./PageTree";
import { PageView, type PageViewHandle } from "./PageView";
import { RuleListEditor } from "./RuleListEditor";
import { SearchResults, searchOptionId, type SearchResultsHandle } from "./SearchResults";
import { SyntaxValueTree } from "./SyntaxValueTree";
import { manyPages, sampleDisplay, sampleGraph, sampleHits, sampleIssues, sampleLinks, samplePages, samplePageView, sampleVersions, SAMPLE_NOW } from "./testing";

afterEach(cleanup);

beforeAll(() => {
  // React Flow가 요구하는 브라우저 API(레이아웃 없는 DOM 에뮬레이터용)
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  if (!("DOMMatrixReadOnly" in globalThis)) {
    (globalThis as unknown as Record<string, unknown>).DOMMatrixReadOnly = class {
      m22 = 1;
      constructor(public transform?: string) {}
    };
  }
});

describe("AuthorChip·OpChip — 쓴 주체 4종 (수용 기준 17)", () => {
  const display = sampleDisplay();
  it("사람 · 에이전트(label) · 에이전트(id만) · 외부 · 모르는 종류", () => {
    const { container } = render(
      <div>
        <AuthorChip author={{ kind: "user" }} display={display} />
        <AuthorChip author={{ kind: "agent", agent_id: "ag-1", label: "이름표" }} display={display} />
        <AuthorChip author={{ kind: "agent", agent_id: "ag-2" }} display={display} />
        <AuthorChip author={{ kind: "external" }} display={display} />
        <AuthorChip author={{ kind: "robot" }} display={display} />
      </div>,
    );
    const texts = Array.from(container.querySelectorAll(".ac-wk-chip-text")).map((e) => e.textContent);
    expect(texts).toEqual(["사람", "이름표", "ag-2", "외부", "robot"]);
    const chips = container.querySelectorAll(".ac-wk-chip");
    expect(chips[4]!.getAttribute("data-tone")).toBe("neutral");
    expect(chips[4]!.getAttribute("data-kind-icon")).toBe("neutral");
    expect(chips[1]!.getAttribute("data-kind-icon")).toBe("agent");
  });
  it("실행 링크: 핸들러가 있으면 단추, 없으면 글자만", () => {
    const onOpenRun = vi.fn();
    const author = { kind: "agent", run_id: "run-1234567890", root_run_id: "root-1", node_path: ["a", "b"], agent_id: "x" };
    const { rerender } = render(<AuthorChip author={author} onOpenRun={onOpenRun} />);
    fireEvent.click(screen.getByRole("button", { name: "실행 run-1234" }));
    expect(onOpenRun).toHaveBeenCalledWith("run-1234567890", "root-1");
    expect(document.querySelector(".ac-wk-chip")?.getAttribute("title")).toContain("노드 a › b");
    rerender(<AuthorChip author={author} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("실행 run-1234")).toBeTruthy();
  });
  it("동작 칩: 아는 값은 이름·톤, 모르는 값은 원문 + 중립", () => {
    const { container } = render(
      <div>
        <OpChip op="create" display={display} />
        <OpChip op="zap" display={display} />
      </div>,
    );
    const chips = container.querySelectorAll(".ac-md-chip");
    expect(chips[0]!.textContent).toBe("만듦");
    expect(chips[0]!.getAttribute("data-tone")).toBe("success");
    expect(chips[1]!.textContent).toBe("zap");
    expect(chips[1]!.getAttribute("data-tone")).toBe("neutral");
  });
});

describe("PageTree", () => {
  const pages = samplePages();
  it("빈 목록과 거르기 결과 없음", () => {
    const { rerender } = render(<PageTree pages={[]} expanded={new Set()} onExpandedChange={() => undefined} />);
    expect(screen.getByText("페이지가 없습니다")).toBeTruthy();
    rerender(<PageTree pages={pages} expanded={new Set()} onExpandedChange={() => undefined} filter="없는 글자" />);
    expect(screen.getByText("조건에 맞는 페이지가 없습니다")).toBeTruthy();
  });
  it("상태는 아이콘 + 이름: 끊긴 링크·고아·첫 페이지·저장 안 됨이 접근성 이름에 있다", () => {
    render(<PageTree pages={pages} expanded={new Set(["notes"])} onExpandedChange={() => undefined} dirtyPaths={new Set(["notes/second"])} />);
    const names = screen.getAllByRole("treeitem").map((e) => e.getAttribute("aria-label"));
    expect(names).toContain("첫째, 끊긴 링크 2개");
    expect(names).toContain("혼자, 고아 페이지");
    expect(names).toContain("처음, 첫 페이지");
    expect(names).toContain("둘째, 저장 안 됨");
    expect(names).toContain("폴더 notes, 페이지 4개");
  });
  it("키보드: 방향키·Enter 선택, →/← 펼침·접힘, F2·Delete, 폴더에는 F2·Delete 없음", () => {
    const onSelect = vi.fn();
    const onExpandedChange = vi.fn();
    const onRename = vi.fn();
    const onDelete = vi.fn();
    render(<PageTree pages={pages} expanded={new Set()} onExpandedChange={onExpandedChange} onSelect={onSelect} onRename={onRename} onDelete={onDelete} />);
    const tree = screen.getByRole("tree");
    fireEvent.keyDown(tree, { key: "F2" }); // 첫 행은 폴더
    fireEvent.keyDown(tree, { key: "Delete" });
    expect(onRename).not.toHaveBeenCalled();
    expect(onDelete).not.toHaveBeenCalled();
    fireEvent.keyDown(tree, { key: "ArrowRight" });
    expect(onExpandedChange).toHaveBeenCalled();
    expect([...(onExpandedChange.mock.calls[0]![0] as Set<string>)]).toEqual(["deep"]);
    fireEvent.keyDown(tree, { key: "End" });
    fireEvent.keyDown(tree, { key: "F2" });
    expect(onRename).toHaveBeenCalledWith("lonely");
    fireEvent.keyDown(tree, { key: "Delete" });
    expect(onDelete).toHaveBeenCalledWith("lonely");
    fireEvent.keyDown(tree, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("lonely");
  });
  it("IME 조합 중에는 키를 가로채지 않는다", () => {
    const onSelect = vi.fn();
    render(<PageTree pages={pages} expanded={new Set()} onExpandedChange={() => undefined} onSelect={onSelect} />);
    fireEvent.keyDown(screen.getByRole("tree"), { key: "Enter", isComposing: true });
    expect(onSelect).not.toHaveBeenCalled();
  });
  it("잘림 안내: total이 있으면 개수, 없으면 일반 문구", () => {
    const { rerender } = render(<PageTree pages={pages} expanded={new Set()} onExpandedChange={() => undefined} truncated total={500} maxPages={100} />);
    expect(screen.getByText("페이지 500개 중 100개까지만 불러왔습니다. 본문 검색을 쓰세요.")).toBeTruthy();
    rerender(<PageTree pages={pages} expanded={new Set()} onExpandedChange={() => undefined} truncated />);
    expect(screen.getByText("일부 페이지만 불러왔습니다. 본문 검색을 쓰세요.")).toBeTruthy();
  });
  it("가상 목록: 10,000개에서 DOM 행 수가 한 화면 + 여유 이하 (수용 기준 5)", () => {
    const all = manyPages(10_000);
    const folders = new Set(all.map((p) => p.path.split("/")[0]!));
    render(<PageTree pages={all} expanded={folders} onExpandedChange={() => undefined} height={400} />);
    expect(screen.getAllByRole("treeitem").length).toBeLessThanOrEqual(480 / 28 + 17);
  });
  it("폴더 클릭은 펼침 토글, 페이지 클릭은 선택, 우클릭은 메뉴 콜백", () => {
    const onExpandedChange = vi.fn();
    const onSelect = vi.fn();
    const onContextMenu = vi.fn();
    render(<PageTree pages={pages} expanded={new Set(["notes"])} onExpandedChange={onExpandedChange} onSelect={onSelect} onContextMenu={onContextMenu} />);
    fireEvent.click(screen.getByRole("treeitem", { name: /^폴더 deep/ }));
    expect([...(onExpandedChange.mock.calls[0]![0] as Set<string>)].sort()).toEqual(["deep", "notes"]);
    fireEvent.click(screen.getByRole("treeitem", { name: "둘째" }));
    expect(onSelect).toHaveBeenCalledWith("notes/second");
    fireEvent.contextMenu(screen.getByRole("treeitem", { name: "둘째" }));
    expect(onContextMenu.mock.calls[0]![0]).toMatchObject({ kind: "page", key: "notes/second" });
  });
});

describe("PageView — 링크 모양 (수용 기준 6~9)", () => {
  const page = samplePageView();
  function setup(extra: Partial<React.ComponentProps<typeof PageView>> = {}) {
    const mocks = { onOpenPage: vi.fn(), onCreatePage: vi.fn(), onOpenScheme: vi.fn() };
    const view = render(<PageView page={page} {...mocks} {...extra} />);
    return { ...mocks, ...view };
  }
  it("한글·이모지 본문에서 링크가 정확한 글자에 걸린다", () => {
    const { container } = setup();
    const ok = container.querySelector<HTMLElement>('[data-wiki-status="ok"]')!;
    expect(ok.textContent).toBe("둘째");
    expect(ok.tagName).toBe("A");
    expect(container.querySelector("h1")?.textContent).toBe("시작 😀");
    expect(container.textContent).toContain("🙂🙂");
    expect(container.textContent).not.toContain("[[");
  });
  it("페이지 링크: 앱 안 이동(새 탭 아님), 절 인자", () => {
    const view = setup();
    fireEvent.click(view.container.querySelector('[data-wiki-status="ok"]')!);
    expect(view.onOpenPage).toHaveBeenCalledWith("notes/second", null);
  });
  it("끊긴 링크: 이름에 이유, 클릭하면 팝오버, [이 페이지 만들기]는 제안 경로를 넘긴다", () => {
    const view = setup();
    const broken = screen.getByRole("button", { name: "끊긴 링크: ‘없는곳’ 페이지가 없습니다" });
    expect(broken.querySelector('[data-icon="link-broken"]')).toBeTruthy();
    fireEvent.click(broken);
    const pop = screen.getByRole("group", { name: "끊긴 링크" });
    fireEvent.click(within(pop).getByRole("button", { name: "이 페이지 만들기" }));
    expect(view.onCreatePage).toHaveBeenCalledTimes(1);
    expect(view.onCreatePage.mock.calls[0]![1]).toBe("notes/none");
    expect(screen.queryByRole("group", { name: "끊긴 링크" })).toBeNull();
  });
  it("끊긴 링크 + suggested_path 없음이면 target을 제안 경로로", () => {
    const links: WikiLink[] = sampleLinks().map((l) => (l.status === "broken" ? { ...l, suggested_path: null } : l));
    const onCreatePage = vi.fn();
    render(<PageView page={samplePageView({ links })} onCreatePage={onCreatePage} />);
    fireEvent.click(screen.getByRole("button", { name: /끊긴 링크: ‘없는곳’/ }));
    fireEvent.click(screen.getByRole("button", { name: "이 페이지 만들기" }));
    expect(onCreatePage.mock.calls[0]![1]).toBe("없는곳");
  });
  it("읽기 전용: 만들기가 aria-disabled이고 호출되지 않는다", () => {
    const onCreatePage = vi.fn();
    render(<PageView page={page} readOnly readOnlyReason="폴더에 쓸 수 없습니다" onCreatePage={onCreatePage} />);
    fireEvent.click(screen.getByRole("button", { name: /끊긴 링크/ }));
    const create = screen.getByRole("button", { name: "이 페이지 만들기" });
    expect(create.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(create);
    expect(onCreatePage).not.toHaveBeenCalled();
    expect(screen.getByText("폴더에 쓸 수 없습니다")).toBeTruthy();
  });
  it("스킴 링크: 이동 가능하면 단추, 화면이 없으면 글자 + 툴팁", () => {
    const view = setup({ canOpenScheme: () => true });
    fireEvent.click(view.container.querySelector<HTMLElement>('[data-wiki-status="scheme"]')!);
    expect(view.onOpenScheme).toHaveBeenCalledTimes(1);
    cleanup();
    const { container } = render(<PageView page={page} onOpenScheme={vi.fn()} canOpenScheme={() => false} />);
    const off = container.querySelector<HTMLElement>('[data-wiki-status="scheme"]')!;
    expect(off.tagName).toBe("SPAN");
    expect(off.getAttribute("title")).toBe("연결된 기능이 꺼져 있습니다");
  });
  it("폴더 밖 링크: aria-disabled, 클릭 무시, 이유 툴팁", () => {
    const view = setup();
    const out = view.container.querySelector<HTMLElement>('[data-wiki-status="outside"]')!;
    expect(out.getAttribute("aria-disabled")).toBe("true");
    expect(out.getAttribute("title")).toContain("폴더 밖");
    fireEvent.click(out);
    expect(view.onOpenPage).not.toHaveBeenCalled();
  });
  it("모르는 status는 글자만(동작 없음) + 중립", () => {
    const links = [{ ...sampleLinks()[0]!, status: "future-x" }];
    const onOpenPage = vi.fn();
    const { container } = render(<PageView page={samplePageView({ links })} onOpenPage={onOpenPage} display={sampleDisplay()} />);
    const el = container.querySelector<HTMLElement>('[data-wiki-status="future-x"]')!;
    expect(el.tagName).toBe("SPAN");
    expect(el.textContent).toBe("둘째");
    fireEvent.click(el);
    expect(onOpenPage).not.toHaveBeenCalled();
  });
  it("status가 비면 unknown으로 중립", () => {
    const { container } = render(<PageView page={samplePageView({ links: [{ ...sampleLinks()[0]!, status: "" }] })} />);
    expect(container.querySelector('[data-wiki-status="unknown"]')).toBeTruthy();
  });
  it("링크가 없으면(문법 없음) 일반 마크다운으로 그리고 외부 링크는 새 탭", () => {
    const { container } = render(<PageView page={samplePageView({ content: "# 제목\n\n[바깥](https://example.com) [[그대로]]", links: [] })} />);
    const a = container.querySelector<HTMLAnchorElement>("a")!;
    expect(a.getAttribute("target")).toBe("_blank");
    expect(a.getAttribute("rel")).toBe("noopener noreferrer");
    expect(container.textContent).toContain("[[그대로]]");
  });
  it("위험한 스킴 주소는 막는다", () => {
    const { container } = render(<PageView page={samplePageView({ content: "[x](javascript:alert(1))", links: [] })} />);
    expect(container.querySelector("a")?.getAttribute("href") ?? "").toBe("");
  });
  it("빈 본문", () => {
    render(<PageView page={samplePageView({ content: "  ", links: [] })} />);
    expect(screen.getByText("이 페이지는 비어 있습니다.")).toBeTruthy();
  });
  it("핸들: 링크로 스크롤·포커스, 절 찾기(대소문자 무시)와 앵커 미스 알림", async () => {
    const ref = createRef<PageViewHandle>();
    const onAnchorMissing = vi.fn();
    const { container, rerender } = render(<PageView page={page} handleRef={ref} />);
    const start = sampleLinks()[1]!.start;
    expect(ref.current!.scrollToLink(start)).toBe(true);
    expect(ref.current!.scrollToLink(99999)).toBe(false);
    expect(ref.current!.scrollToHeading("시작 😀")).toBe(true);
    expect(ref.current!.scrollToHeading("없는 절")).toBe(false);
    rerender(<PageView page={page} anchor="없는 절" onAnchorMissing={onAnchorMissing} />);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40));
    });
    expect(onAnchorMissing).toHaveBeenCalledWith("없는 절");
    expect(container.querySelector("h1")).toBeTruthy();
  });
  it("강조: highlightStart와 같은 링크에 data-highlight", () => {
    const start = sampleLinks()[0]!.start;
    const { container } = render(<PageView page={page} highlightStart={start} />);
    expect(container.querySelector(`[data-wiki-link="${start}"]`)?.hasAttribute("data-highlight")).toBe(true);
  });
});

describe("OutlinksPanel", () => {
  const page = samplePageView();
  it("본문 순서로 모든 링크(같은 대상도 합치지 않음), 상태 글은 표시 표, 모르는 상태는 원문", () => {
    const links = [...sampleLinks(), { ...sampleLinks()[0]!, start: 1, end: 2, status: "mystery" }];
    render(<OutlinksPanel content={page.content} links={links} display={sampleDisplay()} />);
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(5);
    expect(rows[0]!.getAttribute("data-status")).toBe("mystery");
    expect(within(rows[0]!).getAllByText("mystery").length).toBeGreaterThan(0);
    expect(within(rows[2]!).getByText("끊긴 링크")).toBeTruthy();
  });
  it("호버·포커스는 강조 콜백, 클릭은 위치 이동, Enter는 열기, 끊긴 행은 만들기", () => {
    const onHover = vi.fn();
    const onLocate = vi.fn();
    const onOpen = vi.fn();
    const onCreate = vi.fn();
    render(<OutlinksPanel content={page.content} links={page.links ?? []} onHover={onHover} onLocate={onLocate} onOpen={onOpen} onCreate={onCreate} />);
    const row = screen.getAllByRole("listitem")[0]!;
    fireEvent.mouseEnter(row);
    expect(onHover).toHaveBeenLastCalledWith(expect.objectContaining({ status: "ok" }));
    fireEvent.mouseLeave(row);
    expect(onHover).toHaveBeenLastCalledWith(null);
    const btn = within(row).getByRole("button");
    fireEvent.click(btn);
    expect(onLocate).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(btn, { key: "Enter" });
    expect(onOpen).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "‘없는곳’ 페이지 만들기" }));
    expect(onCreate).toHaveBeenCalledTimes(1);
  });
  it("읽기 전용이면 만들기 aria-disabled, 링크 0개면 빈 안내", () => {
    const onCreate = vi.fn();
    const { rerender } = render(<OutlinksPanel content={page.content} links={page.links ?? []} onCreate={onCreate} readOnly />);
    const create = screen.getByRole("button", { name: "‘없는곳’ 페이지 만들기" });
    expect(create.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(create);
    expect(onCreate).not.toHaveBeenCalled();
    rerender(<OutlinksPanel content="" links={[]} />);
    expect(screen.getByText("이 페이지에서 나가는 링크가 없습니다")).toBeTruthy();
  });
});

describe("PageHistory·HistoryDiff — 기록 쓴 주체 4종 (수용 기준 17)", () => {
  it("행: op 칩 + 쓴 주체 칩(label, 없으면 id, 종류), 모르는 op·kind는 원문 + 중립", () => {
    const { container } = render(<PageHistory versions={sampleVersions()} display={sampleDisplay()} now={SAMPLE_NOW} currentVersion={5} />);
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(4);
    expect(within(rows[0]!).getByText("정리 담당")).toBeTruthy();
    expect(within(rows[0]!).getByText("현재")).toBeTruthy();
    expect(within(rows[0]!).getByText("고침")).toBeTruthy();
    expect(within(rows[1]!).getByText("zap")).toBeTruthy();
    expect(within(rows[1]!).getByText("robot")).toBeTruthy();
    expect(within(rows[2]!).getByText("외부 변경")).toBeTruthy();
    expect(within(rows[3]!).getByText("사람")).toBeTruthy();
    expect(container.querySelectorAll('.ac-md-chip[data-tone="neutral"]').length).toBeGreaterThan(0);
    expect(within(rows[0]!).getByText("방금")).toBeTruthy();
  });
  it("비교·되돌리기 콜백, 막는 이유가 있으면 되돌리기 aria-disabled", () => {
    const onCompare = vi.fn();
    const onRestore = vi.fn();
    const { rerender } = render(<PageHistory versions={sampleVersions()} now={SAMPLE_NOW} onCompare={onCompare} onRestore={onRestore} />);
    fireEvent.click(screen.getByRole("button", { name: "v3 비교" }));
    expect(onCompare).toHaveBeenCalledWith(expect.objectContaining({ version: 3 }));
    fireEvent.click(screen.getByRole("button", { name: "v3(으)로 되돌리기" }));
    expect(onRestore).toHaveBeenCalledTimes(1);
    rerender(<PageHistory versions={sampleVersions()} now={SAMPLE_NOW} onRestore={onRestore} restoreDisabledReason="먼저 저장하세요" />);
    const b = screen.getByRole("button", { name: "v3(으)로 되돌리기" });
    expect(b.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(b);
    expect(onRestore).toHaveBeenCalledTimes(1);
  });
  it("pruned일 때만 지워짐 문구, 기록 없음·기록 저장소 없음 상태", () => {
    const { rerender } = render(<PageHistory versions={sampleVersions()} now={SAMPLE_NOW} />);
    expect(screen.queryByText("오래된 버전은 보관 수 제한으로 지워졌습니다")).toBeNull();
    rerender(<PageHistory versions={sampleVersions()} now={SAMPLE_NOW} pruned />);
    expect(screen.getByText("오래된 버전은 보관 수 제한으로 지워졌습니다")).toBeTruthy();
    rerender(<PageHistory versions={[]} />);
    expect(screen.getByText(/아직 기록이 없습니다/)).toBeTruthy();
    const onSettings = vi.fn();
    rerender(<PageHistory versions={[]} unavailable onOpenProjectSettings={onSettings} />);
    expect(screen.getByText("이 위키는 기록을 저장하지 않습니다")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "프로젝트 설정 보기" }));
    expect(onSettings).toHaveBeenCalled();
  });
  it("실행 링크는 콜백이 있을 때만 단추", () => {
    const onOpenRun = vi.fn();
    render(<PageHistory versions={sampleVersions()} now={SAMPLE_NOW} onOpenRun={onOpenRun} />);
    fireEvent.click(screen.getByRole("button", { name: "실행 run-1234" }));
    expect(onOpenRun).toHaveBeenCalledWith("run-1234567890", "root-1");
  });
  it("HistoryDiff: 이전이 없으면 현재 본문과 비교로 자동 전환하고 안내, Esc로 닫기", () => {
    const onClose = vi.fn();
    render(<HistoryDiff version={1} content={"가\n"} previousContent={null} currentContent={"가\n나\n"} onClose={onClose} />);
    expect(screen.getByText("이전 버전이 없습니다 — 현재 본문과 비교합니다")).toBeTruthy();
    expect(screen.getByRole("button", { name: "이전 버전과" }).getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByRole("button", { name: "현재 본문과" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.keyDown(screen.getByRole("region", { name: "v1 비교" }), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
  it("HistoryDiff: 같으면 차이 없음, 기준 전환 콜백", () => {
    const onBaseChange = vi.fn();
    render(<HistoryDiff version={4} content="같음" previousContent="같음" currentContent="다름" onBaseChange={onBaseChange} />);
    expect(screen.getByText("비교할 차이가 없습니다.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "현재 본문과" }));
    expect(onBaseChange).toHaveBeenCalledWith("current");
  });
});

describe("LinkGraph·LinkList", () => {
  it("빈 그래프", () => {
    render(<LinkGraph graph={{ nodes: [], edges: [] }} />);
    expect(screen.getByText("그래프에 그릴 페이지가 없습니다")).toBeTruthy();
  });
  it("접근성 이름의 노드 수, 배치 엔진 호출, 노드 종류는 모양·아이콘, 같은 입력=같은 엔진 입력", async () => {
    const engine = vi.fn<(input: { nodes: Array<{ id: string }> }) => Promise<Record<string, { x: number; y: number }>>>(async () => ({ a: { x: 0, y: 0 }, b: { x: 300, y: 0 }, c: { x: 0, y: 200 }, d: { x: 600, y: 0 }, e: { x: 300, y: 200 } }));
    const { container } = render(<LinkGraph graph={sampleGraph()} centerPath="a" engine={engine} height={400} />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(engine).toHaveBeenCalledTimes(1);
    const input = engine.mock.calls[0]![0];
    expect(input.nodes.map((n) => n.id)).toEqual(["a", "b", "c", "d", "e"]);
    const group = screen.getByRole("group", { name: /^링크 그래프, 노드 5개/ });
    expect(group.getAttribute("tabindex")).toBe("0");
    expect(container.querySelector('.ac-wk-gnode[data-center]')).toBeTruthy();
    expect(container.querySelector('.ac-wk-gnode[data-kind="broken"] [data-icon="link-broken"]')).toBeTruthy();
    expect(container.querySelector('.ac-wk-gnode[data-kind="orphan"] [data-icon="page-orphan"]')).toBeTruthy();
    expect(container.querySelector('.ac-wk-gnode[data-kind="scheme"] [data-icon="external-link"]')).toBeTruthy();
  });
  it("배치 엔진이 실패하면 격자로 남고 안내한다", async () => {
    render(<LinkGraph graph={sampleGraph()} engine={async () => { throw new Error("x"); }} />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("자동 배치를 쓸 수 없어 격자로 놓았습니다")).toBeTruthy();
  });
  it("잘림 안내: total이 있으면 개수, 없으면 일반 문구", async () => {
    const engine = async () => ({});
    const { rerender } = render(<LinkGraph graph={{ ...sampleGraph(), truncated: true, total: 900 }} engine={engine} />);
    expect(screen.getByText("900개 중 5개만 표시했습니다")).toBeTruthy();
    rerender(<LinkGraph graph={{ ...sampleGraph(), truncated: true, total: null }} engine={engine} />);
    expect(screen.getByText("일부만 표시했습니다")).toBeTruthy();
  });
  it("키보드: 방향키 이동은 onSelect, Enter 열기, Shift+Enter·C 중심, Home 중심 노드", async () => {
    const engine = async () => ({ a: { x: 0, y: 0 }, b: { x: 300, y: 0 }, c: { x: 0, y: 200 }, d: { x: 600, y: 0 }, e: { x: 300, y: 200 } });
    const onSelect = vi.fn();
    const onOpen = vi.fn();
    const onCenter = vi.fn();
    render(<LinkGraph graph={sampleGraph()} centerPath="a" engine={engine} onSelect={onSelect} onOpen={onOpen} onCenter={onCenter} />);
    await act(async () => {
      await Promise.resolve();
    });
    const g = screen.getByRole("group", { name: /^링크 그래프/ });
    fireEvent.focus(g);
    fireEvent.keyDown(g, { key: "ArrowRight" });
    expect(onSelect).toHaveBeenLastCalledWith("b");
    fireEvent.keyDown(g, { key: "ArrowDown" });
    expect(onSelect).toHaveBeenLastCalledWith("e");
    fireEvent.keyDown(g, { key: "Enter" });
    expect(onOpen).toHaveBeenLastCalledWith(expect.objectContaining({ path: "e", scheme: "x" }));
    fireEvent.keyDown(g, { key: "Enter", shiftKey: true });
    expect(onCenter).toHaveBeenLastCalledWith("e");
    fireEvent.keyDown(g, { key: "c" });
    expect(onCenter).toHaveBeenCalledTimes(2);
    fireEvent.keyDown(g, { key: "Home" });
    expect(onSelect).toHaveBeenLastCalledWith("a");
    fireEvent.keyDown(g, { key: "ArrowUp" }); // 위에 노드 없음 → 무시
    expect(onSelect).toHaveBeenLastCalledWith("a");
  });

  it("연결 목록: 노드·엣지 수가 그래프와 같고 중심 먼저, 끊긴 대상 표시", () => {
    render(<LinkList graph={sampleGraph()} centerPath="b" />);
    const items = screen.getAllByRole("treeitem");
    const groups = items.filter((e) => e.getAttribute("data-kind") === "group");
    expect(groups).toHaveLength(5);
    expect(groups[0]!.textContent).toContain("나");
    expect(groups[0]!.textContent).toContain("현재");
    const outRows = items.filter((e) => e.getAttribute("data-kind") === "out");
    const inRows = items.filter((e) => e.getAttribute("data-kind") === "in");
    expect(outRows).toHaveLength(5); // 엣지 수
    expect(inRows).toHaveLength(5);
    expect(screen.getAllByText("끊긴 링크").length).toBeGreaterThan(0);
    expect(screen.getAllByText("×3").length).toBeGreaterThan(0);
  });
  it("연결 목록: 거르기·접기·Enter 열기·Shift+Enter 중심", () => {
    const onOpen = vi.fn();
    const onCenter = vi.fn();
    const onSelect = vi.fn();
    render(<LinkList graph={sampleGraph()} onOpen={onOpen} onCenter={onCenter} onSelect={onSelect} />);
    const tree = screen.getByRole("tree");
    fireEvent.keyDown(tree, { key: "ArrowLeft" }); // 첫 그룹 접기
    expect(screen.getAllByRole("treeitem").length).toBeLessThan(15);
    fireEvent.keyDown(tree, { key: "Enter" });
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ path: "a" }));
    fireEvent.keyDown(tree, { key: "Enter", shiftKey: true });
    expect(onCenter).toHaveBeenCalledWith("a");
    fireEvent.change(screen.getByRole("searchbox", { name: "제목·경로 거르기" }), { target: { value: "없는것" } });
    expect(screen.getByText("조건에 맞는 항목이 없습니다")).toBeTruthy();
  });
  it("연결 목록: 빈 그래프·잘림 안내", () => {
    const { rerender } = render(<LinkList graph={{ nodes: [] }} />);
    expect(screen.getByText("표시할 페이지가 없습니다")).toBeTruthy();
    rerender(<LinkList graph={{ ...sampleGraph(), truncated: true }} />);
    expect(screen.getByText("일부만 표시했습니다")).toBeTruthy();
  });
});

describe("LintTable (수용 기준 22)", () => {
  const order = ["error", "warning", "info"];
  it("6열, 모르는 심각도·코드는 원문 + 중립, 심각도 순서로 정렬", () => {
    const { container } = render(<LintTable issues={sampleIssues()} display={sampleDisplay()} severityOrder={order} />);
    expect(screen.getAllByRole("columnheader")).toHaveLength(6);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]!.textContent).toContain("오류");
    expect(rows[rows.length - 1]!.textContent).toContain("purple");
    expect(container.querySelector('.ac-md-chip[data-tone="neutral"]')?.textContent).toBe("purple");
    expect(within(rows[rows.length - 1]!).getByText("custom_x")).toBeTruthy();
    // 줄·규칙 열
    expect(rows[0]!.textContent).toContain("no-secrets");
    expect(within(rows[0]!).getByText("12")).toBeTruthy();
  });
  it("거르기 목록은 데이터에서: 심각도·코드·페이지, 결과 없음에서 지우기", () => {
    render(<LintTable issues={sampleIssues()} display={sampleDisplay()} severityOrder={order} />);
    expect(screen.getByRole("button", { name: /^purple/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /^purple/ }));
    expect(screen.getAllByRole("row")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: /^purple/ }));
    fireEvent.change(screen.getByRole("combobox", { name: "코드 거르기" }), { target: { value: "orphan" } });
    expect(screen.getAllByRole("row")).toHaveLength(2);
    fireEvent.change(screen.getByRole("searchbox", { name: "페이지 경로 거르기" }), { target: { value: "zzz" } });
    expect(screen.getByText(/조건에 맞는 항목이 없습니다/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "거르기 지우기" }));
    expect(screen.getAllByRole("row").length).toBe(5);
  });
  it("열 머리 정렬(aria-sort)", () => {
    render(<LintTable issues={sampleIssues()} severityOrder={order} />);
    const page = screen.getByRole("columnheader", { name: /페이지/ });
    expect(page.getAttribute("aria-sort")).toBe("none");
    fireEvent.click(within(page).getByRole("button"));
    expect(page.getAttribute("aria-sort")).toBe("ascending");
    fireEvent.click(within(page).getByRole("button"));
    expect(page.getAttribute("aria-sort")).toBe("descending");
  });
  it("행 키보드: ↓ Enter로 열기(줄 포함), Shift+F10 메뉴", () => {
    const onOpen = vi.fn();
    const onContextMenu = vi.fn();
    render(<LintTable issues={sampleIssues()} severityOrder={order} onOpen={onOpen} onContextMenu={onContextMenu} />);
    const grid = screen.getByRole("grid");
    fireEvent.keyDown(grid, { key: "Enter" });
    expect(onOpen).toHaveBeenLastCalledWith(expect.objectContaining({ code: "wiki.rule_violation" }), 12);
    fireEvent.keyDown(grid, { key: "ArrowDown" });
    fireEvent.keyDown(grid, { key: "Enter" });
    expect(onOpen).toHaveBeenLastCalledWith(expect.objectContaining({ severity: "warning" }), 3);
    fireEvent.keyDown(grid, { key: "F10", shiftKey: true });
    expect(onContextMenu).toHaveBeenCalledTimes(1);
  });
  it("문제 없음", () => {
    render(<LintTable issues={[]} />);
    expect(screen.getByText("문제가 없습니다")).toBeTruthy();
  });
  it("3000건에서도 DOM 행 수가 한 화면 + 여유 이하", () => {
    render(<LintTable issues={sampleIssues(3000)} severityOrder={order} height={400} />);
    expect(screen.getAllByRole("row").length).toBeLessThanOrEqual(480 / 32 + 17 + 1);
  });
});

describe("SearchResults — marks 강조 (수용 기준 19)", () => {
  it("서버 marks 범위(한글·이모지 섞인 조각)를 강조 span으로", () => {
    const { container } = render(<SearchResults hits={sampleHits()} query="한글검색어" />);
    const hl = container.querySelectorAll("[data-hl]");
    expect(hl).toHaveLength(1);
    expect(hl[0]!.textContent).toBe("한글검색어");
    expect(container.querySelector("mark")).toBeNull();
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });
  it("조각은 HTML이 아니라 글자다", () => {
    const { container } = render(<SearchResults hits={[{ path: "p", snippet: "<b>x</b> & <script>", marks: [] }]} query="q" />);
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<b>x</b> & <script>");
  });
  it("0건·저하·잘림 안내", () => {
    const { rerender } = render(<SearchResults hits={[]} query="찾는말" />);
    expect(screen.getByText("‘찾는말’와 맞는 페이지가 없습니다")).toBeTruthy();
    rerender(<SearchResults hits={sampleHits()} query="q" degraded truncated />);
    expect(screen.getByText(/파일을 하나씩 읽는 방식/)).toBeTruthy();
    expect(screen.getByText("결과가 많아 일부만 표시했습니다")).toBeTruthy();
  });
  it("활성 행·핸들(move/openActive)·입력 칸용 id", () => {
    const onOpen = vi.fn();
    const ref = createRef<SearchResultsHandle>();
    render(<SearchResults hits={sampleHits()} query="q" id="sr" handleRef={ref} onOpen={onOpen} />);
    expect(screen.getByRole("listbox").getAttribute("aria-activedescendant")).toBe(searchOptionId("sr", 0));
    act(() => ref.current!.move(1));
    expect(screen.getByRole("listbox").getAttribute("aria-activedescendant")).toBe(searchOptionId("sr", 1));
    act(() => ref.current!.move(5));
    expect(screen.getByRole("listbox").getAttribute("aria-activedescendant")).toBe(searchOptionId("sr", 1));
    act(() => {
      expect(ref.current!.openActive()).toBe(true);
    });
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ path: "index" }));
    fireEvent.click(screen.getAllByRole("option")[0]!);
    expect(onOpen).toHaveBeenLastCalledWith(expect.objectContaining({ path: "notes/second" }));
  });
});

describe("NewPageForm", () => {
  const templates = [
    { id: "t1", title: "틀 하나", file: "a.md", path: "log/{date}", rule_id: "r", variables: [{ name: "date", builtin: true }, { name: "주제", title: "주제", example: "예" }] },
    { id: "t2", file: "b.md", rule_id: "r", variables: [] },
  ];
  const empty: NewPageValue = { path: "", title: "", templateId: null, variables: {} };
  function Harness(p: Partial<React.ComponentProps<typeof NewPageForm>> & { start?: NewPageValue }) {
    const { start, ...rest } = p;
    const [v, setV] = React.useState(start ?? empty);
    return <NewPageForm value={v} onChange={setV} templates={templates} onSubmit={() => undefined} {...rest} />;
  }
  it("틀이 0개면 빈 페이지만, 있으면 라디오 + 선택 시 콜백, 내장 변수는 입력받지 않고 선언 변수만", () => {
    const onTemplateChange = vi.fn();
    const { rerender } = render(<NewPageForm value={empty} onChange={() => undefined} templates={[]} onSubmit={() => undefined} />);
    expect(screen.getAllByRole("radio")).toHaveLength(1);
    rerender(<Harness onTemplateChange={onTemplateChange} />);
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    fireEvent.click(screen.getByRole("radio", { name: /틀 하나/ }));
    expect(onTemplateChange).toHaveBeenCalledWith("t1");
    expect(screen.getByLabelText("주제")).toBeTruthy();
    expect(screen.queryByLabelText("date")).toBeNull();
    expect(screen.getByRole("radio", { name: /t2/ })).toBeTruthy();
  });
  it("경로: 폴더 제안(최대 8, 앞부분 일치), Tab으로 확정, 이미 있는 페이지 경고", () => {
    const existing = ["notes/a", "notes/sub/b", "other/c"];
    expect(folderSuggestions(existing, "no")).toEqual(["notes/", "notes/sub/"]);
    expect(folderSuggestions(existing, "notes/")).toEqual(["notes/sub/"]);
    expect(folderSuggestions(Array.from({ length: 20 }, (_, i) => `f${i}/x`), "", 8)).toHaveLength(8);
    const onOpenExisting = vi.fn();
    render(<Harness existingPaths={existing} onOpenExisting={onOpenExisting} />);
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "no" } });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Tab" });
    expect((input as HTMLInputElement).value).toBe("notes/");
    fireEvent.change(input, { target: { value: "notes/a" } });
    fireEvent.click(screen.getByRole("button", { name: "열기" }));
    expect(onOpenExisting).toHaveBeenCalledWith("notes/a");
  });
  it("제출: 경로가 비면 aria-disabled, 읽기 전용이면 이유, 서버 메시지는 칸 아래·배너", () => {
    const onSubmit = vi.fn();
    const { rerender } = render(<NewPageForm value={empty} onChange={() => undefined} templates={[]} onSubmit={onSubmit} />);
    const submit = screen.getByRole("button", { name: "만들기" });
    expect(submit.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(submit);
    expect(onSubmit).not.toHaveBeenCalled();
    rerender(<NewPageForm value={{ ...empty, path: "x" }} onChange={() => undefined} templates={[]} onSubmit={onSubmit} pathError="경로가 올바르지 않습니다" error="규칙 ‘r’: 막음" />);
    expect(screen.getByText("경로가 올바르지 않습니다")).toBeTruthy();
    expect(screen.getAllByRole("alert")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "만들기" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    rerender(<NewPageForm value={{ ...empty, path: "x" }} onChange={() => undefined} templates={[]} onSubmit={onSubmit} readOnly readOnlyReason="쓸 수 없는 폴더" />);
    expect(screen.getByRole("button", { name: "만들기" }).getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByText("쓸 수 없는 폴더")).toBeTruthy();
  });
  it("가져온 본문이 있으면 틀 선택이 잠기고 글자 수를 보인다", () => {
    render(<NewPageForm value={empty} onChange={() => undefined} templates={templates} onSubmit={() => undefined} prefilledChars={42} />);
    expect(screen.getByText("본문 42자 가져옴")).toBeTruthy();
    expect((screen.getByRole("radio", { name: /틀 하나/ }) as HTMLInputElement).disabled).toBe(true);
  });
});

describe("MovePageForm", () => {
  const preview = { from: "a", to: "b", moved: false, rewritten: [{ path: "x/one", count: 2 }, { path: "x/two", count: 3 }], conflicts: [] };
  const base = { from: "a", to: "b", onToChange: () => undefined, rewriteLinks: true, onRewriteLinksChange: () => undefined, onSubmit: () => undefined };
  it("미리보기: 바뀔 페이지·링크 수", () => {
    render(<MovePageForm {...base} preview={preview} />);
    expect(screen.getByText("페이지 2 · 링크 5곳")).toBeTruthy();
    expect(screen.getByText("x/one")).toBeTruthy();
  });
  it("같은 경로면 제출 막힘, 링크 고치기를 끄면 끊어질 링크 경고", () => {
    const onSubmit = vi.fn();
    const { rerender } = render(<MovePageForm {...base} to="a" onSubmit={onSubmit} />);
    const btn = screen.getByRole("button", { name: "이름 바꾸기" });
    expect(btn.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(btn);
    expect(onSubmit).not.toHaveBeenCalled();
    rerender(<MovePageForm {...base} rewriteLinks={false} preview={preview} onSubmit={onSubmit} />);
    expect(screen.getByText("링크는 고치지 않습니다. 2개 페이지의 링크 5곳이 끊긴 링크가 됩니다.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "이름 바꾸기" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
  it("충돌 페이지는 닫지 않고 목록에 남고 [열기]", () => {
    const onOpenPage = vi.fn();
    render(<MovePageForm {...base} result={{ ...preview, moved: true, conflicts: ["y/skip"] }} onOpenPage={onOpenPage} />);
    expect(screen.getByRole("alert").textContent).toContain("1개 페이지는 그사이 바뀌어 고치지 못했습니다");
    fireEvent.click(screen.getByRole("button", { name: "열기" }));
    expect(onOpenPage).toHaveBeenCalledWith("y/skip");
  });
  it("저장 안 됨 이유·서버 메시지·읽기 전용", () => {
    render(<MovePageForm {...base} blockedReason="먼저 저장하거나 변경을 버리세요" toError="이미 있는 페이지입니다" />);
    expect(screen.getByRole("button", { name: "이름 바꾸기" }).getAttribute("aria-disabled")).toBe("true");
    expect(screen.getAllByText("먼저 저장하거나 변경을 버리세요").length).toBeGreaterThan(0);
    expect(screen.getByRole("alert").textContent).toBe("이미 있는 페이지입니다");
  });
  it("미리보기 목록은 가상 목록", () => {
    const big = { ...preview, rewritten: Array.from({ length: 2000 }, (_, i) => ({ path: `p${i}`, count: 1 })) };
    render(<MovePageForm {...base} preview={big} />);
    expect(screen.getAllByRole("listitem").length).toBeLessThan(60);
  });
});

describe("RuleListEditor", () => {
  const value = [{ id: "r1", name: "규칙 가" }, { id: "r2", name: "규칙 나" }, { id: "gone", missing: true }];
  const summaries = { r1: { id: "r1", counts: { write: 2, lint: 0, templates: 1 }, has_instructions: true } };
  it("요약 줄·누락 danger 행·가져오기·빈 상태", () => {
    const onImport = vi.fn();
    const { rerender } = render(<RuleListEditor value={value} summaries={summaries} onChange={() => undefined} onImport={onImport} />);
    expect(screen.getByText("쓰기 2 · 틀 1 · 지침 있음")).toBeTruthy();
    expect(screen.getByText("‘gone’ 규칙이 이 프로젝트에 없습니다")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "공용에서 가져오기…" })[0]!);
    expect(onImport).toHaveBeenCalledWith("gone");
    rerender(<RuleListEditor value={[]} onChange={() => undefined} />);
    expect(screen.getByText(/쓰는 규칙이 없습니다/)).toBeTruthy();
  });
  it("순서·빼기·더하기는 새 id 목록으로 알린다 (Alt+↑/↓)", () => {
    const onChange = vi.fn();
    render(<RuleListEditor value={value} available={[{ id: "r9", name: "규칙 다" }]} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "규칙 나 위로" }));
    expect(onChange).toHaveBeenLastCalledWith(["r2", "r1", "gone"], { type: "move", id: "r2", from: 1, to: 0 });
    fireEvent.keyDown(screen.getAllByRole("listitem")[0]!, { key: "ArrowDown", altKey: true });
    expect(onChange).toHaveBeenLastCalledWith(["r2", "r1", "gone"], { type: "move", id: "r1", from: 0, to: 1 });
    fireEvent.click(screen.getByRole("button", { name: "규칙 가 빼기" }));
    expect(onChange).toHaveBeenLastCalledWith(["r2", "gone"], { type: "remove", id: "r1", index: 0 });
    fireEvent.click(screen.getByRole("button", { name: "규칙 더하기" }));
    fireEvent.click(screen.getByRole("menuitem", { name: /규칙 다/ }));
    expect(onChange).toHaveBeenLastCalledWith(["r1", "r2", "gone", "r9"], { type: "add", id: "r9", index: 3 });
  });
  it("중복 id는 warning 행, 읽기 전용이면 아무 것도 바뀌지 않는다", () => {
    const onChange = vi.fn();
    const { container } = render(<RuleListEditor value={[{ id: "r1", name: "가" }, { id: "r1", name: "가" }]} onChange={onChange} readOnly readOnlyReason="읽기 전용 폴더" />);
    expect(container.querySelectorAll('[data-tone="warning"]').length).toBeGreaterThan(1);
    fireEvent.click(screen.getAllByRole("button", { name: "가 빼기" })[0]!);
    fireEvent.click(screen.getByRole("button", { name: "규칙 더하기" }));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("읽기 전용 폴더")).toBeTruthy();
  });
});

describe("SyntaxValueTree (수용 기준 24)", () => {
  const syntax = {
    syntax: { links: [{ id: "l1", kind: "k", pattern: "\\[\\[(.+?)\\]\\]" }], case_insensitive: true, page_extensions: [".md"] },
    sources: { "/links": "rules:내규칙", "/case_insensitive": "settings", "/page_extensions": "mystery-src" },
  };
  it("최상위 키마다 블록 + 출처 배지, 모르는 출처는 원문, 규칙 출처는 id", () => {
    const onOpenSource = vi.fn();
    const { container } = render(<SyntaxValueTree syntax={syntax} display={sampleDisplay()} titles={{ links: "링크" }} onOpenSource={onOpenSource} />);
    expect(screen.getAllByRole("region")).toHaveLength(3);
    expect(screen.getByRole("region", { name: "링크" })).toBeTruthy();
    const badges = Array.from(container.querySelectorAll(".ac-md-source")).map((e) => e.textContent);
    expect(badges).toEqual(["출처: 규칙 내규칙", "출처: 설정", "출처: mystery-src"]);
    expect(container.textContent).toContain("\\[\\[(.+?)\\]\\]");
    fireEvent.click(screen.getAllByRole("button", { name: "열기" })[0]!);
    expect(onOpenSource).toHaveBeenCalledWith("rules:내규칙");
  });
  it("링크 규칙이 비면 warning, 문법이 없으면 안내", () => {
    const { rerender } = render(<SyntaxValueTree syntax={{ syntax: { links: [] }, empty: true }} />);
    expect(screen.getByText(/링크 규칙 없음/)).toBeTruthy();
    rerender(<SyntaxValueTree syntax={null} />);
    expect(screen.queryByText(/링크 규칙 없음/)).toBeNull();
    expect(screen.getByText("표시할 문법 값이 없습니다")).toBeTruthy();
  });
  it("더 구체적인 출처 포인터가 있으면 그 항목에도 배지", () => {
    const { container } = render(<SyntaxValueTree syntax={{ syntax: { links: [{ id: "a", kind: "k" }, { id: "b", kind: "k" }] }, sources: { "/links": "default", "/links/1": "settings" } }} />);
    expect(Array.from(container.querySelectorAll(".ac-md-source")).map((e) => e.textContent)).toEqual(["출처: default", "출처: settings"]);
  });
});
