import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { DEFAULT_DEV_VERSIONS, NewPackageArgsError, buildPackageFiles, devVersionsFromRoot, loadLayers, makeVars, parseNewPackageArgs, splitName } from "./scaffold.mjs";

const TEMPLATES = join(dirname(fileURLToPath(import.meta.url)), "..", "templates", "ts");

describe("parseNewPackageArgs", () => {
  it("종류·이름·옵션을 읽는다", () => {
    expect(parseNewPackageArgs(["--kind", "lib", "--dom", "--scope", "@acme", "foo"])).toMatchObject({ kind: "lib", name: "foo", scope: "@acme", dom: true });
  });
  it.each([[["foo"]], [["--kind", "x", "foo"]], [["--kind", "lib"]], [["--kind", "lib", "a", "b"]], [["--kind", "lib", "--zz", "a"]], [["--kind"]]])("잘못된 인자 %j", (argv) => {
    expect(() => parseNewPackageArgs(argv)).toThrow(NewPackageArgsError);
  });
  it("--help는 다른 검사를 건너뛴다", () => {
    expect(parseNewPackageArgs(["-h"]).help).toBe(true);
  });
});

describe("splitName", () => {
  it("scope를 붙이거나 그대로 둔다", () => {
    expect(splitName("foo", "@agent-console")).toEqual({ full: "@agent-console/foo", scope: "@agent-console", short: "foo" });
    expect(splitName("@acme/bar", "@agent-console")).toEqual({ full: "@acme/bar", scope: "@acme", short: "bar" });
  });
  it("잘못된 이름", () => {
    expect(() => splitName("Foo", "@a")).toThrow(NewPackageArgsError);
    expect(() => splitName("../x", "@a")).toThrow(NewPackageArgsError);
  });
});

describe("makeVars / devVersionsFromRoot", () => {
  it("scope에서 설정 패키지 이름을 만든다", () => {
    expect(makeVars({ name: "@acme/x", scope: "@acme", kind: "lib" })).toMatchObject({ eslintConfigName: "@acme/eslint-config", tsconfigName: "@acme/tsconfig", inhouseRange: "^0.1.0", entry: "src/index.ts" });
  });
  it("루트 devDependencies가 기본값을 덮어쓴다", () => {
    const v = devVersionsFromRoot({ devDependencies: { vitest: "^9.0.0" } });
    expect(v.vitest).toBe("^9.0.0");
    expect(v.typescript).toBe(DEFAULT_DEV_VERSIONS.typescript);
    expect(devVersionsFromRoot(null)).toEqual(DEFAULT_DEV_VERSIONS);
  });
});

describe("buildPackageFiles", () => {
  const vars = (kind, name, dom) => makeVars({ name, scope: "@agent-console", kind, year: 2026, dom });
  it("lib: 조건부 exports·빌드 스크립트·사내 의존 범위", () => {
    const files = buildPackageFiles(loadLayers(TEMPLATES, "lib"), vars("lib", "@agent-console/demo"));
    const pkg = JSON.parse(files["package.json"]);
    expect(pkg).toMatchObject({ version: "0.1.0", private: true, type: "module", exports: { ".": { development: "./src/index.ts", default: "./dist/index.js" } } });
    expect(Object.keys(pkg.scripts)).toEqual(["build", "typecheck", "lint", "test"]);
    expect(pkg.devDependencies["@agent-console/tsconfig"]).toBe("^0.1.0");
    expect(JSON.parse(files["tsconfig.json"]).extends).toBe("@agent-console/tsconfig/library.json");
    expect(Object.keys(files)).not.toContain("package.patch.json");
    expect(Object.keys(files).some((f) => f.endsWith(".tmpl"))).toBe(false);
  });
  it("dom이면 happy-dom을 쓴다", () => {
    const files = buildPackageFiles(loadLayers(TEMPLATES, "lib"), vars("lib", "@agent-console/demo", true), { dom: true });
    expect(files["vitest.config.ts"]).toContain('"happy-dom"');
    expect(JSON.parse(files["package.json"]).devDependencies["happy-dom"]).toBeTruthy();
  });
  it("eslint-config 초안은 자기 자신을 개발 의존으로 갖지 않는다", () => {
    const files = buildPackageFiles(loadLayers(TEMPLATES, "config", "eslint-config"), vars("config", "@agent-console/eslint-config"));
    const pkg = JSON.parse(files["package.json"]);
    expect(pkg.devDependencies).not.toHaveProperty("@agent-console/eslint-config");
    expect(pkg.exports).toHaveProperty("./react");
    expect(files["eslint.config.js"]).toContain('"./index.js"');
  });
  it("tsconfig 초안은 base·library를 싣는다", () => {
    const files = buildPackageFiles(loadLayers(TEMPLATES, "config", "tsconfig"), vars("config", "@agent-console/tsconfig"));
    expect(Object.keys(files)).toEqual(expect.arrayContaining(["base.json", "library.json"]));
    expect(JSON.parse(files["package.json"]).description).toContain("tsconfig");
  });
  it("없는 초안은 오류", () => {
    expect(() => loadLayers(TEMPLATES, "lib", "nope")).toThrow(NewPackageArgsError);
    expect(() => loadLayers(TEMPLATES, "lib", "../x")).toThrow(NewPackageArgsError);
  });
});
