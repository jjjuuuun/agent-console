import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, "usage.css"), "utf-8");

describe("사용량 기간 선택(I.14 D1)", () => {
  it("라벨과 선택 상자 사이 간격은 다른 화면의 CSS에 기대지 않고 usage.css가 직접 정한다", () => {
    const rule = /\.usage-rollup-period\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";
    expect(rule).toMatch(/display:\s*flex/);
    expect(rule).toMatch(/gap:\s*var\(--ac-space-2\)/);
    expect(css).not.toMatch(/\.runs-filter/);
  });
});
