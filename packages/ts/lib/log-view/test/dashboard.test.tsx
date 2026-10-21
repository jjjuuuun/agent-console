import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LogWidget } from "@agent-console/contracts/logs";
import { builtinWidgets, createWidgetRegistry, DashboardGrid, validateWidget, WidgetEditor, defaultLogViewMessages, type WidgetDescriptor, type WidgetResult } from "../src";
import { slotFor, widget } from "./fixtures";

afterEach(cleanup);

/** 테스트 전용 위젯 종류: 레지스트리에 한 줄 더하면 격자가 그린다(코드 수정 없음). */
const probe: WidgetDescriptor = {
  kind: "probe-kind",
  title: "프로브",
  queryShape: { groupBy: { min: 0, max: 3 } },
  optionsSchema: { type: "object" },
  defaultSize: { w: 4, h: 2 },
  render: (p) => <div data-testid="probe">{`${p.rows.length}행/${p.title}/${p.size.w}x${p.size.h}`}</div>,
};
const registry = createWidgetRegistry(builtinWidgets, [probe]);
const rows = (...vals: (number | null)[]): { keys: Record<string, string | null>; value: number | null }[] => vals.map((v, i) => ({ keys: { "dim-a": `k${i}` }, value: v }));
const ok = (r: { keys?: Record<string, string | null>; value?: number | null }[]): WidgetResult => ({ rows: r, loading: false });

describe("DashboardGrid", () => {
  it("레지스트리에 더한 새 위젯 종류를 코드 수정 없이 그린다 + 모르는 종류는 자리 표시", () => {
    const widgets = [widget("w1", "probe-kind"), widget("w2", "kind-nobody-knows", { options: { w: 3, h: 2, keep: 1 } })];
    render(<DashboardGrid widgets={widgets} registry={registry} results={{ w1: ok(rows(1, 2)) }} slotFor={slotFor} />);
    expect(screen.getByTestId("probe").textContent).toContain("2행/프로브 · m-a/4x2");
    expect(screen.getByText("알 수 없는 위젯 (kind-nobody-knows)")).toBeTruthy();
    expect(screen.getByText(/설정은 그대로 보존됩니다/)).toBeTruthy();
    fireEvent.click(screen.getByText("질의·옵션 JSON 보기"));
    expect(screen.getByText(/"keep": 1/)).toBeTruthy();
  });

  it("레지스트리 목록에 switch가 없다: 덮어쓰기(뒤 목록 우선)로 내장 종류도 바꿀 수 있다", () => {
    const mine: WidgetDescriptor = { ...probe, kind: "metric", render: () => <span>덮어씀</span> };
    const reg = createWidgetRegistry(builtinWidgets, [mine]);
    render(<DashboardGrid widgets={[widget("w", "metric", { query: { metric: "m", group_by: [] } })]} registry={reg} results={{ w: ok([{ keys: {}, value: 1 }]) }} slotFor={slotFor} />);
    expect(screen.getByText("덮어씀")).toBeTruthy();
  });

  it("위젯별 상태: 로딩·오류(422)·빈·값 없음", () => {
    const widgets = [widget("l", "probe-kind"), widget("e", "probe-kind"), widget("v", "probe-kind"), widget("m", "metric", { query: { metric: "m-a", group_by: [] } })];
    const onRefresh = vi.fn();
    render(
      <DashboardGrid
        widgets={widgets}
        registry={registry}
        onRefreshWidget={onRefresh}
        slotFor={slotFor}
        results={{
          l: { loading: true },
          e: { loading: false, error: { message: "필드 이상", code: "validation_failed" } },
          v: { loading: false, rows: [] },
          m: ok([{ keys: {}, value: null }]),
        }}
      />,
    );
    expect(screen.getByRole("status", { name: "불러오는 중…" })).toBeTruthy();
    expect(screen.getByText("위젯 설정이 올바르지 않습니다: 필드 이상")).toBeTruthy();
    expect(screen.getByText("조건에 맞는 데이터가 없습니다")).toBeTruthy();
    // 지표 null -> 0이 아니라 "–" + 값 없음
    const metricCard = screen.getByRole("region", { name: /지표 · m-a/ });
    expect(within(metricCard).getByText("–")).toBeTruthy();
    expect(within(metricCard).getByText(/값 없음/)).toBeTruthy();
    fireEvent.click(screen.getAllByText("다시 시도")[0] as HTMLElement);
    expect(onRefresh).toHaveBeenCalledWith("e");
  });

  it("막대: 합계 내림차순·limit·null 행은 막대 없이 –, 표로 보기 토글", () => {
    const w = widget("b", "bar", { options: { limit: 2 } });
    render(<DashboardGrid widgets={[w]} registry={registry} results={{ b: ok(rows(5, null, 9, 1)) }} slotFor={slotFor} />);
    const items = screen.getAllByRole("listitem").map((i) => i.textContent);
    expect(items[0]).toContain("k2");
    expect(items[1]).toContain("k0");
    expect(items).toHaveLength(2);
    expect(screen.getByText("외 2개 항목은 표시하지 않았습니다")).toBeTruthy();
    fireEvent.click(screen.getByText("표로 보기"));
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getAllByText("–").length).toBe(1); // 표에서 null 행
    expect(screen.getByText("차트로 보기")).toBeTruthy();
  });

  it("표 위젯: 값 열 머리 클릭으로 정렬, 표로 보기 토글은 없다", () => {
    render(<DashboardGrid widgets={[widget("t", "table")]} registry={registry} results={{ t: ok(rows(3, 10, 1)) }} slotFor={slotFor} />);
    expect(screen.queryByText("표로 보기")).toBeNull();
    const firstCells = () => within(screen.getByRole("table")).getAllByRole("row").slice(1).map((r) => r.textContent);
    fireEvent.click(screen.getByRole("button", { name: "m-a" })); // desc 먼저
    expect(firstCells()[0]).toContain("k1");
    fireEvent.click(screen.getByRole("button", { name: "m-a" }));
    expect(firstCells()[0]).toContain("k2");
  });

  it("선: recharts를 지연 로드해 그리고(스켈레톤 후 SVG), 계열이 2차원이면 범례에 텍스트", async () => {
    await import("../src/charts/RechartsLine"); // 큰 모듈의 첫 변환 시간을 waitFor 밖에서 치른다
    const w = widget("ln", "line", { query: { group_by: ["dim-t", "dim-s"], metric: "m" } });
    const data = [
      { keys: { "dim-t": "d1", "dim-s": "s1" }, value: 1 },
      { keys: { "dim-t": "d2", "dim-s": "s1" }, value: null },
      { keys: { "dim-t": "d1", "dim-s": "s2" }, value: 3 },
    ];
    render(<DashboardGrid widgets={[w]} registry={registry} results={{ ln: ok(data as never) }} slotFor={slotFor} />);
    await waitFor(() => expect(document.querySelector("svg.recharts-surface")).toBeTruthy(), { timeout: 20000 });
    expect(screen.getByLabelText("dim-s").textContent).toContain("s1");
    expect(screen.getByLabelText("dim-s").textContent).toContain("s2");
  }, 120000);

  it("키보드(편집): Ctrl+↓ 순서, Shift+→ 너비, Delete 삭제, Ctrl+D 복제, Enter 편집 — 알 수 없는 키 보존", () => {
    const onChange = vi.fn();
    const onEdit = vi.fn();
    const odd = widget("w1", "probe-kind", { options: { w: 4, h: 2, secret: { x: 1 } } });
    const widgets: LogWidget[] = [odd, widget("w2", "probe-kind"), widget("w3", "probe-kind")];
    render(<DashboardGrid widgets={widgets} registry={registry} editing results={{}} onChange={onChange} onEditWidget={onEdit} newId={() => "dup"} slotFor={slotFor} />);
    const cards = () => document.querySelectorAll<HTMLElement>("section.ac-lv-card");
    const first = cards()[0] as HTMLElement;
    fireEvent.keyDown(first, { key: "ArrowDown", ctrlKey: true });
    let [next, meta] = onChange.mock.calls.at(-1) as [LogWidget[], { reason: string }];
    expect(next.map((w) => w.id)).toEqual(["w2", "w1", "w3"]);
    expect(meta.reason).toBe("move");
    expect(next[1]).toBe(odd); // 같은 객체
    fireEvent.keyDown(first, { key: "ArrowRight", shiftKey: true });
    [next, meta] = onChange.mock.calls.at(-1) as [LogWidget[], { reason: string }];
    expect(meta.reason).toBe("resize");
    expect(next[0]?.options).toEqual({ w: 5, h: 2, secret: { x: 1 } });
    fireEvent.keyDown(first, { key: "ArrowUp", shiftKey: true });
    expect((onChange.mock.calls.at(-1) as [LogWidget[]])[0][0]?.options).toMatchObject({ h: 2 }); // 최소 2행
    fireEvent.keyDown(first, { key: "Delete" });
    [next, meta] = onChange.mock.calls.at(-1) as [LogWidget[], { reason: string }];
    expect(next.map((w) => w.id)).toEqual(["w2", "w3"]);
    expect(meta.reason).toBe("remove");
    fireEvent.keyDown(first, { key: "d", ctrlKey: true });
    [next, meta] = onChange.mock.calls.at(-1) as [LogWidget[], { reason: string }];
    expect(next.map((w) => w.id)).toEqual(["w1", "dup", "w2", "w3"]);
    expect(meta.reason).toBe("duplicate");
    fireEvent.keyDown(first, { key: "Enter" });
    expect(onEdit).toHaveBeenCalledWith("w1");
  });

  it("편집 모드가 아니면 Ctrl+↓ 같은 변경 키는 무시하고 화살표는 포커스 이동", () => {
    const onChange = vi.fn();
    render(<DashboardGrid widgets={[widget("a", "probe-kind"), widget("b", "probe-kind")]} registry={registry} results={{}} onChange={onChange} slotFor={slotFor} />);
    const cards = document.querySelectorAll<HTMLElement>("section.ac-lv-card");
    fireEvent.keyDown(cards[0] as HTMLElement, { key: "ArrowDown", ctrlKey: true });
    expect(onChange).not.toHaveBeenCalled();
    cards[0]?.focus();
    fireEvent.keyDown(cards[0] as HTMLElement, { key: "ArrowRight" });
    expect(document.activeElement).toBe(cards[1]);
  });

  it("드래그로 순서 변경(손잡이를 다른 카드에 놓기)", () => {
    const onChange = vi.fn();
    render(<DashboardGrid widgets={[widget("a", "probe-kind"), widget("b", "probe-kind"), widget("c", "probe-kind")]} registry={registry} editing results={{}} onChange={onChange} slotFor={slotFor} />);
    const cards = document.querySelectorAll<HTMLElement>("section.ac-lv-card");
    const handle = cards[0]?.querySelector(".ac-lv-handle") as HTMLElement;
    const store: Record<string, string> = {};
    const dt = { setData: (k: string, v: string) => (store[k] = v), getData: (k: string) => store[k] ?? "", effectAllowed: "" };
    fireEvent.dragStart(handle, { dataTransfer: dt });
    fireEvent.dragOver(cards[2] as HTMLElement, { dataTransfer: dt });
    fireEvent.drop(cards[2] as HTMLElement, { dataTransfer: dt });
    const [next] = onChange.mock.calls.at(-1) as [LogWidget[]];
    expect(next.map((w) => w.id)).toEqual(["b", "c", "a"]);
  });

  it("처음 보일 때(IntersectionObserver가 알릴 때) 한 번만 onVisible, 알 수 없는 종류는 요청을 보내지 않으므로 알리지 않는다", () => {
    const observers: { cb: (e: { isIntersecting: boolean }[]) => void }[] = [];
    class FakeIO {
      cb: (e: { isIntersecting: boolean }[]) => void;
      constructor(cb: (e: { isIntersecting: boolean }[]) => void) {
        this.cb = cb;
        observers.push(this);
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    vi.stubGlobal("IntersectionObserver", FakeIO);
    try {
      const onVisible = vi.fn();
      const props = { registry, results: {}, onVisible, slotFor } as const;
      const { rerender } = render(<DashboardGrid widgets={[widget("a", "probe-kind"), widget("x", "unknown-zzz")]} {...props} />);
      expect(observers).toHaveLength(1); // 알 수 없는 종류는 관찰하지 않는다
      expect(onVisible).not.toHaveBeenCalled(); // 화면에 들어오기 전에는 요청 신호 없음
      act(() => observers[0]?.cb([{ isIntersecting: false }]));
      expect(onVisible).not.toHaveBeenCalled();
      act(() => observers[0]?.cb([{ isIntersecting: true }]));
      expect(onVisible).toHaveBeenCalledTimes(1);
      expect(onVisible).toHaveBeenCalledWith("a");
      rerender(<DashboardGrid widgets={[widget("a", "probe-kind")]} {...props} onVisible={vi.fn()} />);
      expect(onVisible).toHaveBeenCalledTimes(1);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("IntersectionObserver가 없는 환경에서는 바로 알린다", () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    try {
      const onVisible = vi.fn();
      render(<DashboardGrid widgets={[widget("a", "probe-kind")]} registry={registry} results={{}} onVisible={onVisible} slotFor={slotFor} />);
      expect(onVisible).toHaveBeenCalledWith("a");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("6열이면 너비가 줄어 한 줄에 더 놓이고 12열 기준 크기 값은 바뀌지 않는다", () => {
    render(<DashboardGrid widgets={[widget("a", "probe-kind", { options: { w: 12, h: 2 } }), widget("b", "probe-kind", { options: { w: 6, h: 2 } })]} registry={registry} columns={6} results={{}} slotFor={slotFor} />);
    const cards = document.querySelectorAll<HTMLElement>("section.ac-lv-card");
    expect(cards[0]?.style.gridColumn).toBe("1 / span 6");
    expect(cards[1]?.style.gridColumn).toBe("1 / span 3");
    expect(cards[1]?.style.gridRow).toBe("3 / span 2");
  });

  it("갱신 시각 표시와 [+ 위젯 추가] 카드 슬롯", () => {
    render(<DashboardGrid widgets={[widget("a", "probe-kind")]} registry={registry} results={{ a: { loading: false, rows: rows(1), updatedAt: 1000 } }} now={() => 13000} addCard={<button type="button">추가</button>} slotFor={slotFor} />);
    expect(screen.getByText("12초 전")).toBeTruthy();
    expect(screen.getByText("추가")).toBeTruthy();
  });
});

describe("WidgetEditor", () => {
  const descriptors = [...builtinWidgets, probe];
  it("서버 목록이 없으면 자유 입력 콤보로 폴백하고 시간 차원 검증은 건너뛴다", () => {
    const onApply = vi.fn();
    const onChange = vi.fn();
    const w = widget("n", "line", { query: { group_by: ["whatever"], metric: "any-name" } });
    render(<WidgetEditor value={w} onChange={onChange} descriptors={descriptors} onApply={onApply} onCancel={() => undefined} />);
    expect(screen.getByText(/서버 검증에 맡깁니다/)).toBeTruthy();
    expect(screen.queryByText("첫 번째 차원은 시간 차원이어야 합니다")).toBeNull();
    fireEvent.change(screen.getByLabelText("+ 차원 추가"), { target: { value: "another" } });
    fireEvent.submit(screen.getByLabelText("+ 차원 추가").closest("form") as HTMLElement);
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ query: expect.objectContaining({ group_by: ["whatever", "another"] }) }));
    fireEvent.click(screen.getByText("위젯 적용"));
    expect(onApply).toHaveBeenCalledWith(w);
  });

  it("서버 목록이 있으면 선택지로 고르고, 시간 차원이 첫째가 아니면 적용 불가", () => {
    const dims = [{ id: "dd-time", kind: "time" }, { id: "dd-other", title: "다른" }];
    const w = widget("n", "line", { query: { group_by: ["dd-other"], metric: "mm" } });
    const { rerender } = render(<WidgetEditor value={w} onChange={() => undefined} descriptors={descriptors} dimensions={dims} metrics={[{ id: "mm", title: "지표 제목", unit: "u" }]} onApply={() => undefined} onCancel={() => undefined} />);
    expect(screen.getByText("첫 번째 차원은 시간 차원이어야 합니다")).toBeTruthy();
    expect((screen.getByText("위젯 적용") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("option", { name: "지표 제목 (u)" })).toBeTruthy();
    rerender(<WidgetEditor value={{ ...w, query: { ...w.query, group_by: ["dd-time"] } }} onChange={() => undefined} descriptors={descriptors} dimensions={dims} metrics={[{ id: "mm" }]} onApply={() => undefined} onCancel={() => undefined} />);
    expect((screen.getByText("위젯 적용") as HTMLButtonElement).disabled).toBe(false);
  });

  it("종류 목록은 레지스트리에서, 차원 개수는 queryShape로 검증(종류 id 비교 없음)", () => {
    const m = defaultLogViewMessages;
    const bad = widget("n", "probe-kind", { query: { group_by: ["a", "b", "c", "d"], metric: "m" } });
    expect(validateWidget(bad, probe, undefined, m)).toEqual(["묶는 기준은 0~3개여야 합니다"]);
    expect(validateWidget(bad, undefined, undefined, m)).toContain("종류를 고르세요");
    const onChange = vi.fn();
    render(<WidgetEditor value={widget("n", "metric", { query: { group_by: [], metric: "m" } })} onChange={onChange} descriptors={descriptors} onApply={() => undefined} onCancel={() => undefined} />);
    expect(screen.getAllByRole("radio")).toHaveLength(descriptors.length);
    fireEvent.click(screen.getByLabelText(/프로브/));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ kind: "probe-kind" }));
  });

  it("옵션 폼·필터·미리보기는 슬롯, 없으면 영역 숨김", () => {
    const { rerender } = render(<WidgetEditor value={widget("n", "bar")} onChange={() => undefined} descriptors={descriptors} onApply={() => undefined} onCancel={() => undefined} />);
    expect(screen.queryByText("표시 옵션")).toBeNull();
    rerender(<WidgetEditor value={widget("n", "bar")} onChange={() => undefined} descriptors={descriptors} renderOptionsForm={(schema) => <p>폼 {Object.keys((schema as { properties: object }).properties).join(",")}</p>} filterBar={<p>필터슬롯</p>} preview={<p>미리보기슬롯</p>} onApply={() => undefined} onCancel={() => undefined} />);
    expect(screen.getByText("폼 limit")).toBeTruthy();
    expect(screen.getByText("필터슬롯")).toBeTruthy();
    expect(screen.getByText("미리보기슬롯")).toBeTruthy();
  });
});

void act;
