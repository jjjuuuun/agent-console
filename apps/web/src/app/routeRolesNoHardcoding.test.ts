import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { DEFAULT_ROUTES } from "../shell/routeConfig";

/**
 * 기능 코드는 라우트 id가 아니라 역할(`RouteDef.serves`)로 다른 화면을 찾는다(phase1r-review H3).
 * features/ 와 shell/(라우트 설정·페이지 표 제외)에서 라우트 id를 따옴표로 골라 라우트를 찾으면 실패한다.
 */

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

const SRC = resolve(__dirname, "..");
const files = [...walk(join(SRC, "features")), ...walk(join(SRC, "shell"))].filter(
  (f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f) && !/shell[\\/](routeConfig|routes)\.tsx?$/.test(f),
);
const ids = DEFAULT_ROUTES.map((r) => r.id).join("|");
const pickById = new RegExp(`(routePath|routeIdOf\\w*)\\(\\s*["'\`](${ids})["'\`]|\\b(r|route)\\.id\\s*===\\s*["'\`](${ids})["'\`]|routeId:\\s*["'\`](${ids})["'\`]`);

describe("기능 코드가 라우트 id를 직접 고르지 않는다", () => {
  it("검사 대상이 있다", () => expect(files.length).toBeGreaterThan(20));
  it("모든 기본 라우트가 역할을 가진다", () => {
    expect(DEFAULT_ROUTES.filter((r) => !r.serves)).toEqual([]);
  });
  it.each(files.map((f) => [f.slice(SRC.length + 1), f] as const))("%s", (_n, f) => {
    expect(pickById.exec(readFileSync(f, "utf8"))?.[0]).toBeUndefined();
  });
});
