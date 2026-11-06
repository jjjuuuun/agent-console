import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { DocumentNav } from "./DocumentNav";
import { GateNotice } from "./GateNotice";
import { PlanBundles } from "./PlanBundles";
import { PlanGraph } from "./PlanGraph";
import { SpecList } from "./SpecList";
import { TaskTable } from "./TaskTable";
import { TraceMatrix } from "./TraceMatrix";
import { sampleDocuments, samplePlan, sampleSpecs, sampleStatuses, sampleTasks, sampleTrace } from "./testing";

afterEach(cleanup);
beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

/** 레이아웃 없는 DOM이라 색 대비는 tokens 쪽 대비 쌍 시험이 맡고 여기서는 구조 규칙만 본다. */
async function violations(el: Element) {
  const r = await axe.run(el, { rules: { "color-contrast": { enabled: false } } });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html.slice(0, 120)).join(" | ")}`);
}

describe("접근성 (axe 0건)", () => {
  it("검사기 자신: 이름 없는 버튼은 잡는다", async () => {
    const { container } = render(<button type="button" aria-label="" />);
    expect((await violations(container)).join("\n")).toContain("button-name");
  });
  it("스펙 목록·문서 목록·빈 상태", async () => {
    const a = render(<SpecList specs={sampleSpecs()} selectedId="sp1" />);
    expect(await violations(a.container)).toEqual([]);
    a.unmount();
    const b = render(<SpecList specs={[]} />);
    expect(await violations(b.container)).toEqual([]);
    b.unmount();
    const c = render(<DocumentNav documents={sampleDocuments()} selectedId="d-req" />);
    expect(await violations(c.container)).toEqual([]);
  });
  it("작업 표(펼침·상태 메뉴 열림·충돌·문법 없음·빈 상태)", async () => {
    const { container, unmount } = render(<TaskTable tasks={sampleTasks()} statuses={sampleStatuses()} conflicts={{ T2: { task_key: "T2", text: "줄" } }} onStatusChange={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: /^작업 T2, 상태 열림/ }));
    fireEvent.click(screen.getByRole("button", { name: "작업 T4의 상태 바꾸기: 진행" }));
    expect(await violations(container)).toEqual([]);
    unmount();
    for (const el of [<TaskTable key="a" tasks={[]} statuses={[]} />, <TaskTable key="b" tasks={sampleTasks()} statuses={[]} syntaxEmpty />]) {
      const r = render(el);
      expect(await violations(r.container)).toEqual([]);
      r.unmount();
    }
  });
  it("계획 그래프·묶음 글", async () => {
    const { container } = render(<PlanGraph plan={samplePlan()} tasks={sampleTasks()} statuses={sampleStatuses()} engine={async () => ({})} height={300} />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(await violations(container)).toEqual([]);
    const b = render(<PlanBundles plan={{ ...samplePlan(), cycles: [["T3", "T4"]] }} tasks={sampleTasks()} onSelect={() => undefined} />);
    expect(await violations(b.container)).toEqual([]);
  });
  it("추적 표·관문 안내", async () => {
    const a = render(<TraceMatrix matrix={sampleTrace()} onOpenTask={() => undefined} onOpenRequirement={() => undefined} />);
    expect(await violations(a.container)).toEqual([]);
    a.unmount();
    const b = render(<GateNotice details={{ gate_id: "g", message: "막힘", document_ids: ["d"] }} onOpenDocument={() => undefined} onDismiss={() => undefined} />);
    expect(await violations(b.container)).toEqual([]);
  });
});
