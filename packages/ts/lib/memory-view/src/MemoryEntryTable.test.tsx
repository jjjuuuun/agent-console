import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryEntryTable, ROW_HEIGHT_COMPACT, ROW_HEIGHT_TALL, tableColumns, tableRowHeight } from "./MemoryEntryTable";
import { SAMPLE_NOW, makeEntries } from "./testing";

afterEach(cleanup);

describe("tableColumns / tableRowHeight (수용 기준 5·8)", () => {
  it("앞 6열은 어떤 폭에서도 남고 태그 열은 폭 720 이상에서 더해진다", () => {
    for (const w of [300, 556, 558, 720 - 1]) expect(tableColumns(w)).toEqual(["pin", "key", "author", "updated", "size", "version"]);
    for (const w of [720, 976, 1220]) expect(tableColumns(w)).toEqual(["pin", "key", "author", "updated", "size", "version", "tags"]);
  });
  it("행 높이는 검색어나 모든 범위일 때 52", () => {
    expect(tableRowHeight(false)).toBe(ROW_HEIGHT_COMPACT);
    expect(tableRowHeight(true)).toBe(ROW_HEIGHT_TALL);
    expect([ROW_HEIGHT_COMPACT, ROW_HEIGHT_TALL]).toEqual([32, 52]);
  });
});

describe("MemoryEntryTable", () => {
  it.each([[556, 6], [976, 7], [1220, 7]])("폭 %i에서 열 머리 %i개가 모두 보인다", (width, cols) => {
    render(<MemoryEntryTable entries={makeEntries(3)} width={width} now={SAMPLE_NOW} />);
    expect(screen.getAllByRole("columnheader")).toHaveLength(cols);
    for (const name of ["고정됨", "키", "쓴 주체", "수정", "크기", "버전"]) expect(screen.getByRole("columnheader", { name })).toBeTruthy();
  });

  it("10,000행에서도 보이는 행 + 위아래 8행만 그린다 (수용 기준 7)", () => {
    const entries = makeEntries(10_000);
    render(<MemoryEntryTable entries={entries} total={10_000} width={800} now={SAMPLE_NOW} />);
    const rows = screen.getAllByRole("row").filter((r) => r.hasAttribute("data-index"));
    // 대체 높이 480 / 행 32 = 15행 + 아래 overscan 8
    expect(rows.length).toBeGreaterThan(10);
    expect(rows.length).toBeLessThanOrEqual(15 + 16);
    expect(rows.length).toBeLessThan(100);
    const grid = screen.getByRole("grid");
    expect(grid.getAttribute("aria-rowcount")).toBe("10001"); // 머리 1 + 10,000
    expect(rows[0]?.getAttribute("aria-rowindex")).toBe("2");
  });

  it("전체 수를 모르면 aria-rowcount는 -1(다음 쪽이 있을 때), 끝이면 실제 개수", () => {
    const { rerender } = render(<MemoryEntryTable entries={makeEntries(4)} hasMore width={800} now={SAMPLE_NOW} />);
    expect(screen.getByRole("grid").getAttribute("aria-rowcount")).toBe("-1");
    rerender(<MemoryEntryTable entries={makeEntries(4)} width={800} now={SAMPLE_NOW} />);
    expect(screen.getByRole("grid").getAttribute("aria-rowcount")).toBe("5");
  });

  it("끝에서 5행 앞이면 다음 쪽을 요청한다", () => {
    const onLoadMore = vi.fn();
    render(<MemoryEntryTable entries={makeEntries(6)} hasMore onLoadMore={onLoadMore} width={800} now={SAMPLE_NOW} />);
    expect(onLoadMore).toHaveBeenCalled();
    const second = vi.fn();
    cleanup();
    render(<MemoryEntryTable entries={makeEntries(6)} hasMore loading onLoadMore={second} width={800} now={SAMPLE_NOW} />);
    expect(second).not.toHaveBeenCalled();
  });

  it("상태 줄: 최신순 / 검색 결과 / n개 이상", () => {
    const { rerender } = render(<MemoryEntryTable entries={makeEntries(3)} width={800} now={SAMPLE_NOW} />);
    expect(screen.getByRole("status").textContent).toBe("항목 3 · 최신순");
    rerender(<MemoryEntryTable entries={makeEntries(3)} query="x" width={800} now={SAMPLE_NOW} />);
    expect(screen.getByRole("status").textContent).toBe("항목 3 · 검색 결과");
    rerender(<MemoryEntryTable entries={makeEntries(3)} hasMore width={800} now={SAMPLE_NOW} />);
    expect(screen.getByRole("status").textContent).toBe("항목 3개 이상 · 최신순");
    rerender(<MemoryEntryTable entries={makeEntries(3)} total={131} width={800} now={SAMPLE_NOW} />);
    expect(screen.getByRole("status").textContent).toBe("항목 131 · 최신순");
  });

  it("열 머리는 눌러도 아무 일이 없다(정렬 인자 없음), 정렬 키를 주면 단추가 된다 (수용 기준 12)", () => {
    const { rerender } = render(<MemoryEntryTable entries={makeEntries(2)} width={800} now={SAMPLE_NOW} />);
    expect(within(screen.getByRole("columnheader", { name: "키" })).queryByRole("button")).toBeNull();
    const onSortChange = vi.fn();
    rerender(<MemoryEntryTable entries={makeEntries(2)} width={800} now={SAMPLE_NOW} sortKeys={{ key: "key" }} sort={{ key: "key", order: "asc" }} onSortChange={onSortChange} />);
    const th = screen.getByRole("columnheader", { name: "키" });
    expect(th.getAttribute("aria-sort")).toBe("ascending");
    fireEvent.click(within(th).getByRole("button"));
    expect(onSortChange).toHaveBeenCalledWith(null);
    expect(screen.getByRole("status").textContent).toBe("항목 2 · 키 오름차순");
  });

  it("행 상태는 색 외 단서(아이콘·글자·취소선)와 접근 이름을 가진다 (수용 기준 9)", () => {
    const entries = [
      ...makeEntries(1, { pinned: true }),
      ...makeEntries(1, { id: "arc", key: "x/archived", archived: true, pinned: false }),
      ...makeEntries(1, { id: "del", key: "x/deleted", deleted_at: SAMPLE_NOW - 5, pinned: false }),
    ];
    render(<MemoryEntryTable entries={entries} width={800} now={SAMPLE_NOW} />);
    const rows = screen.getAllByRole("row").filter((r) => r.hasAttribute("data-index"));
    expect(rows[0]?.getAttribute("aria-label")).toContain("고정됨");
    expect(within(rows[0] as HTMLElement).getByRole("img", { name: "고정됨" })).toBeTruthy();
    expect(rows[1]?.getAttribute("aria-label")).toContain("보관됨");
    expect(within(rows[1] as HTMLElement).getByText("보관됨")).toBeTruthy();
    expect(rows[2]?.getAttribute("aria-label")).toContain("지움");
    expect(within(rows[2] as HTMLElement).getByText("지움")).toBeTruthy();
    expect(rows[2]?.querySelector("[data-struck]")).toBeTruthy();
  });

  it("행 접근 이름: 키, 쓴 주체, 수정, 크기, 버전", () => {
    render(<MemoryEntryTable entries={makeEntries(1)} width={800} now={SAMPLE_NOW} authorOptions={{ resolveAgent: () => ({ status: "named", name: "리뷰어" }) }} />);
    const row = screen.getAllByRole("row").find((r) => r.hasAttribute("data-index")) as HTMLElement;
    expect(row.getAttribute("aria-label")).toContain("a/b/entry-0, 리뷰어, 방금, 100 B, 버전 1");
  });

  it("행 높이 32/52: 검색어 또는 모든 범위(showScope)일 때 52이고 둘째 줄이 있다 (수용 기준 8)", () => {
    const { rerender } = render(<MemoryEntryTable entries={makeEntries(2)} width={800} now={SAMPLE_NOW} />);
    const first = () => screen.getAllByRole("row").find((r) => r.hasAttribute("data-index")) as HTMLElement;
    expect(first().style.height).toBe("32px");
    expect(first().querySelector(".ac-mem-subline")).toBeNull();
    rerender(<MemoryEntryTable entries={makeEntries(2)} width={800} now={SAMPLE_NOW} query="본문" />);
    expect(first().style.height).toBe("52px");
    expect(first().querySelector(".ac-mem-subline")?.textContent).toContain("본문 앞부분 0");
    rerender(<MemoryEntryTable entries={makeEntries(2)} width={800} now={SAMPLE_NOW} showScope scopeText={(s) => `L:${s.id}`} />);
    expect(first().style.height).toBe("52px");
    expect(first().querySelector(".ac-mem-subline")?.textContent).toBe("L:g1");
  });

  it("태그 열이 없는 폭에서는 키 셀 툴팁에 태그가 들어간다", () => {
    render(<MemoryEntryTable entries={makeEntries(1)} width={556} now={SAMPLE_NOW} />);
    expect(document.querySelector(".ac-mem-td-key")?.getAttribute("title")).toContain("t1, t2, t3");
  });

  it("키보드: roving tabindex, 방향키·Home/End·Enter·Space·Delete·N", () => {
    const onSelect = vi.fn();
    const onOpen = vi.fn();
    const onDelete = vi.fn();
    const onPurge = vi.fn();
    const onNew = vi.fn();
    const entries = makeEntries(5);
    render(<MemoryEntryTable entries={entries} width={800} now={SAMPLE_NOW} onSelect={onSelect} onOpen={onOpen} onDelete={onDelete} onPurge={onPurge} onNew={onNew} />);
    const rows = () => screen.getAllByRole("row").filter((r) => r.hasAttribute("data-index"));
    expect(rows().filter((r) => r.getAttribute("tabindex") === "0")).toHaveLength(1);
    const r0 = rows()[0] as HTMLElement;
    r0.focus();
    fireEvent.keyDown(r0, { key: "ArrowDown" });
    return Promise.resolve().then(() => {
      expect(rows().find((r) => r.getAttribute("tabindex") === "0")?.getAttribute("data-index")).toBe("1");
      const r1 = rows()[1] as HTMLElement;
      fireEvent.keyDown(r1, { key: "End" });
    }).then(() => {
      expect(rows().find((r) => r.getAttribute("tabindex") === "0")?.getAttribute("data-index")).toBe("4");
      const r4 = rows()[4] as HTMLElement;
      fireEvent.keyDown(r4, { key: "Enter" });
      expect(onSelect).toHaveBeenCalledWith(entries[4]);
      expect(onOpen).toHaveBeenCalledWith(entries[4]);
      fireEvent.keyDown(r4, { key: " " });
      expect(onOpen).toHaveBeenCalledTimes(1);
      fireEvent.keyDown(r4, { key: "Delete" });
      expect(onDelete).toHaveBeenCalledWith(entries[4]);
      fireEvent.keyDown(r4, { key: "Delete", shiftKey: true });
      expect(onPurge).toHaveBeenCalledWith(entries[4]);
      fireEvent.keyDown(r4, { key: "n" });
      expect(onNew).toHaveBeenCalledTimes(1);
    });
  });

  it("단일 문자 키는 행 밖(입력 필드 등)에서 온 이벤트로는 동작하지 않는다", () => {
    const onNew = vi.fn();
    render(<div><input aria-label="검색" /><MemoryEntryTable entries={makeEntries(2)} width={800} now={SAMPLE_NOW} onNew={onNew} /></div>);
    fireEvent.keyDown(screen.getByLabelText("검색"), { key: "n" });
    expect(onNew).not.toHaveBeenCalled();
  });

  it("빈 목록은 빈 상태를 보인다", () => {
    render(<MemoryEntryTable entries={[]} width={800} now={SAMPLE_NOW} />);
    expect(screen.getByText("표시할 항목이 없습니다.")).toBeTruthy();
  });

  it("쓴 주체: 에이전트는 아바타 + 이름, 사용자는 칩", () => {
    const entries = [...makeEntries(1), ...makeEntries(1, { id: "u", updated_by: { kind: "user" } })];
    render(<MemoryEntryTable entries={entries} width={800} now={SAMPLE_NOW} />);
    const rows = screen.getAllByRole("row").filter((r) => r.hasAttribute("data-index"));
    expect(rows[0]?.querySelector(".ac-mem-avatar")).toBeTruthy();
    expect(rows[1]?.querySelector(".ac-mem-td-author .ac-mem-chip")?.textContent).toBe("사용자");
  });
});
