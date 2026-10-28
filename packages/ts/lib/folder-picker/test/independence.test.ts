import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "src");
const files = readdirSync(SRC).filter((f) => /\.(ts|tsx|css)$/.test(f) && !/\.test\./.test(f));

describe("독립성", () => {
  it("다른 사내 패키지(api-client 포함)를 import하지 않는다", () => {
    for (const f of files) expect(readFileSync(join(SRC, f), "utf-8"), f).not.toMatch(/from\s+["']@agent-console\//);
  });
  it("색을 hex로 직접 쓰지 않는다(토큰만)", () => {
    for (const f of files.filter((n) => n.endsWith(".css"))) expect(readFileSync(join(SRC, f), "utf-8"), f).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
  it("WSL 전용 경로·제안 UI가 없다", () => {
    for (const f of files) expect(readFileSync(join(SRC, f), "utf-8"), f).not.toMatch(/\/mnt\/|suggest/);
  });
});
