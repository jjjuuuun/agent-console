import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// 5.7R.37: 긴 키는 앞부분만 말줄임하고 마지막 마디는 남는다(레이아웃 API가 없어 CSS 규칙을 읽는다).
const css = readFileSync(join(import.meta.dirname, "styles.css"), "utf8");
const rule = (selector: string): string => {
  const m = css.match(new RegExp(`^${selector.replace(/\./g, "\\.")}\\s*\\{([^}]*)\\}`, "m"));
  if (m === null) throw new Error(`규칙 없음: ${selector}`);
  return m[1] ?? "";
};

describe("키 칸 말줄임", () => {
  it("앞부분은 줄어들며 말줄임하고 마지막 마디는 줄지 않는다", () => {
    expect(rule(".ac-mem-key")).toMatch(/display:\s*flex/);
    const head = rule(".ac-mem-key-head");
    expect(head).toMatch(/flex:\s*0 1 auto/);
    expect(head).toMatch(/text-overflow:\s*ellipsis/);
    expect(head).toMatch(/min-width:\s*0/);
    expect(rule(".ac-mem-key-last")).toMatch(/flex:\s*0 0 auto/);
  });
});
