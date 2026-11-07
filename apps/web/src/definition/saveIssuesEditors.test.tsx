import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SaveIssuesBanner } from "./SaveIssuesBanner";

afterEach(cleanup);

describe("SaveIssuesBanner: 평문 비밀 저장 경고(X-Console-Issues)", () => {
  it("secret.plain_found warning의 메시지와 경로를 띠로 보인다", () => {
    render(<SaveIssuesBanner issues={[{ severity: "warning", code: "secret.plain_found", path: "/env/KEY", message: "평문 비밀이 저장되었습니다" }]} />);
    expect(screen.getByText(/평문 비밀이 저장되었습니다/)).toBeTruthy();
    expect(screen.getByText("(/env/KEY)")).toBeTruthy();
  });
  it("경고가 없으면 아무것도 그리지 않는다", () => {
    const { container } = render(<SaveIssuesBanner issues={[]} />);
    expect(container.innerHTML).toBe("");
  });
});
