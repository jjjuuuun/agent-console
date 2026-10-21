import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRef, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  eventColumns, isErrorEvent, LogEventDetail, LogEventTable, SessionList, sessionColumns, toTaxonomyView,
  type DetailTab, type LogEventDetailHandle, type LogEventTableHandle,
} from "../src";
import { ev, events, slotFor, taxonomy } from "./fixtures";
import type { LogEventDetail as DetailData, LogSessionSummary } from "@agent-console/contracts/logs";

afterEach(cleanup);
const view = toTaxonomyView(taxonomy);
const isError = (r: { category: string; tags?: string[] | undefined }) => isErrorEvent(r, view);

describe("LogEventTable 명령형 API (5R.21)", () => {
  const rows = events(200);
  const base = { rows, columns: eventColumns(["time", "title"]), taxonomy: view, isError, slotFor, height: 160 } as const;

  it("scrollToUid: 화면 밖 행으로 스크롤하고, 없는 uid는 false", () => {
    const ref = createRef<LogEventTableHandle>();
    render(<LogEventTable {...base} ref={ref} />);
    const last = rows[199]!.uid;
    expect(screen.queryByText(String(rows[199]!.title))).toBeNull();
    let ok = false;
    act(() => {
      ok = ref.current!.scrollToUid(last);
    });
    expect(ok).toBe(true);
    let missing = true;
    act(() => {
      missing = ref.current!.scrollToUid("nope");
    });
    expect(missing).toBe(false);
  });

  it("scrollToUid: 접힌 응답 묶음 안의 행이면 묶음을 펼친다", () => {
    const grouped = [
      ev({ uid: "g1", seq: 1, time: 1, thread: "t", message_id: "m", title: "first" }),
      ev({ uid: "g2", seq: 2, time: 2, thread: "t", message_id: "m", title: "second" }),
    ];
    const ref = createRef<LogEventTableHandle>();
    render(<LogEventTable {...base} rows={grouped} groupByMessage ref={ref} />);
    expect(screen.queryByText("second")).toBeNull();
    act(() => {
      expect(ref.current!.scrollToUid("g2")).toBe(true);
    });
    expect(screen.getByText("second")).toBeTruthy();
  });

  it("focus: 표(grid)에 포커스", () => {
    const ref = createRef<LogEventTableHandle>();
    render(<LogEventTable {...base} ref={ref} />);
    act(() => ref.current!.focus());
    expect(document.activeElement).toBe(screen.getByRole("grid"));
  });

  it("onActivate: Enter에서만 호출(이미 선택된 행이어도), 클릭은 호출하지 않는다", () => {
    const onActivate = vi.fn();
    const onSelect = vi.fn();
    render(<LogEventTable {...base} selectedUid={rows[0]!.uid} onSelect={onSelect} onActivate={onActivate} />);
    fireEvent.keyDown(screen.getByRole("grid"), { key: "Enter" });
    expect(onActivate).toHaveBeenCalledWith(rows[0]!.uid);
    fireEvent.click(screen.getByText(String(rows[1]!.title)));
    expect(onActivate).toHaveBeenCalledTimes(1);
  });
});

describe("LogEventDetail 활성 탭 (5R.21)", () => {
  const detail: DetailData = {
    event: ev({ uid: "d1", seq: 1, time: 1, category: "zz-bad", title: "T", detail: { a: 1 }, raw: { r: 1 } }),
    related: [ev({ uid: "r1", seq: 2, time: 2, title: "관련 1" })],
    evidence_links: [{ uid: "r1", basis: "b", value: "v", title: "연결" }],
  };
  const common = { taxonomy: view, slotFor, isError, detail } as const;
  const selectedTab = () => screen.getAllByRole("tab").find((t) => t.getAttribute("aria-selected") === "true")?.getAttribute("data-tab");

  it("activeTab을 주면 제어형이고 클릭은 onActiveTabChange로만 알린다", () => {
    const onChange = vi.fn();
    const { rerender } = render(<LogEventDetail {...common} activeTab="raw" onActiveTabChange={onChange} />);
    expect(selectedTab()).toBe("raw");
    fireEvent.click(screen.getByRole("tab", { name: "상세 JSON" }));
    expect(onChange).toHaveBeenCalledWith("detail");
    rerender(<LogEventDetail {...common} activeTab="related" onActiveTabChange={onChange} />);
    expect(selectedTab()).toBe("related");
  });

  it("보이지 않는 탭 id를 주면 첫 탭", () => {
    render(<LogEventDetail {...common} tabs={["overview", "detail"]} activeTab={"evidence" satisfies DetailTab} />);
    expect(selectedTab()).toBe("overview");
  });

  it("ref: selectTabAt이 탭을 바꾸고 포커스하며, 없는 위치는 false. focusTab은 현재 탭 버튼", () => {
    const ref = createRef<LogEventDetailHandle>();
    render(<LogEventDetail {...common} ref={ref} />);
    expect(ref.current!.visibleTabs()).toEqual(["overview", "detail", "raw", "evidence", "related"]);
    act(() => {
      expect(ref.current!.selectTabAt(2)).toBe(true);
    });
    expect(selectedTab()).toBe("raw");
    expect(document.activeElement?.getAttribute("data-tab")).toBe("raw");
    act(() => {
      expect(ref.current!.selectTabAt(9)).toBe(false);
    });
    (document.activeElement as HTMLElement).blur();
    act(() => {
      expect(ref.current!.focusTab()).toBe(true);
    });
    expect(document.activeElement?.getAttribute("data-tab")).toBe("raw");
  });

  it("비제어에서는 내부 상태로 바뀌고 onActiveTabChange도 불린다", () => {
    const onChange = vi.fn();
    function Host() {
      const [n, setN] = useState(0);
      return (
        <>
          <button onClick={() => setN(n + 1)}>rerender</button>
          <LogEventDetail {...common} onActiveTabChange={onChange} />
        </>
      );
    }
    render(<Host />);
    fireEvent.click(screen.getByRole("tab", { name: "원문 JSON" }));
    expect(selectedTab()).toBe("raw");
    expect(onChange).toHaveBeenCalledWith("raw");
    fireEvent.click(screen.getByText("rerender"));
    expect(selectedTab()).toBe("raw");
  });
});

describe("SessionList onActiveChange (5R.21)", () => {
  const sessions: LogSessionSummary[] = [
    { session: "s-one", events: 1, errors: 0, tokens: null },
    { session: "s-two", events: 2, errors: 0, tokens: null },
  ];
  const columns = sessionColumns(["session", "events"]);

  it("처음엔 첫 행, ↓로 커서가 움직이면 그 세션 id를 알리고 빈 목록은 null", () => {
    const onActive = vi.fn();
    const { rerender } = render(<SessionList sessions={sessions} columns={columns} order="desc" onOpen={() => undefined} onActiveChange={onActive} />);
    expect(onActive).toHaveBeenLastCalledWith("s-one");
    fireEvent.keyDown(screen.getByRole("grid"), { key: "ArrowDown" });
    expect(onActive).toHaveBeenLastCalledWith("s-two");
    rerender(<SessionList sessions={[]} columns={columns} order="desc" onOpen={() => undefined} onActiveChange={onActive} />);
    expect(onActive).toHaveBeenLastCalledWith(null);
  });
});
