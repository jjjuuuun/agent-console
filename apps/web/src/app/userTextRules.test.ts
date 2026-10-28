import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import ts from "typescript";
import { describe, expect, it, vi } from "vitest";
import { USER_TEXT_RULES } from "@agent-console/contracts/constants";

/**
 * 사용자에게 보이는 문구에 설계 번호·내부 노드 id를 넣지 않는다(UX-F9, ux-overhaul D13).
 * 금지 패턴은 `USER_TEXT_RULES`(서버 계약의 데이터 하나) scope `messages`를 그대로 쓴다.
 * 웹 앱과 TS 라이브러리 소스의 문자열 리터럴·템플릿 조각만 검사한다(주석·테스트 파일 제외).
 */

// 수백 파일 파싱이라 미러 단독 실행에서도 15초가 걸린다(파싱 범위를 줄이면 검사 의미가 줄어 시간 제한만 늘린다).
vi.setConfig({ testTimeout: 40_000 });

const ROOT = resolve(__dirname, "../../../..");
const SCAN_DIRS = [join(ROOT, "apps/web/src"), ...readdirSync(join(ROOT, "packages/ts/lib")).map((d) => join(ROOT, "packages/ts/lib", d, "src"))];
const SKIP = /(\.test\.tsx?|\.d\.ts)$|[\\/](generated|testing|node_modules|dist)[\\/]/;

function sources(dir: string): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return [];
  }
  return entries.flatMap((name) => {
    const full = join(dir, name);
    if (SKIP.test(full)) return [];
    if (statSync(full).isDirectory()) return sources(full);
    return /\.tsx?$/.test(name) ? [full] : [];
  });
}

// 부모 포인터(setParentNodes)가 필요 없어 끈다: 수백 파일을 한 테스트에서 파싱하므로 느린 파일시스템·부하에서 5초 기본 시간을 넘기던 원인(공개본 CI).
function literals(file: string): string[] {
  const sf = ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, false, file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const out: string[] = [];
  const visit = (n: ts.Node) => {
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n) || ts.isJsxText(n)) out.push(n.text);
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return out;
}

const rules = USER_TEXT_RULES.patterns
  .filter((p) => (p.scopes as readonly string[]).includes("messages"))
  .map((p) => ({ id: p.id, re: new RegExp(p.pattern) }));
const files = SCAN_DIRS.flatMap(sources);

describe("사용자 문구 금지 패턴(USER_TEXT_RULES, scope messages)", () => {
  it("규칙과 검사 대상이 있다", () => {
    expect(rules.length).toBeGreaterThan(0);
    expect(files.length).toBeGreaterThan(50);
  });
  it("웹 앱·TS 라이브러리 문자열에 설계 번호·내부 노드 id가 없다", () => {
    const hits = files.flatMap((f) => literals(f).flatMap((s) => rules.filter((r) => r.re.test(s)).map((r) => `${relative(ROOT, f)} [${r.id}] ${s.slice(0, 80)}`)));
    expect(hits).toEqual([]);
  });
  it("규칙이 실제 위반 문구를 잡는다", () => {
    expect(rules.some((r) => r.re.test("design §5R.6"))).toBe(true);
    expect(rules.some((r) => r.re.test("노드 'n3'에서"))).toBe(true);
  });
});
