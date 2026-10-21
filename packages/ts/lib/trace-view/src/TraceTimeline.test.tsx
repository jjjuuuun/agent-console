import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { Trace, TraceSpan } from "@agent-console/contracts";
import { afterEach, describe, expect, it, vi } from "vitest";
import { compactCount, computeTimeScale, formatTailDuration, flattenRows, isSameSession, niceTicks, visibleHandoffs } from "./layout";
import { TraceTimeline } from "./TraceTimeline";

afterEach(cleanup);

const span = (id: string, over: Partial<TraceSpan> = {}): TraceSpan => ({ id, kind: "whatever", started_at: 0, ended_at: 10, status: "succeeded", ...over });

const trace: Trace = {
  run_id: "r",
  spans: [
    span("pl", { node_id: "pl", started_at: 0, ended_at: 42, session_id: "s1" }),
    span("be", { parent_id: "pl", node_id: "be", started_at: 2, ended_at: 20, session_id: "s1", task_preview: "API 설계" }),
    span("wait", { parent_id: "pl", kind: "interaction", interaction_id: "ix", started_at: 20, ended_at: 32, status: "answered" }),
    span("qa", { node_id: "qa", started_at: 42, ended_at: 72, session_id: "s2", order: 2 }),
  ],
  links: [{ source: "pl", target: "qa", edge_id: "e1" }, { source: "pl", target: "be" }],
};

describe("layout", () => {
  it("부모-자식은 명시 id로만 잇고, 모르는 부모·순환은 최상위/무시", () => {
    const rows = flattenRows([span("a"), span("b", { parent_id: "a" }), span("c", { parent_id: "ghost", started_at: 1 })]);
    expect(rows.map((r) => [r.span.id, r.depth])).toEqual([["a", 0], ["b", 1], ["c", 0]]);
    expect(() => flattenRows([span("x", { parent_id: "y" }), span("y", { parent_id: "x" })])).not.toThrow();
  });
  it("시간 순서가 비슷해도 parent_id 없으면 자식으로 추정하지 않는다", () => {
    const rows = flattenRows([span("a", { started_at: 0, ended_at: 10 }), span("b", { started_at: 1, ended_at: 2 })]);
    expect(rows.every((r) => r.depth === 0)).toBe(true);
  });
  it("접힘과 사용자 대기 제외", () => {
    const spans = trace.spans!;
    expect(flattenRows(spans, { collapsed: new Set(["pl"]) }).map((r) => r.span.id)).toEqual(["pl", "qa"]);
    expect(flattenRows(spans, { showUserWait: false }).map((r) => r.span.id)).not.toContain("wait");
  });
  it("사용자 대기를 접으면 시간 축이 줄어든다", () => {
    const full = computeTimeScale(trace.spans!, { showUserWait: true });
    const compact = computeTimeScale(trace.spans!, { showUserWait: false });
    expect(full.total).toBe(72);
    expect(compact.total).toBe(60);
    expect(compact.at(32)).toBeCloseTo(20 / 60);
  });
  it("실행 중 막대는 now까지", () => {
    const sc = computeTimeScale([span("a", { ended_at: null })], { now: 30, running: true });
    expect(sc.total).toBe(30);
  });
  it("세션 판정은 session_id, 없으면 부모 유무", () => {
    expect(isSameSession(span("c", { session_id: "s1" }), span("p", { session_id: "s1" }))).toBe(true);
    expect(isSameSession(span("c", { session_id: "s2" }), span("p", { session_id: "s1" }))).toBe(false);
    expect(isSameSession(span("c"), span("p"))).toBe(true);
    expect(isSameSession(span("c"), undefined)).toBe(false);
  });
  it("넘기기 화살표는 자식 링크를 제외", () => {
    const rows = flattenRows(trace.spans!);
    const h = visibleHandoffs(trace, rows);
    expect(h.map((x) => x.link.target)).toEqual(["qa"]);
    expect(h[0]?.order).toBe(2);
  });
  it("niceTicks는 5~8칸 안팎", () => {
    const t = niceTicks(72);
    expect(t.length).toBeGreaterThanOrEqual(5);
    expect(t.length).toBeLessThanOrEqual(9);
    expect(niceTicks(0)).toEqual([0]);
  });
});

describe("수치 열 표기", () => {
  const u = { s: "초", m: "분", h: "시간" };
  it("소요는 최대 8자, 100분 이상은 99분+", () => {
    expect(formatTailDuration(0, u)).toBe("0초");
    expect(formatTailDuration(59 * 60 + 59, u)).toBe("59분 59초");
    expect(formatTailDuration(99 * 60 + 59, u)).toBe("99분 59초");
    expect(formatTailDuration(6000, u)).toBe("99분+");
  });
  it("토큰은 k·M으로 줄인다", () => {
    expect([999, 1234, 34000, 1_200_000].map(compactCount)).toEqual(["999", "1.2k", "34k", "1.2M"]);
  });
});

describe("TraceTimeline", () => {
  const labelFor = (s: TraceSpan) => ({ title: `이름-${s.id}`, sub: s.actor ?? undefined });
  const methodBadgeFor = (s: TraceSpan) => (s.parent_id ? { text: "임의 위임 방식" } : s.order ? { text: "임의 넘기기" } : undefined);

  it("빈 trace 안내", () => {
    render(<TraceTimeline trace={{ run_id: "r", spans: [] }} />);
    expect(screen.getByRole("status").textContent).toContain("위임 흐름이 없습니다");
  });
  it("트리 구조·들여 쓰기·방식/세션 배지·접근성 이름", () => {
    render(<TraceTimeline trace={trace} labelFor={labelFor} methodBadgeFor={methodBadgeFor} />);
    expect(screen.getByRole("tree", { name: "위임 흐름" })).toBeTruthy();
    const be = screen.getByRole("treeitem", { name: "이름-be, 임의 위임 방식 같은 세션, 완료, 18초" });
    expect(be.getAttribute("aria-level")).toBe("2");
    const qa = screen.getByRole("treeitem", { name: /이름-qa, 임의 넘기기 별도 세션, 완료, 30초/ });
    expect(qa.getAttribute("aria-level")).toBe("1");
    expect(qa.getAttribute("data-session")).toBe("separate");
    expect(be.querySelector('[data-session-badge="same"]')?.getAttribute("aria-label")).toBe("같은 세션");
    expect(be.textContent).not.toContain("같은 세션"); // 글자 칩은 쓰지 않는다(아이콘 + 툴팁)
    expect(be.querySelector('[data-trace-method]')?.getAttribute("aria-label")).toBe("임의 위임 방식");
  });
  it("사용자 대기 행: waiting 막대, 모르는 kind는 일반 행", () => {
    render(<TraceTimeline trace={trace} labelFor={labelFor} />);
    const wait = document.querySelector('[data-span-id="wait"] .ac-trace-bar');
    expect(wait?.getAttribute("data-status")).toBe("waiting");
    expect(wait?.className).toContain("ac-trace-wait");
    expect(screen.getByRole("treeitem", { name: /사용자 대기 12초/ })).toBeTruthy();
    expect(document.querySelector('[data-span-id="pl"] .ac-trace-bar')?.className).not.toContain("ac-trace-wait");
  });
  it("기본 배율에서는 패널 폭을 넘기지 않고, 수치는 오른쪽 고정 열(막대 위치와 무관)에 둔다", () => {
    render(<TraceTimeline trace={trace} labelFor={labelFor} />);
    const tree = screen.getByRole("tree") as HTMLElement;
    expect(tree.style.minWidth).toBe("100%");
    const row = document.querySelector('[data-span-id="qa"]') as HTMLElement;
    const tail = row.querySelector("[data-trace-tail]") as HTMLElement;
    expect(tail.parentElement).toBe(row); // 행 grid의 세 번째 칸
    expect(tail.querySelector("[data-trace-dur]")?.textContent).toBe("30초");
    expect(row.querySelector("[data-trace-barcell]")?.contains(tail)).toBe(false);
  });
  it("번호 원은 라벨 칸 슬롯에 있고 막대 칸에는 막대·화살표·칩만 있다", () => {
    render(<TraceTimeline trace={trace} labelFor={labelFor} />);
    const row = document.querySelector('[data-span-id="qa"]') as HTMLElement;
    expect(row.querySelector("[data-trace-labelcell] [data-trace-order]")?.textContent).toBe("2");
    expect(row.querySelector("[data-trace-barcell] [data-trace-order]")).toBeNull();
    expect(row.querySelector("[data-trace-barcell] [data-trace-bar]")).toBeTruthy();
  });
  it("방식 글자 표시 토글은 부제를 방식 문구로 바꾼다", () => {
    const onToggle = vi.fn();
    const { rerender } = render(<TraceTimeline trace={trace} labelFor={(s) => ({ title: s.id, sub: "부제" })} methodBadgeFor={methodBadgeFor} onShowMethodTextChange={onToggle} />);
    const be = () => document.querySelector('[data-span-id="be"]') as HTMLElement;
    expect(be().querySelector("[data-trace-icons]")?.textContent).toContain("부제");
    fireEvent.click(screen.getByLabelText("방식 글자 표시"));
    expect(onToggle).toHaveBeenCalledWith(true);
    rerender(<TraceTimeline trace={trace} labelFor={(s) => ({ title: s.id, sub: "부제" })} methodBadgeFor={methodBadgeFor} showMethodText onShowMethodTextChange={onToggle} />);
    expect(be().querySelector("[data-trace-icons]")?.textContent).toContain("임의 위임 방식 · 같은 세션");
  });
  it("renderIcon·renderTooltip 슬롯으로 앱이 아이콘과 툴팁을 주입한다", () => {
    render(
      <TraceTimeline
        trace={trace}
        labelFor={labelFor}
        methodBadgeFor={(s) => (s.parent_id ? { text: "방식", iconName: "zz" } : undefined)}
        renderIcon={(n) => <i data-icon={n} />}
        renderTooltip={(c, child) => <b data-tip={c}>{child}</b>}
      />,
    );
    const be = document.querySelector('[data-span-id="be"]') as HTMLElement;
    expect(be.querySelector('[data-icon="zz"]')).toBeTruthy();
    expect(be.querySelector('[data-tip="방식"]')).toBeTruthy();
  });
  it("형제(독립) 넘기기 화살표와 순번 칩", () => {
    render(<TraceTimeline trace={trace} labelFor={labelFor} />);
    expect(document.querySelectorAll("line[data-handoff]")).toHaveLength(1);
    expect(document.querySelector('[data-order="2"]')).toBeTruthy();
  });
  it("showUserWait=false면 대기 행이 사라진다", () => {
    render(<TraceTimeline trace={trace} labelFor={labelFor} showUserWait={false} />);
    expect(document.querySelector('[data-span-id="wait"]')).toBeNull();
  });
  it("키보드: 방향키 이동, ←로 접기, →로 펴기, Enter 선택, Home/End", () => {
    const onSelect = vi.fn();
    render(<TraceTimeline trace={trace} labelFor={labelFor} onSelect={onSelect} />);
    const first = screen.getByRole("treeitem", { name: /이름-pl/ });
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(document.activeElement?.getAttribute("data-span-id")).toBe("be");
    fireEvent.keyDown(document.activeElement!, { key: "End" });
    expect(document.activeElement?.getAttribute("data-span-id")).toBe("qa");
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    expect(document.querySelector('[data-span-id="be"]')).toBeNull();
    expect(first.getAttribute("aria-expanded")).toBe("false");
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(document.querySelector('[data-span-id="be"]')).toBeTruthy();
    fireEvent.keyDown(first, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("pl");
  });
  it("+/- 는 onTimeScaleChange, 상세는 renderDetail, 하이라이트", () => {
    const onScale = vi.fn();
    render(<TraceTimeline trace={trace} labelFor={labelFor} timeScale={2} onTimeScaleChange={onScale} selectedSpanId="be" renderDetail={(s) => <div>상세 {s.task_preview}</div>} highlightNodeId="qa" />);
    fireEvent.keyDown(screen.getByRole("treeitem", { name: /이름-pl/ }), { key: "+" });
    expect(onScale).toHaveBeenCalledWith(3);
    expect(screen.getByText("상세 API 설계")).toBeTruthy();
    expect(document.querySelector('[data-span-id="qa"]')?.getAttribute("data-highlighted")).toBe("true");
  });
  it("messages로 문구를 바꾼다", () => {
    render(<TraceTimeline trace={{ run_id: "r", spans: [] }} messages={{ empty: "none" }} />);
    expect(screen.getByText("none")).toBeTruthy();
  });
});
