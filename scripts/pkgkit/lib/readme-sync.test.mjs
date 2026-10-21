import { describe, expect, it } from "vitest";

import { checkReadmeSync, extractReadmeBlocks, extractTestRegions, normalizeCode } from "./readme-sync.mjs";

const README = ["# x", "```ts", "ignored()", "```", "```ts readme", 'import { a } from "x";', "", "const v = a();", "```", ""].join("\n");
const TEST = ['import { expect } from "vitest";', "// readme:start", 'import { a } from "x";', "", "const v = a();", "// readme:end", "expect(v);"].join("\n");

describe("normalize", () => {
  it("공통 들여쓰기·줄 끝 공백·앞뒤 빈 줄·CRLF를 정리한다", () => {
    expect(normalizeCode("\r\n    a  \r\n      b\r\n\r\n")).toBe("a\n  b");
  });
});

describe("추출", () => {
  it("ts readme 블록만 뽑는다", () => {
    expect(extractReadmeBlocks(README)).toEqual(['import { a } from "x";\n\nconst v = a();']);
  });
  it("4개짜리 펜스 안의 3개 펜스를 닫힘으로 보지 않는다", () => {
    const md = "````ts readme\nx\n```\ny\n````\n";
    expect(extractReadmeBlocks(md)).toEqual(["x\n```\ny"]);
  });
  it("표시 구간 짝이 안 맞으면 문제로 알린다", () => {
    expect(extractTestRegions("// readme:start\na").problems).toHaveLength(1);
    expect(extractTestRegions("// readme:end").problems).toHaveLength(1);
  });
});

describe("checkReadmeSync", () => {
  it("같으면 문제가 없다", () => {
    expect(checkReadmeSync(README, TEST)).toEqual([]);
  });
  it("다르면 알린다", () => {
    expect(checkReadmeSync(README, TEST.replace("a()", "b()"))).toEqual(["README 블록 1번이 테스트 구간과 다르다"]);
  });
  it("블록이나 구간이 없으면 알린다", () => {
    expect(checkReadmeSync("# x", TEST).join()).toContain("블록이 없다");
    expect(checkReadmeSync(README, "x").join()).toContain("구간이 없다");
  });
  it("개수가 다르면 알린다", () => {
    expect(checkReadmeSync(`${README}\n\`\`\`ts readme\nz\n\`\`\`\n`, TEST).join()).toContain("개수가 다르다");
  });
  it("파일이 없으면 알린다", () => {
    expect(checkReadmeSync(null, TEST)).toHaveLength(1);
    expect(checkReadmeSync(README, null)).toHaveLength(1);
  });
});
