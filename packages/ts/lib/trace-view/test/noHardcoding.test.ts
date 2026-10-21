import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * 연결 종류·노드 종류·위임 방식·조건 연산자의 이름과 그 config 키는 코드에 없다(R0, screen-delegation.md §11).
 * 화면은 디스크립터 속성(`cycle`·`handles_failure`·`invocation`·`binds`·`scheduling`)과 서버가 주는 목록만 본다.
 * 계약이 고정한 RunEvent 타입 문자열(`loop.iteration` 등)은 앱의 이벤트 매핑 표 한 파일에서만 쓴다.
 * 금지 목록은 예시 이름이며, 새 이름이 생기면 여기에 더한다.
 */
const FORBIDDEN = [
  // 종류 이름(예시)
  "loop", "when", "on_error", "delegate", "team", "host", "subagent",
  // config 키(예시)
  "max_iterations", "conditions", "team_ref",
  // 계약이 고정한 이벤트 타입
  "loop.iteration", "loop.exhausted", "run.child_started", "run.child_finished",
];

/** 대소문자 변형과 접두·접미 변형(`loop:x`·`x_loop`)도 같은 이름으로 본다. */
export function isForbiddenName(literal: string, names: readonly string[] = FORBIDDEN): boolean {
  const lower = literal.toLowerCase();
  const esc = (n: string) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return names.some((n) => lower === n || new RegExp(`^${esc(n)}[:._/-]`).test(lower) || new RegExp(`[:._/-]${esc(n)}$`).test(lower));
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}
const SRC = join(__dirname, "..", "src");
const files = walk(SRC).filter((f) => /\.(ts|tsx)$/.test(f) && !/\.test\./.test(f) && !/testing\.ts$/.test(f));

/** 따옴표 문자열 리터럴만 본다(주석·모듈 경로 제외). */
function literals(source: string): string[] {
  const text = source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:"'`])\/\/.*$/gm, "$1")
    .replace(/\b(from|import)\s*\(?\s*(["'])[^"']*\2/g, "$1 ");
  const out: string[] = [];
  for (const m of text.matchAll(/(["'`])((?:\\.|(?!\1)[^\\\n])*)\1/g)) out.push(m[2] as string);
  return out;
}

describe("noHardcoding", () => {
  it("검사기 자신: 변형을 잡고 정상 문구는 통과시킨다", () => {
    for (const bad of ["loop", "Loop", "ON_ERROR", "delegate", "team", "host", "loop:iteration", "x_when", "max_iterations", "run.child_started"]) expect(isForbiddenName(bad)).toBe(true);
    for (const ok of ["looping", "whenever", "hosted", "teamwork", "", "a loop b", "cycle", "invocation"]) expect(isForbiddenName(ok)).toBe(false);
  });
  it("검사 대상이 있다", () => expect(files.length).toBeGreaterThan(3));
  it.each(files.map((f) => [f.slice(SRC.length + 1), f] as const))("%s에 종류 이름·config 키 리터럴이 없다", (_n, file) => {
    const hits = literals(readFileSync(file, "utf8")).filter((l) => isForbiddenName(l));
    expect(hits).toEqual([]);
  });
});
