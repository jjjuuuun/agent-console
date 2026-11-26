import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const css = readFileSync(`${__dirname}/styles.css`, "utf-8");

describe("주 단추 호버 대비", () => {
  it("primary 변형은 자기 hover 배경(--ac-accent-hover)과 밝은 글자색을 가진다", () => {
    const rule = css
      .split("\n")
      .find((l) => l.startsWith('.ac-fp-btn[data-variant="primary"]:hover'));
    expect(rule).toBeDefined();
    expect(rule).toContain("background: var(--ac-accent-hover)");
    expect(rule).toContain("color: var(--ac-text-on-accent)");
    expect(rule).not.toContain("--ac-hover-bg");
  });
});
