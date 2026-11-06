import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * 작업 상태·문서 상태·문서 종류·단계·톤을 정하는 이름·모듈 id·프리셋 이름은 서버/사용자 데이터다(R0.1, docs/design/screen-sdd.md S1).
 * 컴포넌트·계산 코드에는 그 이름이 없다. 표본 데이터 `testing.ts`와 테스트는 검사 대상이 아니다.
 * 금지 목록은 예시이며 새 이름이 생기면 더한다. 톤 어휘(neutral·info·success·warning·danger)는 서버 톤 어휘라 허용한다.
 */
const FORBIDDEN = [
  // 상태 이름 예시
  "todo", "done", "in_progress", "doing", "draft", "approved", "review", "blocked_status", "open", "closed",
  // 문서 종류·역할 예시
  "requirements", "tasks", "design", "spec", "plan", "readme",
  // 모듈 id·연동 이름
  "mod-sdd", "mod-runs", "mod-projects", "link-runs-sdd", "link-projects-sdd", "sdd", "runs",
  // 실행 연결 종류
  "run", "verification",
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
    for (const bad of ["todo", "Done", "requirements", "mod-sdd", "link-runs-sdd", "run"]) expect(isForbidden(bad)).toBe(true);
    for (const ok of ["", "neutral", "success", "status", "document", "data-tone", "ac-sdd-task", "task_key"]) expect(isForbidden(ok)).toBe(false);
  });
  it("검사 대상이 있다", () => expect(files.length).toBeGreaterThan(12));
  it.each(files.map((f) => [f.slice(SRC.length + 1), f] as const))("%s에 상태·문서 종류·모듈 이름 리터럴이 없다", (_n, file) => {
    expect(literals(readFileSync(file, "utf8")).filter((l) => isForbidden(l))).toEqual([]);
  });
  it("문구 표에도 특정 상태·문서 종류 이름이 없다", () => {
    const text = readFileSync(join(SRC, "messages.ts"), "utf8");
    for (const word of ["초안", "승인됨", "구현 중", "요구사항", "TODO"]) expect(text).not.toContain(word);
  });
  it("CSS에는 hex 색과 상태 이름 선택자가 없다", () => {
    const css = readFileSync(join(SRC, "styles.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(css).not.toMatch(/data-(status|state|kind|stage)[^a-z]/);
  });
  it("api-client·log-view·ui를 import하지 않는다", () => {
    for (const f of files) {
      const src = readFileSync(f, "utf8");
      expect(src, f).not.toMatch(/from ["']@agent-console\/(api-client|log-view|ui|graph-editor|schema-form)["']/);
    }
  });
  it("contracts는 타입만 가져온다", () => {
    for (const f of files) {
      const src = readFileSync(f, "utf8");
      for (const m of src.matchAll(/^import\s+(?!type\b)[^;]*from ["']@agent-console\/contracts[^"']*["']/gm)) throw new Error(`${f}: ${m[0]}`);
    }
  });
});
