import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import type { Trace, TraceSpan } from "@agent-console/contracts";
import { afterEach, describe, expect, it, vi } from "vitest";
import { defaultExpandedGroups, flattenRows, isCallSpan, spanOrdinals } from "./layout";
import { TraceTimeline } from "./TraceTimeline";

afterEach(cleanup);

const span = (id: string, over: Partial<TraceSpan> = {}): TraceSpan => ({ id, kind: "x-kind", started_at: 0, ended_at: 10, status: "succeeded", ...over });

/** 임의 이름의 노드·종류만 쓴다. 호출 span = `call` 필드가 있고 위임자 span 아래. 자식 Run span = `run_id`가 다름. */
const trace: Trace = {
  run_id: "root",
  spans: [
    span("lead", { node_id: "n1", started_at: 0, ended_at: 50 }),
    span("callee-a", { parent_id: "lead", node_id: "n2", call: 0, started_at: 2, ended_at: 10, task_preview: "과제 하나" }),
    span("callee-b", { parent_id: "lead", node_id: "n2", call: 1, started_at: 12, ended_at: 20 }),
    span("w0", { node_id: "n3", iteration: 0, started_at: 50, ended_at: 60 }),
    span("w1", { node_id: "n3", iteration: 1, started_at: 70, ended_at: 80 }),
    span("nest", { node_id: "n4", started_at: 80, ended_at: 100 }),
    span("c-top", { parent_id: "nest", run_id: "child-run-1", node_id: "m1", started_at: 82, ended_at: 90 }),
    span("c-sub", { parent_id: "c-top", run_id: "child-run-1", node_id: "m2", started_at: 83, ended_at: 89 }),
    span("g-top", { parent_id: "c-sub", run_id: "grand-run-2", node_id: "q1", started_at: 84, ended_at: 88 }),
  ],
  links: [{ source: "w0", target: "w1", edge_id: "e", kind: "kind-z" }],
};

describe("layout: 회차·호출·묶음", () => {
  it("회차는 같은 노드에 둘 이상일 때만 번호를 단다", () => {
    const o = spanOrdinals(trace.spans!);
    expect(o.get("w0")?.iteration).toBe(0);
    expect(o.get("w1")?.iteration).toBe(1);
    expect(o.get("lead")).toBeUndefined();
    expect(o.get("callee-a")?.call).toBe(0);
    expect(o.get("callee-b")?.call).toBe(1);
    expect(spanOrdinals([span("only", { node_id: "z", call: 0, iteration: 0 })].slice()).size).toBe(0);
  });
  it("자식 Run은 묶음 행 아래로 중첩되고 접으면 숨는다", () => {
    const open = flattenRows(trace.spans!, { runId: "root", expandedGroups: new Set(["child-run-1", "grand-run-2"]) });
    const ids = open.map((r) => [r.span.id, r.depth]);
    expect(ids).toContainEqual(["group:child-run-1", 1]);
    expect(ids).toContainEqual(["c-top", 2]);
    expect(ids).toContainEqual(["group:grand-run-2", 4]);
    expect(ids).toContainEqual(["g-top", 5]);
    const closed = flattenRows(trace.spans!, { runId: "root" });
    expect(closed.some((r) => r.span.id === "c-top")).toBe(false);
    expect(closed.find((r) => r.group)?.expanded).toBe(false);
    // runId가 없으면 묶지 않는다
    expect(flattenRows(trace.spans!).some((r) => r.group)).toBe(false);
  });
  it("기본 펼침은 끝나지 않은 묶음만", () => {
    const spans = [span("a", { run_id: "c1" }), span("b", { run_id: "c2", ended_at: null }), span("r")];
    expect([...defaultExpandedGroups(spans, "root")]).toEqual(["c2"]);
  });
});

describe("TraceTimeline: 위임 호출·회차·자식 묶음", () => {
  const labelFor = (s: TraceSpan) => ({ title: `이름-${s.node_id ?? s.id}` });

  it("호출 span은 위임자 아래 들여 쓰고 별도 세션 배지, 과제는 막대 안, 호출 번호는 +1", () => {
    render(<TraceTimeline trace={trace} labelFor={labelFor} />);
    const a = document.querySelector('[data-span-id="callee-a"]')!;
    expect(a.getAttribute("aria-level")).toBe("2");
    expect(a.getAttribute("data-call")).toBe("true");
    expect(a.querySelector('[data-session-badge="separate"]')?.getAttribute("aria-label")).toBe("별도 세션");
    expect(a.querySelector('[data-task-preview="true"]')?.textContent).toBe("과제 하나");
    expect(a.textContent).toContain("이름-n2 · 호출 1");
    expect(document.querySelector('[data-span-id="callee-b"]')?.textContent).toContain("이름-n2 · 호출 2");
  });
  it("반복 회차 이름 뒤 #n과 링크 칩", () => {
    render(<TraceTimeline trace={trace} labelFor={labelFor} linkBadgeFor={(l) => ({ text: `칩-${l.kind}`, iconName: "↻" })} />);
    expect(document.querySelector('[data-span-id="w0"]')?.textContent).toContain("이름-n3 #1");
    expect(document.querySelector('[data-span-id="w1"]')?.textContent).toContain("이름-n3 #2");
    expect(document.querySelector("[data-link-badge]")?.textContent).toContain("칩-kind-z");
  });
  it("자식 Run 묶음: 끝났으면 접힘, Enter로 펴고 접기, 사용자 선택 유지, Ctrl+Enter로 열기", () => {
    const onOpen = vi.fn();
    const onToggle = vi.fn();
    const { rerender } = render(
      <TraceTimeline trace={trace} labelFor={labelFor} onOpenChildRun={onOpen} onGroupToggle={onToggle} groupBadgeFor={(g) => ({ title: `팀-${g.runId}`, sub: `${g.spans.length}개` })} />,
    );
    const row = () => document.querySelector('[data-group="child-run-1"]') as HTMLElement;
    expect(row().getAttribute("aria-expanded")).toBe("false");
    expect(row().getAttribute("aria-label")).toContain("자식 실행 팀-child-run-1");
    expect(document.querySelector('[data-span-id="c-top"]')).toBeNull();
    row().focus();
    fireEvent.keyDown(row(), { key: "Enter" });
    expect(onToggle).toHaveBeenCalledWith("child-run-1", true);
    expect(document.querySelector('[data-span-id="c-top"]')).toBeTruthy();
    // 새 데이터가 와도 사용자가 편 상태가 유지된다
    rerender(<TraceTimeline trace={{ ...trace }} labelFor={labelFor} />);
    expect(document.querySelector('[data-span-id="c-top"]')).toBeTruthy();
    fireEvent.keyDown(row(), { key: "Enter", ctrlKey: true });
    expect(onOpen).not.toHaveBeenCalled(); // 이 렌더에는 onOpenChildRun이 없다
    rerender(<TraceTimeline trace={trace} labelFor={labelFor} onOpenChildRun={onOpen} />);
    fireEvent.keyDown(row(), { key: "Enter", ctrlKey: true });
    expect(onOpen).toHaveBeenCalledWith("child-run-1");
    fireEvent.keyDown(row(), { key: "ArrowLeft" });
    expect(document.querySelector('[data-span-id="c-top"]')).toBeNull();
  });
  it("제어형: expandedGroupIds가 기본값 계산을 대신하고 onGroupToggle만 알린다", () => {
    const onToggle = vi.fn();
    render(<TraceTimeline trace={trace} labelFor={labelFor} expandedGroupIds={["child-run-1"]} onGroupToggle={onToggle} />);
    expect(document.querySelector('[data-span-id="c-top"]')).toBeTruthy();
    fireEvent.click(document.querySelector('[data-group="child-run-1"] button')!);
    expect(onToggle).toHaveBeenCalledWith("child-run-1", false);
    expect(document.querySelector('[data-span-id="c-top"]')).toBeTruthy(); // 상위가 값을 안 바꾸면 그대로
  });
  it("[열기] 버튼은 onOpenChildRun이 있을 때만", () => {
    const onOpen = vi.fn();
    const { rerender } = render(<TraceTimeline trace={trace} labelFor={labelFor} />);
    expect(document.querySelector("[data-open-child]")).toBeNull();
    rerender(<TraceTimeline trace={trace} labelFor={labelFor} onOpenChildRun={onOpen} />);
    fireEvent.click(document.querySelector('[data-open-child="child-run-1"]')!);
    expect(onOpen).toHaveBeenCalledWith("child-run-1");
  });
  it("실행 중 자식은 처음부터 펼침, 모르는 필드는 무시", () => {
    const t: Trace = { run_id: "r", spans: [span("p", { node_id: "a"}), { ...span("k", { parent_id: "p", run_id: "c9", ended_at: null }), extra_unknown: 1 } as TraceSpan] };
    render(<TraceTimeline trace={t} running now={20} labelFor={labelFor} />);
    expect(document.querySelector('[data-span-id="k"]')).toBeTruthy();
  });
  it("접힌 묶음 행도 막대·상태·소요가 보인다", () => {
    render(<TraceTimeline trace={trace} labelFor={labelFor} />);
    const row = document.querySelector('[data-group="child-run-1"]')!;
    expect(row.querySelector(".ac-trace-bar")?.getAttribute("data-status")).toBe("succeeded");
    expect(row.textContent).toContain("span 2개");
  });
  it("제어형 래퍼에서 토글이 반영된다", () => {
    function Wrap() {
      const [ids, setIds] = useState<string[]>([]);
      return <TraceTimeline trace={trace} labelFor={labelFor} expandedGroupIds={ids} onGroupToggle={(id, open) => setIds(open ? [...ids, id] : ids.filter((x) => x !== id))} />;
    }
    render(<Wrap />);
    fireEvent.click(document.querySelector('[data-group="child-run-1"]')!);
    expect(document.querySelector('[data-span-id="c-top"]')).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "접기" })[0]!);
  });
});

describe("isCallSpan", () => {
  it("계약 필드 call만 본다(호출 span은 늘 call을 채운다). 계약에 없는 필드는 읽지 않는다", () => {
    expect(isCallSpan(span("a", { call: 0 }))).toBe(true);
    expect(isCallSpan(span("b", {}))).toBe(false);
    expect(isCallSpan({ ...span("c", {}), invoked_by: ["x"] } as TraceSpan)).toBe(false);
  });
});
