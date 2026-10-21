import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Avatar } from "./Avatar";

afterEach(cleanup);

describe("Avatar", () => {
  it("avatar 지정이 없으면 이름 첫 글자 + id 해시 색", () => {
    const { container } = render(<Avatar agentId="a" name="기획자" />);
    const el = container.querySelector("[data-avatar]") as HTMLElement;
    expect(el.textContent).toBe("기");
    expect(el.style.background).toMatch(/var\(--ac-cat-[1-8]\)/);
  });
  it("앱이 해석한 글자·색을 우선한다", () => {
    const { container } = render(<Avatar agentId="a" name="기획자" avatar={{ text: "🚀", color: "#123456" }} />);
    const el = container.querySelector("[data-avatar]") as HTMLElement;
    expect(el.textContent).toBe("🚀");
    expect(el.style.background).toMatch(/#123456|rgb\(18, 52, 86\)/);
  });
});
