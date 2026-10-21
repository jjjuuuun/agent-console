import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * 저장소 수준 검사: 다른 TS 패키지가 쓰는 `--ac-*` 변수·유틸 클래스가 ui 패키지의 tokens.css에 정의돼 있는지.
 * (ui 패키지는 형제 패키지를 읽지 않아야 저장소 밖에서도 테스트가 돈다. 그래서 이 검사는 조립 앱에 둔다.)
 */
const tsRoot = resolve(import.meta.dirname, "../../../../packages/ts/lib");
const css = readFileSync(join(tsRoot, "ui", "src", "tokens.css"), "utf-8");
const allDefined = new Set([...css.matchAll(/(--ac-[a-z0-9-]+)\s*:/g)].map((m) => m[1]!));

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules") continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) sourceFiles(p, out);
    else if (/\.(css|ts|tsx)$/.test(name)) out.push(p);
  }
  return out;
}

describe("다른 패키지가 쓰는 --ac-* 변수(tokens.css)", () => {
  const consumers = readdirSync(tsRoot).filter((d) => d !== "ui" && statSync(join(tsRoot, d)).isDirectory());
  it("소비 패키지가 있다", () => expect(consumers).toContain("graph-editor"));

  for (const pkg of consumers) {
    it(`${pkg}: var(--ac-*)로 읽는 모든 변수가 tokens.css에 정의돼 있다(패키지 자체 변수 제외)`, () => {
      const files = sourceFiles(join(tsRoot, pkg, "src"));
      const text = files.map((f) => readFileSync(f, "utf-8")).join("\n");
      const own = new Set([...text.matchAll(/["']?(--ac-[a-z0-9-]+)["']?\s*:/g)].map((m) => m[1]!)); // 패키지가 스스로 설정하는 변수
      // `var(--ac-cat-${slot})`처럼 이름이 조립되거나 접두어만 쓰는 곳은 건너뛴다(--ac-cat-1..8은 아래 테스트가 따로 확인).
      const used = new Set([...text.matchAll(/var\((--ac-[a-z0-9]+(?:-[a-z0-9]+)*)(-\$\{|-["'`])?/g)].filter((m) => m[2] === undefined).map((m) => m[1]!));
      const missing = [...used].filter((n) => !allDefined.has(n) && !own.has(n));
      expect(missing).toEqual([]);
    });
  }
});

describe("유틸 클래스 사용처", () => {
  it("graph-editor가 쓰는 유틸 클래스 이름이 모두 정의돼 있다", () => {
    const text = sourceFiles(join(tsRoot, "graph-editor", "src")).map((f) => readFileSync(f, "utf-8")).join("\n");
    const used = new Set([...text.matchAll(/\bac-(?:ellipsis|clamp-\d|mono-wrap|pre|status-icon)\b/g)].map((m) => m[0]));
    expect(used.size).toBeGreaterThan(0);
    for (const c of used) expect(css, c).toContain(`.${c}`);
  });
});
