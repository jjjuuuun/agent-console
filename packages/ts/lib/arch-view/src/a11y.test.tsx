import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it } from "vitest";
import { ArchitectureCellList, ArchitectureDiagram, ArchitectureInfoBar, ArchitectureLegend } from "./index";
import { defaultProfileView } from "./testing";

afterEach(cleanup);

/** 레이아웃 없는 DOM이라 색 대비는 tokens.test(대비 쌍)가 맡고 여기서는 구조 규칙만 본다. */
async function violations(el: Element) {
  const r = await axe.run(el, { rules: { "color-contrast": { enabled: false } } });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html.slice(0, 120)).join(" | ")}`);
}
const SIZE = { width: 1200, height: 700 };

describe("접근성 (axe 0건, 수용 §13-25)", () => {
  it("검사기 자신: 이름 없는 버튼은 잡는다", async () => {
    const { container } = render(<button type="button" />);
    expect((await violations(container)).join("\n")).toContain("button-name");
  });
  it("그림: 전체 표시", async () => {
    const { container } = render(<ArchitectureDiagram view={defaultProfileView()} containerSize={SIZE} selection={{ kind: "cell", id: "llm" }} highlight={{ profile: "p", cells: ["input"], edges: ["task_submit"] }} onSkip={() => undefined} />);
    expect(await violations(container)).toEqual([]);
  });
  it("그림: 요약 표시", async () => {
    const { container } = render(<ArchitectureDiagram view={defaultProfileView()} containerSize={SIZE} scale={0.4} fitMode="none" />);
    expect(await violations(container)).toEqual([]);
  });
  it("목록·범례 열림·배치 미리보기", async () => {
    const { container } = render(<ArchitectureDiagram view={defaultProfileView()} containerSize={SIZE} defaultViewMode="list" />);
    expect(await violations(container)).toEqual([]);
    cleanup();
    const r2 = render(<ArchitectureDiagram view={defaultProfileView()} containerSize={SIZE} />);
    fireEvent.click(screen.getByRole("button", { name: "범례" }));
    expect(await violations(r2.container)).toEqual([]);
    cleanup();
    const r3 = render(<ArchitectureDiagram view={defaultProfileView()} containerSize={SIZE} mode="layout" />);
    expect(await violations(r3.container)).toEqual([]);
  });
  it("단독 부품: 목록·정보 줄·범례", async () => {
    const v = defaultProfileView();
    const { container } = render(
      <div>
        <ArchitectureCellList view={v} />
        <ArchitectureInfoBar view={v} target={{ kind: "cell", id: "mcp" }} />
        <ArchitectureLegend />
      </div>,
    );
    expect(await violations(container)).toEqual([]);
  });
  it("구조 연결의 접근 이름에는 횟수가 없고 '구조 연결'이 붙는다", () => {
    const { container } = render(<ArchitectureCellList view={defaultProfileView()} />);
    const labels = Array.from(container.querySelectorAll("[aria-label]")).map((b) => b.getAttribute("aria-label") ?? "");
    expect(labels.filter((l) => l.startsWith("ID / 응답"))).toEqual(["ID / 응답, 에이전트 제어에서 SDK / CLI로, 구조 연결"]);
  });
  it("이름 없는 button 0, 칸 이름이 비어 있지 않다", () => {
    const { container } = render(<ArchitectureDiagram view={defaultProfileView()} containerSize={SIZE} />);
    for (const b of container.querySelectorAll("button")) expect((b.getAttribute("aria-label") ?? b.textContent ?? "").trim(), b.outerHTML.slice(0, 100)).not.toBe("");
  });
});
