import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const here = import.meta.dirname;
const css = readFileSync(join(here, "usage.css"), "utf-8");
const tsx = readFileSync(join(here, "RollupPanel.tsx"), "utf-8");

describe("표 보기 비고 칸 간격(P1.8)", () => {
  it("비고 셀은 막대 보기와 같은 간격 래퍼로 감싼다", () => {
    expect(tsx).toMatch(/const cell = [^;]*<span className="usage-bar-note">/s);
  });
  it("래퍼는 간격 토큰과 줄바꿈을 갖고 5번째 열은 고정 폭이 아니다", () => {
    const rule = /\.usage-bar-note \{([^}]*)\}/.exec(css)![1]!;
    expect(rule).toMatch(/gap:\s*var\(--ac-space-\d+\)/);
    expect(rule).toContain("flex-wrap: wrap");
    expect(css).not.toMatch(/usage-rollup-table th:nth-child\(5\)/);
  });
});
