import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MarkdownPreview } from "./MarkdownPreview";

afterEach(cleanup);

describe("MarkdownPreview", () => {
  it("GFM(표)을 그리고 className이 없으면 감싸는 요소가 없다", () => {
    const { container } = render(<MarkdownPreview source={"| a | b |\n| - | - |\n| 1 | 2 |"} />);
    expect(container.querySelector("table")).toBeTruthy();
    expect(container.firstElementChild?.tagName).toBe("TABLE");
  });
  it("원시 HTML은 실행하지 않는다", () => {
    const { container } = render(<MarkdownPreview source={"<script>1</script>\n\n<img src=x onerror=alert(1)>"} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });
  it("renderLink가 링크를 대신 그린다(href·글자를 받는다)", () => {
    render(<MarkdownPreview source="[문서](wiki:a/b)" urlTransform={(u) => u} renderLink={(href, children) => <button type="button" data-href={href}>{children}</button>} />);
    const b = screen.getByRole("button", { name: "문서" });
    expect(b.getAttribute("data-href")).toBe("wiki:a/b");
  });
  it("transformSource가 그리기 전에 원문을 바꾼다", () => {
    render(<MarkdownPreview source="[[페이지]]" transformSource={(t) => t.replace(/\[\[(.+?)\]\]/g, "[$1](/p/page)")} />);
    expect(screen.getByRole("link", { name: "페이지" }).getAttribute("href")).toBe("/p/page");
  });
  it("기본 urlTransform은 위험한 스킴을 막고, 넘기면 허용 스킴을 넓힌다", () => {
    const a = render(<MarkdownPreview source="[x](javascript:alert(1))" />);
    expect(a.container.querySelector("a")?.getAttribute("href") ?? "").toBe("");
    a.unmount();
    const b = render(<MarkdownPreview source="[x](wiki:p)" urlTransform={(u) => u} />);
    expect(b.container.querySelector("a")?.getAttribute("href")).toBe("wiki:p");
  });
  it("className을 주면 그 요소로 감싼다", () => {
    const { container } = render(<MarkdownPreview source="a" className="w" />);
    expect(container.querySelector("div.w p")).toBeTruthy();
  });
});
