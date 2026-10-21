import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * 출처·범주·위젯·차원·지표 이름은 코드에 없다(R0). 이 이름들은 설정/서버가 주는 데이터이고, 문서와 예시에만 나온다.
 * 예외: `widgets/builtins.tsx`는 내장 위젯 종류(metric·bar·line·table)를 레지스트리 데이터로 정의한다.
 * 금지 목록은 예시 이름이며, 새 이름이 생기면 여기에 더한다.
 */
const FORBIDDEN = [
  // 출처·범주 예시
  "hook", "mcp", "claude-code-jsonl", "platform-runs", "claude-code", "tool_use", "tool_result", "subagent", "prompt", "assistant", "thinking",
  "pretooluse", "posttooluse", "userpromptsubmit", "sessionstart", "sessionend", "notification", "compaction", "attachment",
  // 지표·차원 예시
  "tokens.total", "tokens.input", "tokens.output", "cache_read", "cache_creation", "day", "hour",
];

/** 대소문자 변형(`Hook`·`MCP`)과 접두·접미 변형(`hook:pre`·`mcp.call`·`log_hook`)도 같은 이름으로 본다. */
export function isForbiddenName(literal: string, names: readonly string[] = FORBIDDEN): boolean {
  const lower = literal.toLowerCase();
  return names.some((n) => lower === n || new RegExp(`^${n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}[:._/-]`).test(lower) || new RegExp(`[:._/-]${n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`).test(lower));
}
const BUILTIN_KINDS = ["metric", "bar", "line", "table"];

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}
const SRC = join(__dirname, "..", "src");
const files = walk(SRC).filter((f) => /\.(ts|tsx)$/.test(f) && !/\.test\./.test(f));

/** 따옴표 문자열 리터럴만 본다(주석·식별자 제외). */
function literals(source: string): string[] {
  const text = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
  const out: string[] = [];
  for (const m of text.matchAll(/(["'`])((?:\\.|(?!\1)[^\\\n])*)\1/g)) out.push(m[2] as string);
  return out;
}

describe("noHardcoding", () => {
  it("검사기 자신: 변형을 잡고 정상 문구는 통과시킨다", () => {
    for (const bad of ["hook", "Hook", "MCP", "hook:pre", "mcp.call", "log_hook", "claude-code", "Tool_Use", "tokens.total"]) expect(isForbiddenName(bad)).toBe(true);
    for (const ok of ["hooked", "mcpx", "daytime", "hours", "", "a b hook c", "events"]) expect(isForbiddenName(ok)).toBe(false);
  });
  it("검사 대상이 있다", () => expect(files.length).toBeGreaterThan(10));
  it.each(files.map((f) => [f.slice(SRC.length + 1), f] as const))("%s에 출처·범주·차원·지표 이름 리터럴이 없다", (_n, file) => {
    // 문구(messages.ts)는 한글 표시 문구이므로 id가 아닌 문장 단위로만 비교한다: 정확히 같은 문자열만 금지.
    const lits = literals(readFileSync(file, "utf8"));
    const hits = lits.filter((l) => isForbiddenName(l));
    expect(hits).toEqual([]);
  });
  it("내장 위젯 종류 이름은 builtins.tsx에만 있다", () => {
    // layout.ts·registry.ts의 "metric"은 계약 `query`의 필드 이름(알려진 키·타입 키)이지 위젯 종류가 아니다.
    for (const f of files.filter((x) => !x.endsWith("builtins.tsx"))) {
      const hits = literals(readFileSync(f, "utf8")).filter((l) => BUILTIN_KINDS.includes(l) && !(/(layout\.ts|registry\.ts)$/.test(f) && l === "metric"));
      expect({ file: f, hits }).toEqual({ file: f, hits: [] });
    }
  });
  it("위젯 레지스트리 목록에 switch가 없다", () => {
    const text = readFileSync(join(SRC, "widgets", "registry.ts"), "utf8") + readFileSync(join(SRC, "DashboardGrid.tsx"), "utf8");
    expect(text).not.toMatch(/switch\s*\(\s*[\w.]*kind/);
  });
  it("다른 사내 UI 패키지를 import하지 않는다(contracts 타입만)", () => {
    for (const f of files) {
      const imports = [...readFileSync(f, "utf8").matchAll(/from\s+["'](@agent-console\/[^"']+)["']/g)].map((m) => m[1] as string);
      for (const i of imports) expect(i.startsWith("@agent-console/contracts")).toBe(true);
    }
  });
});
