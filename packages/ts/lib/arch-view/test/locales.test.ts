import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import en from "../src/locales/en.json";
import ko from "../src/locales/ko.json";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ArchitectureLegend, defaultMessages, formatMessage } from "../src";
import enExport from "../src/locales/en";
import koExport from "../src/locales/ko";

/** 값(문자열)까지 내려가 `경로 -> 문자열` 표로 편다. 배열은 쓰지 않는다. */
function flatten(value: unknown, prefix = ""): Record<string, string> {
  if (typeof value === "string") return { [prefix]: value };
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error(`문구 묶음에는 문자열과 객체만 둔다: ${prefix}`);
  return Object.assign({}, ...Object.entries(value).map(([k, v]) => flatten(v, prefix ? `${prefix}.${k}` : k)));
}

/** 자리표시자 이름 집합(`{name}`, 조사 서식 `{name|으로/로}`의 이름만). */
function placeholders(text: string): string[] {
  return [...new Set([...text.matchAll(/\{(\w+)(?:\|[^{}|]+)?\}/g)].map((m) => m[1] as string))].sort();
}

const HANGUL = /[ᄀ-ᇿ㄰-㆏가-힣]/;
const koFlat = flatten(ko);
const enFlat = flatten(en);

describe("문구 묶음 ko·en", () => {
  it("ko와 en의 키 집합이 같다", () => {
    expect(Object.keys(enFlat).sort()).toEqual(Object.keys(koFlat).sort());
  });
  it("같은 키의 자리표시자 집합이 같다", () => {
    const diff = Object.keys(koFlat).filter((k) => placeholders(koFlat[k] as string).join() !== placeholders(enFlat[k] as string).join());
    expect(diff).toEqual([]);
  });
  it("en 값에는 한글이 없고 조사 서식도 없다", () => {
    expect(Object.entries(enFlat).filter(([, v]) => HANGUL.test(v) || /\{\w+\|/.test(v)).map(([k]) => k)).toEqual([]);
  });
  it("빈 문구가 없다(값 없음 표시 같은 의도된 한 글자는 허용)", () => {
    expect(Object.entries(enFlat).filter(([, v]) => v.length === 0).map(([k]) => k)).toEqual([]);
  });
  it("defaultMessages는 ko 그대로이고 locales 내보내기가 같은 값이다", () => {
    expect(defaultMessages).toEqual(ko);
    expect(koExport).toEqual(ko);
    expect(enExport).toEqual(en);
  });
  it("조사 서식은 ko에서만 쓴다(en은 값만 채운다)", () => {
    expect(formatMessage(ko.ariaEdgeFlow, { from: "A", to: "Hook" })).toBe("A에서 Hook으로");
    expect(formatMessage(enExport.ariaEdgeFlow, { from: "A", to: "Hook" })).toBe("From A to Hook");
  });
  it("messages={en}을 넘기면 영어로 그려진다", () => {
    const html = renderToStaticMarkup(createElement(ArchitectureLegend, { messages: enExport }));
    expect(html).toContain("Request or call");
  });
});

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
  const files = walk(SRC).filter((f) => /\.(ts|tsx)$/.test(f) && !/\.test\./.test(f) && !/(fixtures|testing)\.ts$/.test(f));
  it("검사 대상이 있다", () => expect(files.length).toBeGreaterThan(3));
  it.each(files.map((f) => [f.slice(SRC.length + 1), f] as const))("%s", (_n, file) => {
    expect(hangulLiterals(file)).toEqual([]);
  });
});
