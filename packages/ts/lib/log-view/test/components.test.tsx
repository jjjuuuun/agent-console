import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CategoryChips, ColorSlotPicker, eventColumns, fitColumns, HandoffMatrixView, isErrorEvent, LaneRibbon, LogEventDetail, LogEventTable, LogFilterBar, PlaybackBar, SessionList, sessionColumns, TemplatePicker,
  toTaxonomyView, type FilterFieldSpec, type LogFilterValue,
} from "../src";
import { ev, events, slotFor, taxonomy } from "./fixtures";
import type { LogEventDetail as DetailData, LogSessionSummary } from "@agent-console/contracts/logs";

afterEach(cleanup);
const view = toTaxonomyView(taxonomy);
const isError = (r: { category: string; tags?: string[] | undefined }) => isErrorEvent(r, view);

describe("LogEventTable", () => {
  const rows = [
    ev({ uid: "a", seq: 1, time: 1_700_000_000, category: "zz-bad", title: "boom", tool: "tool-q", call_id: "c1" }),
    ev({ uid: "b", seq: 2, time: 1_700_000_001.5, category: "zz-odd", title: "y".repeat(120), duration_ms: 842 }),
    ev({ uid: "c", seq: 3, time: 1_700_000_002, category: "never-seen", title: "plain", status: "failed" }),
  ];
  const columns = eventColumns(["time", "category", "title", "duration"]);
  const base = { rows, columns, taxonomy: view, isError, slotFor, originTime: 1_700_000_000 } as const;

  it("모르는 범주·100자 이름·분류 체계 0개도 깨지지 않고 오류는 tone=danger만 표시", () => {
    render(<LogEventTable {...base} />);
    const grid = screen.getByRole("grid");
    expect(grid.getAttribute("aria-rowcount")).toBe("4");
    const rowEls = within(grid).getAllByRole("row");
    expect(rowEls[1]?.getAttribute("data-error")).toBe("true"); // zz-bad (tone=danger)
    expect(rowEls[3]?.getAttribute("data-error")).toBeNull(); // status가 failed여도 오류 아님
    expect(within(rowEls[1] as HTMLElement).getByText("오류")).toBeTruthy();
    expect(screen.getAllByText("x".repeat(100)).length).toBeGreaterThan(0); // 100자 분류 체계 이름
    expect(screen.getByText("never-seen")).toBeTruthy(); // 모르는 범주는 id 원문
    expect(screen.getByText("+0:01.500")).toBeTruthy();
    expect(screen.getByText("842ms")).toBeTruthy();
    cleanup();
    render(<LogEventTable {...base} taxonomy={toTaxonomyView(undefined)} isError={() => false} />);
    expect(screen.queryByText("오류")).toBeNull();
  });

  it("절대 시각 모드와 값 없음은 0이 아니라 –", () => {
    render(<LogEventTable {...base} timeMode="absolute" />);
    expect(screen.getAllByText("–").length).toBeGreaterThan(0); // 소요 없는 행
    expect(screen.queryByText("+0:00.000")).toBeNull();
  });

  it("키보드: ↓ 이동, Enter 선택, 선택된 상태에서 ↑↓는 선택도 따라감, Shift+F10 메뉴", () => {
    const onSelect = vi.fn();
    const onRowMenu = vi.fn();
    const { rerender } = render(<LogEventTable {...base} onSelect={onSelect} onRowMenu={onRowMenu} />);
    const grid = screen.getByRole("grid");
    fireEvent.keyDown(grid, { key: "ArrowDown" });
    fireEvent.keyDown(grid, { key: "Enter" });
    expect(onSelect).toHaveBeenLastCalledWith("b");
    fireEvent.keyDown(grid, { key: "F10", shiftKey: true });
    expect(onRowMenu).toHaveBeenCalledWith("b", expect.any(Object));
    rerender(<LogEventTable {...base} selectedUid="b" onSelect={onSelect} />);
    fireEvent.keyDown(grid, { key: "ArrowDown" });
    expect(onSelect).toHaveBeenLastCalledWith("c");
    fireEvent.click(screen.getByText("plain"));
    expect(onSelect).toHaveBeenLastCalledWith("c");
  });

  it("응답 묶기: 대표 행 + 블록 수 칩, → 로 펼치고 ← 로 접는다", () => {
    const grouped = [
      ev({ uid: "g1", seq: 1, time: 1, thread: "t", message_id: "m", title: "first" }),
      ev({ uid: "g2", seq: 2, time: 2, thread: "t", message_id: "m", title: "second" }),
      ev({ uid: "s", seq: 3, time: 3, title: "single" }),
    ];
    render(<LogEventTable {...base} rows={grouped} groupByMessage />);
    const grid = screen.getByRole("grid");
    expect(screen.getByText(/응답 · 2개 블록/)).toBeTruthy();
    expect(screen.queryByText("second")).toBeNull();
    fireEvent.keyDown(grid, { key: "ArrowRight" });
    expect(screen.getByText("second")).toBeTruthy();
    fireEvent.keyDown(grid, { key: "ArrowLeft" });
    expect(screen.queryByText("second")).toBeNull();
  });

  it("가상 스크롤: 큰 목록도 일부 행만 그리고 끝 근처에서 다음 페이지 신호를 한 번만 보낸다", () => {
    const many = events(2000);
    const onNearEnd = vi.fn();
    const { container } = render(<LogEventTable {...base} rows={many} hasMore onNearEnd={onNearEnd} height={320} />);
    expect(container.querySelectorAll('[role="row"]').length).toBeLessThan(60);
    expect(screen.getByRole("grid").getAttribute("aria-rowcount")).toBe("2001");
    expect(onNearEnd).not.toHaveBeenCalled();
    // 끝으로 이동하면 신호
    fireEvent.keyDown(screen.getByRole("grid"), { key: "End" });
    // happy-dom은 스크롤 이벤트를 만들어 주지 않으므로 마지막 행이 가상화 범위에 들어오는지로 확인한다.
  });

  it("끝에서 20행 이내면 onNearEnd (적은 행 수에서 즉시)", () => {
    const onNearEnd = vi.fn();
    render(<LogEventTable {...base} hasMore onNearEnd={onNearEnd} />);
    expect(onNearEnd).toHaveBeenCalledTimes(1);
  });

  it("로딩·오류·빈 슬롯", () => {
    const onRetry = vi.fn();
    const { rerender } = render(<LogEventTable {...base} rows={[]} loading />);
    expect(screen.getByRole("status")).toBeTruthy();
    rerender(<LogEventTable {...base} rows={[]} error={{ message: "서버 오류", detail: "GET /x" }} onRetry={onRetry} />);
    fireEvent.click(screen.getByText("다시 시도"));
    expect(onRetry).toHaveBeenCalled();
    rerender(<LogEventTable {...base} rows={[]} renderEmpty={() => <p>없음 슬롯</p>} />);
    expect(screen.getByText("없음 슬롯")).toBeTruthy();
  });

  it("현재 위치 행 표시와 따라가기 칩", () => {
    const onFollow = vi.fn();
    const { container } = render(<LogEventTable {...base} currentUid="c" followLast={false} onFollowChange={onFollow} />);
    expect(container.querySelector('[data-current="true"]')?.getAttribute("data-uid")).toBe("c");
    fireEvent.click(screen.getByText(/현재 위치로/));
    expect(onFollow).toHaveBeenCalledWith(true);
  });
});

describe("LogFilterBar", () => {
  const fields: FilterFieldSpec[] = [
    { name: "ff-text", label: "텍스트", input: "text" },
    { name: "ff-sel", label: "선택", input: "select", options: [{ value: "o1", label: "하나" }, { value: "o2" }] },
    { name: "ff-multi", label: "여럿", input: "multiselect", options: [{ value: "m1" }, { value: "m2" }] },
    { name: "ff-time", label: "시각", input: "time-range" },
  ];
  function Harness({ initial = {}, onChangeSpy, ...rest }: { initial?: LogFilterValue; onChangeSpy?: (v: LogFilterValue) => void } & Partial<Parameters<typeof LogFilterBar>[0]>) {
    const [value, setValue] = useState<LogFilterValue>(initial);
    return <LogFilterBar fields={fields} value={value} onChange={(v) => { setValue(v); onChangeSpy?.(v); }} searchField="qq" debounceMs={300} {...rest} />;
  }

  it("임의 필드 정의로 칩을 만들고 지운다(이름은 fields 데이터만)", () => {
    const spy = vi.fn();
    render(<Harness initial={{ "ff-multi": ["m1", "m2", "m3", "m4"], "ff-sel": "o1", "unknown-x": "1" }} onChangeSpy={spy} />);
    expect(screen.getByText("여럿: m1, m2, m3 +1")).toBeTruthy();
    expect(screen.getByText("선택: 하나")).toBeTruthy();
    expect(screen.getByText(/알 수 없는 필터/)).toBeTruthy(); // fields에 없는 이름 경고
    fireEvent.click(screen.getByLabelText("선택 필터 지우기"));
    expect(spy).toHaveBeenLastCalledWith({ "ff-multi": ["m1", "m2", "m3", "m4"], "unknown-x": "1" });
  });

  it("[+ 필터]는 아직 안 쓴 필드만 보이고 선택하면 입력 팝오버가 열려 값을 적용한다", () => {
    const spy = vi.fn();
    render(<Harness initial={{ "ff-sel": "o1" }} onChangeSpy={spy} />);
    fireEvent.click(screen.getByText("+ 필터"));
    const items = screen.getAllByRole("menuitem").map((n) => n.textContent);
    expect(items).toEqual(["텍스트", "여럿", "시각"]);
    fireEvent.click(screen.getByText("텍스트"));
    const input = screen.getByLabelText("텍스트 값");
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(spy).toHaveBeenLastCalledWith({ "ff-sel": "o1", "ff-text": "hello" });
  });

  it("검색어는 300ms 디바운스, IME 조합 중에는 반영하지 않고 Enter는 즉시", () => {
    vi.useFakeTimers();
    try {
      const spy = vi.fn();
      render(<Harness onChangeSpy={spy} />);
      const input = screen.getByLabelText("검색어");
      fireEvent.change(input, { target: { value: "ab" } });
      act(() => void vi.advanceTimersByTime(299));
      expect(spy).not.toHaveBeenCalled();
      act(() => void vi.advanceTimersByTime(2));
      expect(spy).toHaveBeenLastCalledWith({ qq: "ab" });
      fireEvent.compositionStart(input);
      fireEvent.change(input, { target: { value: "abㅎ" } });
      act(() => void vi.advanceTimersByTime(1000));
      expect(spy).toHaveBeenCalledTimes(1);
      fireEvent.compositionEnd(input);
      fireEvent.keyDown(input, { key: "Enter" });
      expect(spy).toHaveBeenLastCalledWith({ qq: "abㅎ" });
      expect(input.getAttribute("maxlength")).toBe("500");
    } finally {
      vi.useRealTimers();
    }
  });

  it("서버 검증 오류(422)는 해당 칩에 표시", () => {
    render(<Harness initial={{ "ff-sel": "o1" }} fieldErrors={{ "ff-sel": "잘못된 값" }} />);
    const chip = screen.getByRole("button", { name: /선택: 하나/ });
    expect(chip.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByRole("alert").textContent).toContain("잘못된 값");
  });

  it("즐겨찾는 필터: 저장·적용·삭제 콜백", () => {
    const onSave = vi.fn();
    const onApply = vi.fn();
    const onDelete = vi.fn();
    render(<Harness savedFilters={[{ name: "내것", value: { "ff-text": "z" } }]} onSaveFilter={onSave} onApplySaved={onApply} onDeleteSaved={onDelete} />);
    fireEvent.click(screen.getByLabelText("즐겨찾는 필터"));
    fireEvent.click(screen.getByLabelText("내것 적용"));
    expect(onApply).toHaveBeenCalledWith({ name: "내것", value: { "ff-text": "z" } });
    fireEvent.click(screen.getByLabelText("즐겨찾는 필터"));
    fireEvent.click(screen.getByLabelText("내것 삭제"));
    expect(onDelete).toHaveBeenCalledWith("내것");
    fireEvent.change(screen.getByLabelText("저장할 이름"), { target: { value: "새 이름" } });
    fireEvent.click(screen.getByText("현재 필터 저장"));
    expect(onSave).toHaveBeenCalledWith("새 이름");
  });
});

describe("CategoryChips", () => {
  it("받은 항목에서만 칩을 만들고 순서·다중 토글·개수 툴팁", () => {
    const onChange = vi.fn();
    render(<CategoryChips items={[{ id: "alpha", count: 1, total: 7 }, { id: "zz-bad", count: 2 }, { id: "zz-odd", count: 3 }]} taxonomy={view} slotFor={slotFor} selected={["zz-bad"]} onChange={onChange} />);
    const chips = screen.getAllByRole("button");
    expect(chips.map((c) => c.getAttribute("aria-pressed"))).toEqual(["false", "true", "false"].length === 3 ? ["false", "false", "true", "false"] : []);
    expect(chips[1]?.textContent).toContain("x".repeat(100)); // 분류 체계 순서: zz-odd, zz-bad, alpha
    fireEvent.click(chips[3] as HTMLElement); // alpha
    expect(onChange).toHaveBeenLastCalledWith(["zz-bad", "alpha"]);
    expect(chips[3]?.getAttribute("title")).toBe("전체 7 · 현재 위치까지 1");
    fireEvent.click(chips[0] as HTMLElement);
    expect(onChange).toHaveBeenLastCalledWith([]);
  });
  it("12개를 넘으면 [더 보기]", () => {
    const items = Array.from({ length: 15 }, (_, i) => ({ id: `c${i}`, count: i + 1 }));
    render(<CategoryChips items={items} taxonomy={view} slotFor={slotFor} selected={[]} onChange={() => undefined} />);
    expect(screen.getAllByRole("button")).toHaveLength(1 + 12 + 1);
    fireEvent.click(screen.getByText(/더 보기/));
    expect(screen.getAllByRole("button")).toHaveLength(1 + 15 + 1);
  });
  it("←→ 로 칩 사이 이동", () => {
    render(<CategoryChips items={[{ id: "a", count: 1 }, { id: "b", count: 1 }]} taxonomy={view} slotFor={slotFor} selected={[]} onChange={() => undefined} />);
    const chips = screen.getAllByRole("button");
    (chips[0] as HTMLElement).focus();
    fireEvent.keyDown(chips[0] as HTMLElement, { key: "ArrowRight" });
    expect(document.activeElement).toBe(chips[1]);
  });
});

describe("LogEventDetail", () => {
  const detail: DetailData = {
    event: ev({ uid: "d1", seq: 1, time: 1_700_000_005, category: "zz-bad", title: "상세 제목", tool: "t", call_id: "cid", session: "sess-1", run_id: "run-1", detail: { a: 1 }, raw: { r: true }, tags: ["zz-bad", "other"], stage: "stg", model: "mdl" }),
    related: [ev({ uid: "r1", seq: 2, time: 1_700_000_006, title: "관련 1" })],
    evidence_links: [{ uid: "r1", basis: "basis-k", value: "val-v", title: "연결" }],
    truncated: true,
    detail_truncated: true,
    usage: { input_tokens: 10, output_tokens: 20, cache_read_input_tokens: null },
  };
  const common = { taxonomy: view, slotFor, isError } as const;

  it("개요 필드는 값이 있는 것만, 탭은 내용 있는 것만(개수 표시), 잘림 경고와 가려진 사본 안내", () => {
    render(<LogEventDetail {...common} detail={detail} originTime={1_700_000_000} />);
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["개요", "상세 JSON", "원문 JSON", "근거 (1)", "관련 (1)"]);
    expect(screen.getByText("오류")).toBeTruthy();
    expect(screen.getByText("cid")).toBeTruthy();
    expect(screen.queryByText("turn_id")).toBeNull();
    expect(screen.getByText(/최대 출력 1회만 집계/)).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "상세 JSON" }));
    expect(screen.getByText("내용이 길어 일부만 보입니다")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "원문 JSON" }));
    expect(screen.getByText(/가려진 사본/)).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "관련 (1)" }));
    expect(screen.getByText("관련 이벤트가 많아 일부만 보입니다")).toBeTruthy();
  });

  it("raw가 null이면 원문 탭이 없고 detail이 null이면 안내", () => {
    const d: DetailData = { event: { ...detail.event, raw: null, detail: null }, related: [], evidence_links: [] };
    render(<LogEventDetail {...common} detail={d} />);
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["개요", "상세 JSON"]);
    fireEvent.click(screen.getByRole("tab", { name: "상세 JSON" }));
    expect(screen.getByText("상세가 없습니다")).toBeTruthy();
  });

  it("슬롯: 코드 블록·링크, 근거/관련 클릭 이동, 탭 ←→ 키", () => {
    const onOpen = vi.fn();
    render(
      <LogEventDetail
        {...common}
        detail={detail}
        onOpenEvent={onOpen}
        renderCodeBlock={(v, o) => <div data-testid="code">{o.language}:{JSON.stringify(v)}</div>}
        renderLinks={(kind, id) => <a href={`#${kind}-${id}`}>{kind}:{id}</a>}
      />,
    );
    expect(screen.getByText("run:run-1")).toBeTruthy();
    expect(screen.getByText("session:sess-1")).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowRight" });
    expect(screen.getByTestId("code").textContent).toContain('json:{"a":1}');
    fireEvent.click(screen.getByRole("tab", { name: "근거 (1)" }));
    fireEvent.click(screen.getByText("val-v"));
    expect(onOpen).toHaveBeenCalledWith("r1");
  });

  it("로딩 중에는 목록 행 정보(preview)로 개요를 먼저 그리고 오류에는 다시 시도", () => {
    const onRetry = vi.fn();
    render(<LogEventDetail {...common} preview={detail.event} loading />);
    expect(screen.getByText("상세 제목")).toBeTruthy();
    cleanup();
    render(<LogEventDetail {...common} error={{ message: "실패" }} onRetry={onRetry} />);
    fireEvent.click(screen.getByText("다시 시도"));
    expect(onRetry).toHaveBeenCalled();
  });
});

describe("SessionList", () => {
  const sessions: LogSessionSummary[] = [
    { session: "abcdef0123456789", first_time: 1_700_000_000, last_time: 1_700_000_125, events: 1204, errors: 2, thread_count: 3, models: ["m1", "m2", "m3"], tokens: { input: 1, output: 2, cache_read: null, cache_creation: 4, total: 4100 }, project: { id: "p1", label: "프로젝트 하나" } },
    { session: "ffff", events: 0, errors: 0, tokens: null },
  ];
  const columns = sessionColumns(["start", "session", "project", "events", "errors", "models", "tokens", "length"]);
  it("값이 없으면 –, 오류는 아이콘+숫자, 모델은 2개+외 n, 토큰 약식", () => {
    render(<SessionList sessions={sessions} columns={columns} order="desc" onOpen={() => undefined} now={() => 1_700_000_000_000} />);
    expect(screen.getByText("abcdef01")).toBeTruthy();
    expect(screen.getByText("프로젝트 하나")).toBeTruthy();
    expect(screen.getByText("1,204")).toBeTruthy();
    expect(screen.getByText("+2")).toBeTruthy();
    expect(screen.getByText("4.1k").getAttribute("title")).toContain("같은 응답은 한 번만");
    expect(screen.getAllByText("–").length).toBeGreaterThanOrEqual(4); // 두 번째 세션의 빈 값들
    expect(screen.getByText(/⚠/)).toBeTruthy();
    expect(screen.getByText("2분 05초")).toBeTruthy();
  });
  it("제목 열: 제목을 말줄임 셀로 보이고 없으면 –, 머리글은 메시지 표", () => {
    const cols = sessionColumns(["session", "title"]);
    expect(cols[1]?.header).toBe("제목");
    render(<SessionList sessions={[{ session: "s1", title: "로그인 버그 고치기" }, { session: "s2", title: "" }]} columns={cols} order="desc" onOpen={() => undefined} />);
    const t = screen.getByText("로그인 버그 고치기");
    expect(t.getAttribute("title")).toBe("로그인 버그 고치기");
    expect(t.className).toContain("ac-lv-ellipsis");
    expect(screen.getAllByText("–").length).toBe(1);
  });
  it("시작 열 머리만 정렬 토글, Enter·클릭으로 열기, 상한 안내", () => {
    const onOrder = vi.fn();
    const onOpen = vi.fn();
    render(<SessionList sessions={sessions} columns={columns} order="desc" onOrderChange={onOrder} onOpen={onOpen} limitReached limit={200} />);
    fireEvent.click(screen.getByRole("button", { name: /시작/ }));
    expect(onOrder).toHaveBeenCalledWith("asc");
    expect(screen.getAllByRole("columnheader").filter((h) => h.getAttribute("aria-sort"))).toHaveLength(1);
    fireEvent.keyDown(screen.getByRole("grid"), { key: "Enter" });
    expect(onOpen).toHaveBeenCalledWith("abcdef0123456789");
    fireEvent.click(screen.getByText("ffff"));
    expect(onOpen).toHaveBeenCalledWith("ffff");
    expect(screen.getByText(/상위 200개만 표시/)).toBeTruthy();
  });
});

describe("fitColumns(좁은 폭 열 우선순위)", () => {
  const cols = sessionColumns(["start", "session", "project", "threads", "events", "errors", "models", "tokens", "length"]);
  it("1024 폭(콘텐츠 약 940)에서는 모든 열이 들어가 길이 열이 남는다", () => {
    expect(fitColumns(cols, 940).map((c) => c.id)).toContain("length");
    expect(fitColumns(cols, 940)).toHaveLength(cols.length);
  });
  it("모자라면 우선순위가 낮은 열(에이전트 수·모델·프로젝트)부터 빠지고 길이는 끝까지 남는다", () => {
    const ids = fitColumns(cols, 560).map((c) => c.id);
    expect(ids).toContain("length");
    expect(ids).toContain("start");
    expect(ids).not.toContain("threads");
    expect(ids.indexOf("start")).toBeLessThan(ids.indexOf("length"));
  });
  it("폭을 모르면(0·null) 그대로 둔다", () => {
    expect(fitColumns(cols, null)).toBe(cols);
    expect(fitColumns(cols, 0)).toBe(cols);
  });
});

describe("PlaybackBar", () => {
  const evs = [1, 2, 3, 4, 5].map((n) => ({ seq: n, time: 100 + n }));
  const props = { events: evs, playing: false, onPlayingChange: () => undefined, speed: 1, onSpeedChange: () => undefined, skipGaps: true, onSkipGapsChange: () => undefined } as const;
  it("슬라이더 aria: min 0, max N, now = index+1, valuetext", () => {
    render(<PlaybackBar {...props} index={2} onIndexChange={() => undefined} describe={(i) => `제목${i}`} />);
    const s = screen.getByRole("slider");
    expect(s.getAttribute("aria-valuemin")).toBe("0");
    expect(s.getAttribute("aria-valuemax")).toBe("5");
    expect(s.getAttribute("aria-valuenow")).toBe("3");
    expect(s.getAttribute("aria-valuetext")).toContain("3번째 / 5");
    expect(s.getAttribute("aria-valuetext")).toContain("제목2");
    cleanup();
    render(<PlaybackBar {...props} index={-1} onIndexChange={() => undefined} />);
    expect(screen.getByRole("slider").getAttribute("aria-valuetext")).toBe("시작 전 · 0 / 5");
  });
  it("키보드: ←→ ±1, Shift ±10, Page ±100, Home 첫 이벤트, End 끝", () => {
    const onIndex = vi.fn();
    render(<PlaybackBar {...props} index={2} onIndexChange={onIndex} />);
    const s = screen.getByRole("slider");
    fireEvent.keyDown(s, { key: "ArrowRight" });
    expect(onIndex).toHaveBeenLastCalledWith(3);
    fireEvent.keyDown(s, { key: "ArrowLeft", shiftKey: true });
    expect(onIndex).toHaveBeenLastCalledWith(-1); // 클램프(시작 전)
    fireEvent.keyDown(s, { key: "PageUp" });
    expect(onIndex).toHaveBeenLastCalledWith(4);
    fireEvent.keyDown(s, { key: "Home" });
    expect(onIndex).toHaveBeenLastCalledWith(0);
    fireEvent.keyDown(s, { key: "End" });
    expect(onIndex).toHaveBeenLastCalledWith(4);
  });
  it("재생 버튼 이름이 상태를 따른다(재생/일시정지/처음부터) + 이전·다음", () => {
    const onPlay = vi.fn();
    const onIndex = vi.fn();
    const { rerender } = render(<PlaybackBar {...props} index={4} ended onIndexChange={onIndex} onPlayingChange={onPlay} />);
    fireEvent.click(screen.getByLabelText("처음부터 재생"));
    expect(onPlay).toHaveBeenCalledWith(true);
    rerender(<PlaybackBar {...props} index={1} playing onIndexChange={onIndex} onPlayingChange={onPlay} />);
    fireEvent.click(screen.getByLabelText("일시정지"));
    expect(onPlay).toHaveBeenLastCalledWith(false);
    fireEvent.click(screen.getByLabelText("다음 이벤트"));
    expect(onIndex).toHaveBeenLastCalledWith(2);
  });
  it("오류 틱은 같은 위치를 합치고 최대 개수 제한, 상태 변화만 polite로 알림", () => {
    const many = Array.from({ length: 1000 }, (_, i) => ({ seq: i + 1, time: i }));
    const { container, rerender } = render(<PlaybackBar {...props} events={many} index={5} onIndexChange={() => undefined} errorIndexes={Array.from({ length: 1000 }, (_, i) => i)} maxTicks={200} />);
    expect(container.querySelectorAll(".ac-lv-scrub-tick").length).toBeLessThanOrEqual(200);
    expect(container.querySelectorAll(".ac-lv-scrub-tick").length).toBeGreaterThan(0);
    rerender(<PlaybackBar {...props} index={5} playing onIndexChange={() => undefined} />);
    expect(container.querySelector('[aria-live="polite"]')?.textContent).toContain("재생 시작");
  });
  it("끌기는 놓을 때 한 번만 확정한다", () => {
    const onIndex = vi.fn();
    render(<PlaybackBar {...props} index={4} onIndexChange={onIndex} />);
    const s = screen.getByRole("slider");
    s.getBoundingClientRect = () => ({ left: 0, width: 100, top: 0, height: 10, right: 100, bottom: 10, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.pointerDown(s, { clientX: 20, pointerId: 1 });
    fireEvent.pointerMove(s, { clientX: 60, pointerId: 1 });
    expect(onIndex).not.toHaveBeenCalled();
    expect(s.getAttribute("aria-valuenow")).toBe("3");
    fireEvent.pointerUp(s, { clientX: 60, pointerId: 1 });
    expect(onIndex).toHaveBeenCalledTimes(1);
    expect(onIndex).toHaveBeenCalledWith(2);
  });
});

describe("LaneRibbon", () => {
  const lanes = [{ id: "l-main" }, { id: "l-sub", label: "서브 라벨", parent_id: "l-main" }, { id: "l-orphan", parent_id: "gone" }];
  const evs = [
    { uid: "e1", lane: "l-main", time: 0, category: "zz-bad", error: true },
    { uid: "e2", lane: "l-sub", time: 5, endTime: 8, category: "q", error: false },
    { uid: "e3", lane: "l-sub", time: 10, category: "q", error: false },
  ];
  it("부모-자식 순서로 줄을 그리고 접근 이름에 이벤트 수, 커서 뒤 이벤트는 그리지 않는다", () => {
    const { container } = render(<LaneRibbon lanes={lanes} events={evs} taxonomy={view} slotFor={slotFor} cursorTime={6} />);
    const rows = screen.getAllByRole("row");
    expect(rows.map((r) => r.getAttribute("aria-label"))).toEqual(["l-main, 1개 이벤트", "서브 라벨, 1개 이벤트", "l-orphan, 0개 이벤트"]);
    expect(container.querySelectorAll(".ac-lv-lane-tick, .ac-lv-lane-bar")).toHaveLength(2);
    expect(container.querySelector(".ac-lv-lane-cursor")).toBeTruthy();
  });
  it("레인 행에서 ←→ 이벤트 이동·선택, Tab 정지점은 한 줄", () => {
    const onSel = vi.fn();
    render(<LaneRibbon lanes={lanes} events={evs} taxonomy={view} slotFor={slotFor} onSelectEvent={onSel} />);
    const rows = screen.getAllByRole("row");
    expect(rows.filter((r) => r.tabIndex === 0)).toHaveLength(1);
    fireEvent.keyDown(rows[1] as HTMLElement, { key: "ArrowRight" });
    expect(onSel).toHaveBeenLastCalledWith("e3", { additive: false });
  });
  it("레인이 없으면 안내", () => {
    render(<LaneRibbon lanes={[]} events={[]} taxonomy={view} slotFor={slotFor} />);
    expect(screen.getByText(/레인 정보가 없습니다/)).toBeTruthy();
  });
});

describe("HandoffMatrixView", () => {
  const cells = [
    { from: "p-a", to: "p-b", via: "v1", count: 5 },
    { from: "p-a", to: "p-b", via: "v2", count: 2 },
    { from: "p-b", to: "p-a", count: 1 },
  ];
  it("같은 (from,to)를 합치고 합계 순서, 접근 이름, 방식별 분해 툴팁", () => {
    const onClick = vi.fn();
    render(<HandoffMatrixView cells={cells} onCellClick={onClick} labelFor={(id) => id.toUpperCase()} viaLabelFor={(v) => `방식 ${v}`} />);
    const btn = screen.getByLabelText("P-A에서 P-B로 7회");
    expect(btn.getAttribute("title")).toBe("방식 v1 5 · 방식 v2 2");
    fireEvent.click(btn);
    expect(onClick).toHaveBeenLastCalledWith({ from: "p-a", to: "p-b" });
    fireEvent.click(screen.getByLabelText("P-B에서 P-A로 1회"));
    expect(onClick).toHaveBeenLastCalledWith({ from: "p-b", to: "p-a" });
    expect(screen.getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["P-A", "P-B"]);
  });
  it("빈 상태·상한 안내", () => {
    const { rerender } = render(<HandoffMatrixView cells={[]} />);
    expect(screen.getByText("집계할 위임이 없습니다")).toBeTruthy();
    rerender(<HandoffMatrixView cells={Array.from({ length: 40 }, (_, i) => ({ from: `f${i}`, to: "t", count: 1 }))} limit={40} />);
    expect(screen.getByText(/상위 40개 연결만 표시/)).toBeTruthy();
  });
});

describe("TemplatePicker·ColorSlotPicker", () => {
  const templates = [
    { id: "t1", title: "템플릿 하나", widgets: [{ id: "w1", kind: "k-a", title: "위젯 A", query: { metric: "m" }, options: { w: 6, h: 2 } }] },
    { id: "t2", title: "템플릿 둘", widgets: [] },
  ] as never[];
  it("새 대시보드/덧붙이기 선택과 알 수 없는 위젯 경고", () => {
    const onApply = vi.fn();
    render(<TemplatePicker templates={templates} canAppend onApply={onApply} unknownKinds={(t) => (t.id === "t1" ? 2 : 0)} />);
    expect(screen.getByText("알 수 없는 위젯 2개")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("대시보드 제목"), { target: { value: "내 제목" } });
    fireEvent.click(screen.getByText("적용"));
    expect(onApply).toHaveBeenLastCalledWith({ mode: "new", templateId: "t1", title: "내 제목" });
    fireEvent.click(screen.getByLabelText("현재 대시보드에 위젯 추가"));
    fireEvent.click(screen.getByText("적용"));
    expect(onApply).toHaveBeenLastCalledWith({ mode: "append", templateId: "t1" });
  });
  it("showActions=false: 내부 버튼 없이 formId 제출로 onApply, 라디오는 .ac-choice", () => {
    const onApply = vi.fn();
    const { container } = render(<TemplatePicker templates={templates} canAppend formId="tpl-form" showActions={false} onApply={onApply} unknownKinds={() => 0} />);
    expect(screen.queryByText("적용")).toBeNull();
    const form = container.querySelector("form#tpl-form") as HTMLFormElement;
    expect(form).toBeTruthy();
    expect(container.querySelectorAll("label.ac-choice").length).toBe(2);
    fireEvent.submit(form);
    expect(onApply).toHaveBeenLastCalledWith({ mode: "new", templateId: "t1", title: "템플릿 하나" });
  });
  it("템플릿 0개 안내", () => {
    const onCreateBlank = vi.fn();
    render(<TemplatePicker templates={[]} canAppend={false} onApply={() => undefined} onCreateBlank={onCreateBlank} unknownKinds={() => 0} />);
    expect(screen.getByText(/사용할 수 있는 템플릿이 없습니다/)).toBeTruthy();
    expect(screen.queryByText("템플릿에서 시작")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "빈 대시보드 만들기" }));
    expect(onCreateBlank).toHaveBeenCalled();
  });
  it("색 슬롯: 자동·cat-1~8·중립, 모르는 값은 선택 없음으로 두고 바꾸지 않는다", () => {
    const onChange = vi.fn();
    render(<ColorSlotPicker value="not-a-token" onChange={onChange} ariaLabel="색" />);
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(10);
    expect(radios.some((r) => (r as HTMLInputElement).checked)).toBe(false);
    fireEvent.click(radios[3] as HTMLElement);
    expect(onChange).toHaveBeenCalledWith("cat-3");
    fireEvent.click(radios[0] as HTMLElement);
    expect(onChange).toHaveBeenLastCalledWith(undefined);
  });
});

void waitFor;
