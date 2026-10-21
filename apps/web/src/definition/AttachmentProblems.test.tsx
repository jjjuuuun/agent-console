import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AttachmentProblems } from "./AttachmentProblems";

afterEach(cleanup);

describe("첨부 오류 표시", () => {
  const attachments = [{ ref: "r1" }, { ref: "r2", config_override: { env: { K: "***" } } }] as never[];
  it("서버 오류는 해당 첨부 줄에, 가려진 비밀은 비밀 참조 안내로 보인다", () => {
    render(<AttachmentProblems attachments={attachments} errors={{ 0: ["평문 비밀"] }} titleOf={(a) => `이름-${a.ref}`} />);
    const list = screen.getByRole("alert", { name: "첨부 오류" });
    expect(list.textContent).toContain("이름-r1: 평문 비밀");
    expect(list.textContent).toMatch(/이름-r2: .*secret:\/\//);
  });
  it("문제가 없으면 아무것도 그리지 않는다", () => {
    const { container } = render(<AttachmentProblems attachments={[{ ref: "r" }] as never[]} titleOf={(a) => a.ref} />);
    expect(container.firstChild).toBeNull();
  });
});
