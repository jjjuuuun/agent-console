import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { PROJECT_CONTEXT_RETIRED_TERMS, RETIRED_TERMS } from "@agent-console/projects";

/**
 * 화면 문구 폐기어 검사(U-16): 웹 앱의 모든 메시지 표(`*messages*.ts`)의 문자열에 `RETIRED_TERMS`가 없다.
 * `PROJECT_CONTEXT_RETIRED_TERMS`("사용 중"·"빼기" 등)는 다른 기능에서 일반 뜻으로 쓰이므로 프로젝트 기능 폴더의 표에만 적용한다.
 * 목록은 `@agent-console/projects`의 데이터이고, 표 파일이 늘면 검사 대상도 자동으로 는다. 주석은 보지 않는다.
 */

const SRC = resolve(__dirname, "..");
const PROJECT_DIR = join(SRC, "features", "projects") + sep;
const SKIP = /(\.test\.tsx?|\.d\.ts)$|[\\/](generated|node_modules|dist)[\\/]/;

function messageTables(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (SKIP.test(full)) return [];
    if (statSync(full).isDirectory()) return messageTables(full);
    return /messages\.ts$/i.test(name) ? [full] : [];
  });
}

function literals(file: string): string[] {
  const sf = ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, false, ts.ScriptKind.TS);
  const out: string[] = [];
  const visit = (n: ts.Node) => {
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n)) out.push(n.text);
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return out;
}

/** 파일 하나에 적용할 폐기어. 프로젝트 기능 폴더면 전부, 아니면 프로젝트 맥락 말을 뺀다. */
function termsFor(file: string): readonly string[] {
  return file.startsWith(PROJECT_DIR) ? RETIRED_TERMS : RETIRED_TERMS.filter((t) => !PROJECT_CONTEXT_RETIRED_TERMS.includes(t));
}

function hitsIn(file: string, strings: readonly string[]): string[] {
  const terms = termsFor(file);
  return strings.flatMap((s) => terms.filter((t) => s.includes(t)).map((t) => `${relative(SRC, file).replaceAll("\\", "/")} [${t}] ${s.slice(0, 80)}`));
}

const files = messageTables(SRC);

describe("앱 메시지 표에 폐기어(U-16)가 없다", () => {
  it("검사 대상과 목록이 있다", () => {
    expect(RETIRED_TERMS.length).toBeGreaterThan(0);
    expect(files.some((f) => f.startsWith(PROJECT_DIR))).toBe(true);
    expect(files.some((f) => !f.startsWith(PROJECT_DIR))).toBe(true);
  });
  it("모든 메시지 표 문자열", () => {
    expect(files.flatMap((f) => hitsIn(f, literals(f)))).toEqual([]);
  });
  it("폐기어를 넣으면 잡고, 프로젝트 맥락 말은 프로젝트 기능 표에서만 잡는다", () => {
    const general = RETIRED_TERMS.find((t) => !PROJECT_CONTEXT_RETIRED_TERMS.includes(t));
    const contextual = PROJECT_CONTEXT_RETIRED_TERMS[0];
    expect(general).toBeDefined();
    expect(contextual).toBeDefined();
    const other = join(SRC, "features", "logs", "messages.ts");
    const project = join(PROJECT_DIR, "messages.ts");
    expect(hitsIn(other, [`${general} 열기`])).toHaveLength(1);
    expect(hitsIn(other, [`${contextual}`])).toEqual([]);
    expect(hitsIn(project, [`${contextual}`])).toHaveLength(1);
  });
});
