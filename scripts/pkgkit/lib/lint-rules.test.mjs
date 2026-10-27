import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { escapesPackage, extractSpecifiers, formatViolations, lintTsPackage, packageNameOf } from "./lint-rules.mjs";
import { buildPackageFiles, loadLayers, makeVars } from "./scaffold.mjs";

const TEMPLATES = join(dirname(fileURLToPath(import.meta.url)), "..", "templates", "ts");
const make = (kind, name, dom = false) =>
  buildPackageFiles(loadLayers(TEMPLATES, kind), makeVars({ name, scope: "@agent-console", kind, year: 2026, dom }), { dom });
const rules = (violations) => [...new Set(violations.map((v) => v.rule))].sort();

describe("템플릿 산출물은 pkg-lint를 통과한다", () => {
  it.each([
    ["lib", "@agent-console/demo"],
    ["lib", "@agent-console/demo-dom", true],
    ["config", "@agent-console/demo-config"],
  ])("%s %s", (kind, name, dom) => {
    expect(lintTsPackage({ kind, files: make(kind, name, dom) })).toEqual([]);
  });
});

describe("규칙", () => {
  const base = () => make("lib", "@agent-console/demo");
  const withPkg = (patch) => {
    const files = base();
    files["package.json"] = JSON.stringify({ ...JSON.parse(files["package.json"]), ...patch });
    return files;
  };

  it("필수 파일 누락", () => {
    const files = base();
    delete files["CHANGELOG.md"];
    expect(lintTsPackage({ kind: "lib", files })).toMatchObject([{ rule: "required-file", file: "CHANGELOG.md" }]);
  });

  it("workspace: 문법과 사내 의존 범위", () => {
    const v = lintTsPackage({ kind: "lib", files: withPkg({ dependencies: { "@agent-console/a": "workspace:*", "@agent-console/b": "*", "@agent-console/c": "^0.4.0", react: "workspace:^" } }) });
    expect(v.filter((x) => x.rule === "workspace-protocol")).toHaveLength(2);
    expect(v.filter((x) => x.rule === "inhouse-range")).toHaveLength(1);
  });

  it("상대 extends와 패키지 밖 경로", () => {
    const files = base();
    files["tsconfig.json"] = JSON.stringify({ extends: "../../../tsconfig.base.json", include: ["../shared"] });
    expect(rules(lintTsPackage({ kind: "lib", files }))).toEqual(["external-path", "tsconfig-extends"]);
  });

  it("같은 패키지 안을 가리키는 상대 extends는 허용", () => {
    const files = base();
    files["tsconfig.build.json"] = JSON.stringify({ extends: "./tsconfig.json" });
    expect(lintTsPackage({ kind: "lib", files })).toEqual([]);
  });

  it("exports: 소스 직접 노출·dist 없음·files 누락", () => {
    expect(rules(lintTsPackage({ kind: "lib", files: withPkg({ exports: { ".": "./src/index.ts" }, main: "./src/index.ts" }) }))).toEqual(["exports"]);
    expect(lintTsPackage({ kind: "lib", files: withPkg({ exports: { ".": { development: "./src/index.ts", default: "./src/index.ts" } } }) })).toMatchObject([{ rule: "exports", message: expect.stringContaining("default") }]);
    expect(lintTsPackage({ kind: "lib", files: withPkg({ files: ["src"] }) })).toMatchObject([{ rule: "exports" }]);
  });

  it("css 같은 비코드 자산은 문자열 export 허용", () => {
    const pkg = JSON.parse(base()["package.json"]);
    pkg.exports["./tokens.css"] = "./src/tokens.css";
    const files = { ...base(), "package.json": JSON.stringify(pkg) };
    expect(lintTsPackage({ kind: "lib", files })).toEqual([]);
  });

  it("스크립트 누락과 패키지 밖 경로", () => {
    const pkg = JSON.parse(base()["package.json"]);
    delete pkg.scripts.build;
    pkg.scripts.lint = "eslint ../..";
    const v = lintTsPackage({ kind: "lib", files: { ...base(), "package.json": JSON.stringify(pkg) } });
    expect(rules(v)).toEqual(["external-path", "scripts"]);
  });

  it("소스 import: 패키지 밖, 내부 직접 참조, 선언하지 않은 의존", () => {
    const files = base();
    files["src/bad.ts"] = [
      'import a from "../../other/src/x";',
      'import b from "@agent-console/contracts/src/index";',
      'import c from "left-pad";',
      'import d from "node:fs";',
      'import e from "vitest/config";',
      'import f from "./index";',
      'export * from "../index";',
    ].join("\n");
    const v = lintTsPackage({ kind: "lib", files });
    expect(v.map((x) => [x.rule, x.message.split(": ").pop().split(" ")[0]])).toEqual([
      ["escaping-import", "../../other/src/x"],
      ["deep-import", "@agent-console/contracts/src/index"],
      ["undeclared-dep", "@agent-console/contracts"],
      ["undeclared-dep", "left-pad"],
    ]);
  });

  it("@types/* 선언은 원래 이름의 선언으로 본다", () => {
    const files = withPkg({ devDependencies: { "@types/left-pad": "^1.0.0", "@agent-console/eslint-config": "^0.1.0", "@agent-console/tsconfig": "^0.1.0", typescript: "^6", vitest: "^5" } });
    files["src/a.ts"] = 'import x from "left-pad";';
    expect(lintTsPackage({ kind: "lib", files })).toEqual([]);
  });

  it("README 블록과 테스트가 다르면 알린다", () => {
    const files = base();
    files["test/readme.test.ts"] = files["test/readme.test.ts"].replace("describePackage();", "describePackage(1);");
    expect(lintTsPackage({ kind: "lib", files })).toMatchObject([{ rule: "readme-sync" }]);
  });

  it("깨진 package.json", () => {
    const files = base();
    files["package.json"] = "{";
    expect(lintTsPackage({ kind: "lib", files })[0]).toMatchObject({ rule: "package-json" });
  });
});

describe("도우미", () => {
  it("지정자 추출", () => {
    expect(extractSpecifiers('import a from "x";\nimport "y";\nconst z = await import("z");\nexport { q } from "w";\nrequire("v")').sort()).toEqual(["v", "w", "x", "y", "z"]);
  });
  it("패키지 이름", () => {
    expect(packageNameOf("@a/b/c")).toBe("@a/b");
    expect(packageNameOf("vitest/config")).toBe("vitest");
    expect(packageNameOf("node:fs")).toBeNull();
    expect(packageNameOf("fs")).toBeNull();
    expect(packageNameOf("./x")).toBeNull();
  });
  it("패키지 밖 상대 경로", () => {
    expect(escapesPackage("src/a.ts", "../x")).toBe(false);
    expect(escapesPackage("src/a.ts", "../../x")).toBe(true);
    expect(escapesPackage("a.ts", "../x")).toBe(true);
    expect(escapesPackage("a.ts", "pkg")).toBe(false);
  });
  it("출력 형식", () => {
    const text = formatViolations([{ dir: "a", violations: [] }, { dir: "b", violations: [{ rule: "r", file: "f", message: "m" }] }]);
    expect(text).toContain("ok    a");
    expect(text).toContain("[r] f: m");
    expect(text).toContain("1/2");
  });
});

describe("scope·표식", () => {
  it("--scope @acme 산출물이 @acme 접두사로 통과한다", () => {
    const files = buildPackageFiles(loadLayers(TEMPLATES, "lib"), makeVars({ name: "@acme/demo", scope: "@acme", kind: "lib", year: 2026 }));
    expect(JSON.parse(files["package.json"]).agentConsole.kind).toBe("lib");
    expect(lintTsPackage({ kind: "lib", files, inHousePrefixes: ["@acme/"] })).toEqual([]);
    files["package.json"] = JSON.stringify({ ...JSON.parse(files["package.json"]), dependencies: { "@acme/core": "*" } });
    expect(rules(lintTsPackage({ kind: "lib", files, inHousePrefixes: ["@acme/"] }))).toContain("inhouse-range");
  });
  it("상대 extends 안내에 전달받은 이름을 쓴다", () => {
    const files = make("lib", "@agent-console/demo");
    files["tsconfig.json"] = JSON.stringify({ extends: "../../base.json" });
    const [v] = lintTsPackage({ kind: "lib", files, inHousePrefixes: ["@acme/"] });
    expect(v.message).toContain("@acme/tsconfig");
    expect(v.message).not.toContain("@agent-console");
  });
});
