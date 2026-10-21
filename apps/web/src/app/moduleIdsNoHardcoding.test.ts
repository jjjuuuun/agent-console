import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * 웹 앱 코드에는 서버 기능 모듈 id(`mod-*`, `link-*`, `ac-mod-*`)가 없다. 화면은 모듈이 선언한 역할(`web_roles`, 예: `logs`·`logs:trace`)로만
 * 켜짐을 판단한다(4R.17, 3R.32). 문서 주석의 설명은 제외하고 따옴표 문자열만 본다.
 */
function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}
const SRC = resolve(__dirname, "..");
const files = walk(SRC).filter((f) => /\.(tsx?|json)$/.test(f) && !/\.test\.tsx?$/.test(f) && !/[\\/]testing[\\/]/.test(f));

describe("웹 앱 코드에 모듈 id 문자열이 없다", () => {
  it("검사 대상이 있다", () => expect(files.length).toBeGreaterThan(50));
  it("따옴표 문자열 안에 mod-·link-·ac-mod- 모듈 id가 없다", () => {
    const hits: string[] = [];
    for (const f of files) {
      const text = readFileSync(f, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
      for (const m of text.matchAll(/(["'`])((?:\\.|(?!\1)[^\\\n])*)\1/g)) {
        if (/^(mod|link|ac-mod|ac-link)-[a-z]/.test(m[2] as string)) hits.push(`${f.slice(SRC.length + 1)}: ${m[2]}`);
      }
    }
    expect(hits).toEqual([]);
  });
});
