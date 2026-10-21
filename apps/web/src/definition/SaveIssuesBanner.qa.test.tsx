import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SaveIssuesBanner } from "./SaveIssuesBanner";

afterEach(cleanup);
// 4R.19 QA: 경고 배너 접근성
describe("SaveIssuesBanner", () => {
  it("빈 목록이면 아무것도 그리지 않는다", () => {
    const { container } = render(<SaveIssuesBanner issues={[]} />);
    expect(container.innerHTML).toBe("");
  });
  it("경고는 이름 있는 status 영역이며(alert 아님) 항목과 경로가 목록으로 나온다", () => {
    render(<SaveIssuesBanner issues={[{ severity: "warning", code: "a", message: "첫째", path: "/files/.git/x" }, { severity: "warning", code: "a", message: "둘째" }] as never} />);
    const region = screen.getByRole("status", { name: "저장 경고" });
    expect(region.querySelectorAll("li").length).toBe(2);
    expect(region.textContent).toContain(".git/x");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
