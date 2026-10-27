import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * 칸 id·연결 id·tone·style·영역 style·지표 이름은 데이터다(R0, screen-architecture.md §13-1).
 * 컴포넌트·계산 코드에는 그 이름이 없다. 이름이 나오는 곳은 X24 기본 대응표 `defaults.ts`(prop으로 바꿀 수 있는 데이터)뿐이고,
 * 예제 데이터 `testing.ts`와 테스트는 검사 대상이 아니다. 금지 목록은 예시이며 새 이름이 생기면 더한다.
 * (영역 style 세 가지는 CSS가 [data-zone-style] 선택자로 고르고, 컴포넌트가 알아보는 이름은 Nodes.tsx 한 곳이다.)
 */
const FORBIDDEN = [
  // 기본 프로필 칸 id
  "input", "sdk", "api", "rules", "instructions", "context", "llm", "dispatch", "hook", "tools", "mcp", "result", "workspace", "delegation", "subagents", "response",
  // 기본 프로필 연결 id
  "task_submit", "tool_call", "model_output", "mcp_call", "delegate", "merge",
  // tone 이름
  "blue", "teal", "pink", "orange", "gold", "purple", "sky", "rose",
  // 연결 style 이름
  "request", "return",
  // 지표 이름
  "count", "errors", "tokens", "duration", "inferred_duration",
];
/** 이 파일들만 예외: 기본 대응표(데이터)와 예제. */
const EXEMPT = new Set(["defaults.ts", "testing.ts"]);

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
    for (const bad of ["llm", "LLM", "blue", "request", "count", "inferred_duration"]) expect(isForbidden(bad)).toBe(true);
    for (const ok of ["", "cell", "edge", "full", "summary", "data-cell-id", "ac-arch-cell"]) expect(isForbidden(ok)).toBe(false);
  });
  it("검사 대상이 있다", () => expect(files.length).toBeGreaterThan(8));
  it.each(files.map((f) => [f.slice(SRC.length + 1), f] as const))("%s에 칸·연결·tone·style·지표 이름 리터럴이 없다", (_n, file) => {
    expect(literals(readFileSync(file, "utf8")).filter((l) => isForbidden(l))).toEqual([]);
  });
  it("CSS에도 칸 id·연결 id·색 이름이 없다(hex 직접 사용 금지)", () => {
    const css = readFileSync(join(SRC, "styles.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(css).not.toMatch(/data-(cell|edge|zone)-id="/);
    expect(css).not.toMatch(/data-tone|\[data-(style|tone)="/);
  });
});
