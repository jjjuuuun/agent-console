import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { assertCatalogsMatch } from "@agent-console/i18n/testing";
import type { MessageTree } from "@agent-console/i18n";
import pendingData from "../testing/i18nPending.json";
import { findHangulLiterals } from "../testing/hangulLiterals";
import { listScreenSources, matchesEntry, pendingTotals, scanHangul, type I18nPendingData } from "../testing/i18nScan";
import { DATA_NAMES, dataNameLiteral, isAllowedVariant } from "../testing/dataNames";

/**
 * I.11 — design §I18N.10 W1(코드 안 한글 0), W2(ko·en 묶음 짝), W3(묶음에 서버 데이터 이름 없음).
 * 아직 옮기지 않은 폴더는 `testing/i18nPending.json`에 두고 I.12가 하나씩 지운다(I.15에서 빈 목록).
 */

const REPO = resolve(__dirname, "../../../..");
const data = pendingData as I18nPendingData;
const APP_SRC = join(REPO, "apps/web/src");
const LIB_DIR = join(REPO, "packages/ts/lib");
const libSrcRoots = readdirSync(LIB_DIR).map((n) => join(LIB_DIR, n, "src")).filter((p) => existsDir(p));

function existsDir(p: string): boolean {
  try {
    return readdirSync(p).length >= 0;
  } catch {
    return false;
  }
}

const files = [APP_SRC, ...libSrcRoots].flatMap((root) => listScreenSources(root, REPO));
const report = scanHangul(files, REPO, data);
/** 소스 전체를 훑는 테스트의 시간 한도(부하가 있으면 기본 5초를 넘는다). */
const SCAN_TIMEOUT = 60_000;

describe("W1 findHangulLiterals(가짜 소스)", () => {
  it("문자열·템플릿·JSX 텍스트의 한글을 잡는다", () => {
    expect(findHangulLiterals("a.ts", `const a = "안녕"; const b = \`값 \${x}\`; const c = 'ok';`)).toHaveLength(2);
    expect(findHangulLiterals("a.tsx", `const A = () => <p title="x">저장</p>;`)).toHaveLength(1);
    expect(findHangulLiterals("a.ts", "const t = `a${1}한글`;")).toHaveLength(1);
  });
  it("주석과 영어 문자열은 통과한다", () => {
    expect(findHangulLiterals("a.ts", `// 한글 주석\n/** 한글 문서 */\nconst a = "ok";`)).toEqual([]);
  });
});

describe("W1 scanHangul(가짜 저장소)", () => {
  const dir = mkdtempSync(join(tmpdir(), "i18n-scan-"));
  mkdirSync(join(dir, "src/old"), { recursive: true });
  mkdirSync(join(dir, "src/new"), { recursive: true });
  writeFileSync(join(dir, "src/old/a.ts"), `export const a = "옛 문구";`);
  writeFileSync(join(dir, "src/new/b.ts"), `export const b = "새 문구";`);
  writeFileSync(join(dir, "src/new/c.ts"), `export const c = "English";`);
  writeFileSync(join(dir, "src/new/c.test.ts"), `export const t = "테스트는 제외";`);
  const fake: I18nPendingData = { exempt: [], pending: { x: ["src/old/", "src/gone/"] } };
  const found = listScreenSources(join(dir, "src"), dir);
  it("테스트 파일을 빼고 목록을 만든다", () => expect(found).toEqual(["src/new/b.ts", "src/new/c.ts", "src/old/a.ts"]));
  it("허용 목록 밖의 한글은 걸리고, 든 것은 수로 센다", () => {
    const r = scanHangul(found, dir, fake);
    expect(Object.keys(r.unexpected)).toEqual(["src/new/b.ts"]);
    expect(r.allowedCounts).toEqual({ "src/old/": 1, "src/gone/": 0 });
    expect(pendingTotals(fake, r.allowedCounts)).toEqual({ x: 1 });
  });
  it("폴더를 허용 목록에서 빼면 그 폴더의 한글이 걸린다", () => {
    expect(Object.keys(scanHangul(found, dir, { exempt: [], pending: {} }).unexpected)).toContain("src/old/a.ts");
  });
  it("항목 일치: 폴더는 접두, 파일은 정확히", () => {
    expect(matchesEntry("a/b/c.ts", "a/b/")).toBe(true);
    expect(matchesEntry("a/bc.ts", "a/b/")).toBe(false);
    expect(matchesEntry("a/b.ts", "a/b.ts")).toBe(true);
    expect(matchesEntry("a/b.tsx", "a/b.ts")).toBe(false);
    rmSync(dir, { recursive: true, force: true });
  });
});

describe("W1 앱·TS 라이브러리 소스에 한글 문자열이 없다(허용 목록 제외)", () => {
  it("검사 대상이 있다(앱 + 라이브러리)", () => {
    expect(files.some((f) => f.startsWith("apps/web/src/"))).toBe(true);
    expect(files.some((f) => f.startsWith("packages/ts/lib/chat/src/"))).toBe(true);
  });
  it("허용 목록 밖에 한글 문자열이 없다", () => {
    expect(report.unexpected).toEqual({});
  }, SCAN_TIMEOUT);
  it("허용 목록 항목마다 한글 문자열이 남아 있다(다 옮겼으면 항목을 지운다)", () => {
    expect(Object.entries(report.allowedCounts).filter(([, n]) => n === 0).map(([p]) => p)).toEqual([]);
  });
  it("exempt 항목마다 이유가 있다", () => {
    expect(data.exempt.filter((e) => e.reason.trim() === "")).toEqual([]);
  });
  it("묶음별 남은 한글 문자열 수를 보고한다(I.12 분량)", () => {
    const totals = pendingTotals(data, report.allowedCounts);
    console.info(`i18n pending: ${JSON.stringify(totals)}\n${Object.entries(report.allowedCounts).map(([p, n]) => `  ${p.replace("apps/web/src/", "")} ${n}`).join("\n")}`);
    expect(Object.keys(totals)).toEqual(Object.keys(data.pending));
  });
});

// ── W2: 앱 묶음 ko·en 짝(키·자리표시자, 영어에 조사 서식 없음) — 라이브러리 묶음은 각 패키지 test/locales.test.ts가 같은 검사를 한다.
const LOCALES = join(APP_SRC, "locales");
const readBundle = (lang: string, ns: string) => JSON.parse(readFileSync(join(LOCALES, lang, `${ns}.json`), "utf8")) as MessageTree;
const namespaces = readdirSync(join(LOCALES, "ko")).map((f) => f.replace(/\.json$/, ""));

describe("W2 앱 묶음 ko·en 짝", () => {
  it.each(namespaces)("%s: 키·자리표시자가 같고 영어에 particle.* 서식이 없다", (ns) => {
    assertCatalogsMatch(readBundle("ko", ns), readBundle("en", ns));
  });
  it("영어 묶음에는 한글이 없다", () => {
    for (const ns of namespaces) expect(findHangulInJson(readBundle("en", ns)), ns).toEqual([]);
  });
});

function leaves(tree: unknown, prefix = ""): [string, string][] {
  if (typeof tree === "string") return [[prefix, tree]];
  if (typeof tree !== "object" || tree === null) return [];
  return Object.entries(tree).flatMap(([k, v]) => leaves(v, prefix ? `${prefix}.${k}` : k));
}
function findHangulInJson(tree: unknown): string[] {
  return leaves(tree).filter(([, v]) => /[ᄀ-ᇿ㄰-㆏가-힣]/.test(v)).map(([k]) => k);
}

// ── W3: 묶음 문자열이 서버 데이터 이름(연결 종류·리소스 종류 등)을 값으로 쓰지 않는다(옛 messagesNoHardcoding·featureMessagesNoHardcoding을 JSON 묶음으로).
describe("W3 묶음 값에 서버 데이터 이름이 없다", () => {
  const bundles: [string, [string, string][]][] = [];
  for (const lang of readdirSync(LOCALES)) {
    for (const f of readdirSync(join(LOCALES, lang))) bundles.push([`apps/web/src/locales/${lang}/${f}`, leaves(readBundle(lang, f.replace(/\.json$/, "")))]);
  }
  for (const lib of readdirSync(LIB_DIR)) {
    for (const lang of ["ko", "en"]) {
      const path = join(LIB_DIR, lib, "src/locales", `${lang}.json`);
      try {
        bundles.push([`packages/ts/lib/${lib}/src/locales/${lang}.json`, leaves(JSON.parse(readFileSync(path, "utf8")))]);
      } catch {
        /* 문구 묶음이 없는 라이브러리 */
      }
    }
  }
  it("검사 대상이 있다", () => expect(bundles.length).toBeGreaterThan(2));
  it.each(bundles)("%s", (rel, entries) => {
    const hits = entries.flatMap(([key, value]) => DATA_NAMES.filter((n) => dataNameLiteral(n).test(JSON.stringify(value)) && !isAllowedVariant(rel, value)).map((n) => `${key} = ${value} (${n})`));
    expect(hits).toEqual([]);
  });
});

// ── 쓰지 않는 키 보고(앱 묶음): 실패하지 않고 목록만 남긴다. 동적 키(`prefix.${x}`)는 `prefix.${`가 소스에 있으면 쓴 것으로 본다.
export function unusedKeys(tree: MessageTree, sourceText: string): string[] {
  return leaves(tree)
    .map(([k]) => k)
    .filter((k) => {
      const parts = k.replace(/_(zero|one|two|few|many|other)$/, "").split(".");
      for (let i = parts.length; i >= 1; i--) {
        const path = parts.slice(0, i).join(".");
        if (sourceText.includes(i === parts.length ? path : `${path}.${"$"}{`)) return false;
      }
      return true;
    });
}

describe("쓰지 않는 키 보고", () => {
  let text = "";
  beforeAll(() => {
    text = files.filter((f) => f.startsWith("apps/web/src/")).map((f) => readFileSync(join(REPO, f), "utf8")).join("\n");
  }, SCAN_TIMEOUT);
  it("전체 경로나 동적 접두가 소스에 없으면 쓰지 않는 키", () => {
    const tree = { a: { b: "x", c: "y" }, d: "z" };
    expect(unusedKeys(tree, `t("a.b") t("d")`)).toEqual(["a.c"]);
    expect(unusedKeys(tree, "t(`a.${k}`) t(\"d\")")).toEqual([]);
  });
  it("앱 묶음의 쓰지 않는 키를 보고한다(실패 아님)", () => {
    const unused = namespaces.flatMap((ns) => unusedKeys(readBundle("ko", ns), text).map((k) => `${ns}:${k}`));
    if (unused.length) console.info(`i18n unused keys (${unused.length}): ${unused.slice(0, 20).join(", ")}`);
    expect(Array.isArray(unused)).toBe(true);
  }, SCAN_TIMEOUT);
});
