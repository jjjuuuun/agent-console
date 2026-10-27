import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * 범위 종류 이름·범위 이름·도구 이름은 서버 데이터다(R0.1, docs/design/screen-memory.md §19-1).
 * 컴포넌트·계산 코드에는 그 이름이 없다. 예제 데이터 `testing.ts`와 테스트는 검사 대상이 아니다.
 * 금지 목록은 예시이며 새 이름이 생기면 더한다. (`project_id` 같은 맥락 필드 이름은 계약 어휘라 허용: 정확히 일치하는 낱말만 막는다.)
 */
const FORBIDDEN = [
  // 기본 범위 종류 id
  "shared", "project", "team",
  // 기본 범위 id·예시
  "default", "global",
  // 도구 이름 예시
  "memory_read", "memory_write", "memory_search", "memory_delete", "read_memory", "write_memory", "search_memory", "delete_memory",
  // 예시 사용자 데이터
  "notes", "journal", "pl", "designer", "backend",
];
const EXEMPT = new Set(["testing.ts"]);

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}
const SRC = join(__dirname, "..", "src");
const files = walk(SRC).filter((f) => /\.(ts|tsx)$/.test(f) && !/\.test\./.test(f) && !EXEMPT.has(f.slice(SRC.length + 1)));

function literals(source: string): string[] {
  const text = source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:"'`])\/\/.*$/gm, "$1")
    .replace(/\b(from|import)\s*\(?\s*(["'])[^"']*\2/g, "$1 ");
  const out: string[] = [];
  for (const m of text.matchAll(/(["'`])((?:\\.|(?!\1)[^\\\n])*)\1/g)) out.push(m[2] as string);
  return out;
}
export function isForbidden(literal: string, names: readonly string[] = FORBIDDEN): boolean {
  const lower = literal.toLowerCase();
  return names.some((n) => lower === n);
}

describe("noHardcoding", () => {
  it("검사기 자신", () => {
    for (const bad of ["shared", "Team", "project", "memory_read", "notes"]) expect(isForbidden(bad)).toBe(true);
    for (const ok of ["", "scope", "kind", "project_id", "graph_id", "data-row-id", "ac-mem-tree"]) expect(isForbidden(ok)).toBe(false);
  });
  it("검사 대상이 있다", () => expect(files.length).toBeGreaterThan(8));
  it.each(files.map((f) => [f.slice(SRC.length + 1), f] as const))("%s에 범위 종류·도구 이름 리터럴이 없다", (_n, file) => {
    expect(literals(readFileSync(file, "utf8")).filter((l) => isForbidden(l))).toEqual([]);
  });
  it("문구 표에도 범위 종류 이름이 없다", () => {
    const text = readFileSync(join(SRC, "messages.ts"), "utf8");
    for (const word of ["공용", "shared", "팀 범위"]) expect(text).not.toContain(word);
  });
  it("CSS에는 hex 색과 종류 선택자가 없다", () => {
    const css = readFileSync(join(SRC, "styles.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(css).not.toMatch(/data-(kind|scope)[^a-z]/);
  });
  it("api-client·log-view·ui를 import하지 않는다", () => {
    for (const f of files) {
      const src = readFileSync(f, "utf8");
      expect(src, f).not.toMatch(/from ["']@agent-console\/(api-client|log-view|ui)["']/);
    }
  });
});
