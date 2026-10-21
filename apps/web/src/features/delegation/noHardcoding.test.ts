import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = resolve(__dirname, "../..");
const PKGS = resolve(SRC, "../../../packages/ts/lib");

function files(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist" || name === "testing") continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) files(p, out);
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name) && !/\.generated\./.test(name)) out.push(p);
  }
  return out;
}

/** 계약이 고정한 이벤트 타입 문자열(screen-delegation 0.1 예외): 이벤트 매핑 표 한 파일만 쓴다. */
const EVENT_TYPES = ["loop.iteration", "loop.exhausted", "run.child_started", "run.child_finished"];
const MAP_FILE = join("features", "delegation", "eventSummaryMap.ts");

describe("이벤트 타입 문자열은 매핑 표 한 파일에만 있다", () => {
  it("앱 소스(매핑 표 제외)에 반복·자식 실행 이벤트 타입 문자열이 없다", () => {
    const hits: string[] = [];
    for (const f of files(SRC)) {
      if (relative(SRC, f) === MAP_FILE) continue;
      const text = readFileSync(f, "utf8");
      for (const type of EVENT_TYPES) if (new RegExp(`["'\`]${type.replace(".", "\\.")}["'\`]`).test(text)) hits.push(`${relative(SRC, f)}: ${type}`);
    }
    expect(hits).toEqual([]);
  });
  it("패키지(graph-editor·trace-view·chat) 소스에는 이벤트 타입도 payload 키도 없다", () => {
    const hits: string[] = [];
    for (const pkg of ["graph-editor", "trace-view", "chat"]) {
      for (const f of files(join(PKGS, pkg, "src"))) {
        const text = readFileSync(f, "utf8");
        for (const type of EVENT_TYPES) if (text.includes(type)) hits.push(`${pkg}/${relative(join(PKGS, pkg, "src"), f)}: ${type}`);
        if (/["'`](max_iterations|team_ref|conditions)["'`]/.test(text)) hits.push(`${pkg}/${relative(join(PKGS, pkg, "src"), f)}: config key`);
      }
    }
    expect(hits).toEqual([]);
  });
  it("검사 대상이 있다", () => {
    expect(files(SRC).length).toBeGreaterThan(50);
    expect(files(join(PKGS, "graph-editor", "src")).length).toBeGreaterThan(10);
  });
});
