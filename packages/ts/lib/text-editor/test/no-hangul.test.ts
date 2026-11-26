import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

// 이 패키지는 화면 문구를 호출자에게서 받거나 기본이 영어다(I.9a). 소스 문자열에 한글이 없음을 지킨다.
const HANGUL = /[ᄀ-ᇿ㄰-㆏가-힣]/;

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

/** 문자열·템플릿·JSX 텍스트의 한글(주석 제외)을 찾는다(I.11 검사의 패키지 단위 판). */
function hangulLiterals(file: string): string[] {
  const source = ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true, file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const hits: string[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isJsxText(node) || ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) {
      if (HANGUL.test(node.text)) hits.push(node.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return hits;
}

describe("컴포넌트 소스에 한글 문자열이 없다", () => {
  const SRC = join(__dirname, "..", "src");
  const files = walk(SRC).filter((f) => /\.(ts|tsx)$/.test(f) && !/\.test\./.test(f));
  it("검사 대상이 있다", () => expect(files.length).toBeGreaterThan(0));
  it.each(files.map((f) => [f.slice(SRC.length + 1), f] as const))("%s", (_n, file) => {
    expect(hangulLiterals(file)).toEqual([]);
  });
});
