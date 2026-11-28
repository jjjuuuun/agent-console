import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ArchitectureDiagram, cellAccessibleName, defaultMessages } from "./index";
import { defaultProfileView } from "./testing";

afterEach(cleanup);

describe("칸 접근 이름: 보이는 글자로 시작한다(WCAG 2.5.3)", () => {
  it("보이는 글자는 그대로 앞에 두고 없는 조각만 뒤에 덧붙인다", () => {
    const cell = defaultProfileView().cells?.[0];
    if (!cell) throw new Error("fixture cell");
    const name = cellAccessibleName(cell, `${cell.label} 화면 글자`, defaultMessages);
    expect(name.startsWith(`${cell.label} 화면 글자`)).toBe(true);
  });

  it("그림의 칸 단추 이름은 칸 제목으로 시작하고 배율 단추는 보이는 퍼센트를 포함한다", () => {
    const view = defaultProfileView();
    render(<ArchitectureDiagram view={view} containerSize={{ width: 1200, height: 700 }} />);
    const cell = view.cells?.[0];
    if (!cell) throw new Error("fixture cell");
    const btn = document.querySelector<HTMLButtonElement>(`button[data-cell-id="${cell.id}"]`);
    expect(btn?.getAttribute("aria-label")?.startsWith(cell.label)).toBe(true);
    const scale = document.querySelector<HTMLButtonElement>(".ac-arch-scale");
    expect(scale?.getAttribute("aria-label")).toContain(scale?.textContent ?? "?");
    expect(screen.queryAllByRole("button").length).toBeGreaterThan(0);
  });
});
