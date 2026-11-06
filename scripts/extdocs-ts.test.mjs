import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { entryFile, main, parseSymbol, run } from "./extdocs-ts.mjs";

const schemaPath = join(dirname(fileURLToPath(import.meta.url)), "extdocs/declaration.schema.json");
let root;
const write = (rel, text) => {
  mkdirSync(dirname(join(root, rel)), { recursive: true });
  writeFileSync(join(root, rel), typeof text === "string" ? text : JSON.stringify(text));
};
const point = (extra = {}) => ({
  title: "위젯", area: "web", summary: "요약",
  registration: { kind: "props", export: "@t/lib#Widgets" },
  interface: ["@t/lib#Widget"],
  ...extra,
});
const lib = (points) => {
  write("packages/ts/lib/lib/package.json", {
    name: "@t/lib",
    exports: { ".": { development: "./src/index.ts", default: "./dist/index.js" } },
    ...(points ? { agentConsole: { kind: "lib", extensionPoints: points } } : {}),
  });
  write("packages/ts/lib/lib/src/index.ts", 'export * from "./widgets";\nexport type Widget = { id: string };\n');
  write("packages/ts/lib/lib/src/widgets.ts", "export const Widgets = [];\n");
};
const go = () => run({ root, configPath: join(root, "extdocs.yaml"), schemaPath });

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "extdocs-ts-"));
  write("extdocs.yaml", "ts_package_globs:\n  - packages/ts/*/*\n  - apps/web\nts_table: agentConsole\n");
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("extdocs-ts", () => {
  it("선언 없는 패키지는 통과한다", () => {
    lib(null);
    expect(go()).toEqual({ declarations: [], findings: [] });
  });

  it("export 되는 기호(재수출·타입 포함)는 통과한다", () => {
    lib({ "dash-widget": point() });
    const r = go();
    expect(r.findings).toEqual([]);
    expect(r.declarations).toEqual([{ slug: "dash-widget", package: "@t/lib", file: "packages/ts/lib/lib/package.json" }]);
  });

  it("없는 export는 실패한다", () => {
    lib({ "dash-widget": point({ interface: ["@t/lib#Nope"] }) });
    const f = go().findings;
    expect(f).toHaveLength(1);
    expect(f[0]).toMatchObject({ code: "symbol-missing" });
    expect(f[0].where).toContain("dash-widget.interface");
  });

  it("형식 오류는 실패한다", () => {
    lib({ "Bad Slug": point(), ok: { title: "x" } });
    const codes = go().findings.map((f) => f.code);
    expect(codes.every((c) => c === "schema-invalid")).toBe(true);
    expect(codes.length).toBeGreaterThanOrEqual(2);
  });

  it("기호 형식·없는 패키지·진입 파일 없음을 구분한다", () => {
    lib({ a: point({ interface: ["noHash"] }), b: point({ interface: ["@x/other#Y"] }) });
    expect(go().findings.map((f) => f.code).sort()).toEqual(["package-unknown", "symbol-malformed"]);
  });

  it("앱은 파일 경로가 든 기호로 그 파일을 본다", () => {
    lib(null);
    write("apps/web/package.json", {
      name: "@t/web",
      agentConsole: { extensionPoints: { routes: point({ registration: { kind: "props", export: "@t/web/src/routes.tsx#routes" }, interface: [] }) } },
    });
    write("apps/web/src/routes.tsx", "export const routes = [];\n");
    expect(go().findings).toEqual([]);
    write("apps/web/src/routes.tsx", "export const other = [];\n");
    expect(go().findings.map((f) => f.code)).toEqual(["symbol-missing"]);
  });

  it("parseSymbol·entryFile", () => {
    expect(parseSymbol("@a/b/src/x.tsx#N")).toEqual({ pkg: "@a/b", subpath: "src/x.tsx", name: "N" });
    expect(parseSymbol("pkg#N")).toEqual({ pkg: "pkg", subpath: null, name: "N" });
    expect(parseSymbol("@a/b#")).toBeNull();
    lib(null);
    expect(entryFile(join(root, "packages/ts/lib/lib"), { exports: { ".": { development: "./src/index.ts" } } })).toMatch(/src\/index\.ts$/);
  });

  it("main: 오류면 1, 통과면 0 종료 코드", () => {
    lib({ x: point({ interface: ["@t/lib#Nope"] }) });
    const log = console.log;
    console.log = () => {};
    try {
      const args = ["--root", root, "--config", join(root, "extdocs.yaml"), "--schema", schemaPath];
      expect(main(args)).toBe(1);
      lib({ x: point() });
      expect(main([...args, "--json"])).toBe(0);
    } finally {
      console.log = log;
    }
  });
});
