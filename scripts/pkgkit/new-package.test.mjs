import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { NewPackageArgsError, parseNewPackageArgs } from "./lib/scaffold.mjs";
import { lintTsPackage } from "./lib/lint-rules.mjs";
import { readPackageFiles } from "./lib/fsutil.mjs";
import { createPackage } from "./new-package.mjs";

let root;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "pkgkit-new-"));
  writeFileSync(join(root, "pnpm-workspace.yaml"), 'packages:\n  - "packages/ts/*/*"\n');
  writeFileSync(join(root, "package.json"), JSON.stringify({ devDependencies: { vitest: "^7.7.7" } }));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

const args = (...a) => parseNewPackageArgs(["--root", root, ...a]);

describe("createPackage", () => {
  it("packages/ts/<kind>/<이름>에 만들고 pkg-lint를 통과한다", () => {
    const r = createPackage(args("--kind", "lib", "--description", "데모", "demo"));
    expect(r.relDir).toBe("packages/ts/lib/demo");
    expect(r.covered).toBe(true);
    const pkg = JSON.parse(readFileSync(join(r.dir, "package.json"), "utf8"));
    expect(pkg).toMatchObject({ name: "@agent-console/demo", description: "데모" });
    expect(pkg.devDependencies.vitest).toBe("^7.7.7");
    expect(lintTsPackage({ kind: "lib", files: readPackageFiles(r.dir) })).toEqual([]);
  });

  it("초안으로 tsconfig·eslint-config 패키지를 만든다", () => {
    for (const draft of ["tsconfig", "eslint-config"]) {
      const r = createPackage(args("--kind", "config", "--draft", draft, draft));
      expect(lintTsPackage({ kind: "config", files: readPackageFiles(r.dir) })).toEqual([]);
    }
  });

  it("--dry-run은 쓰지 않는다", () => {
    const r = createPackage(args("--kind", "lib", "--dry-run", "demo"));
    expect(existsSync(r.dir)).toBe(false);
    expect(r.files).toContain("package.json");
  });

  it("이미 있는 폴더는 거부한다", () => {
    mkdirSync(join(root, "packages/ts/lib/demo"), { recursive: true });
    expect(() => createPackage(args("--kind", "lib", "demo"))).toThrow(NewPackageArgsError);
  });

  it("워크스페이스 패턴 밖이면 covered=false", () => {
    expect(createPackage(args("--kind", "lib", "--dir", "elsewhere/demo", "demo")).covered).toBe(false);
  });
});

import { discoverPackages, inferKind } from "./lib/fsutil.mjs";
import { lintWorkspace } from "./pkg-lint.mjs";

describe("scope·종류 표식·폴더 오류", () => {
  it("--scope @acme --dir 임의 위치: 표식으로 config 종류가 정해지고 pkg-lint가 통과한다", () => {
    writeFileSync(join(root, "pnpm-workspace.yaml"), 'packages:\n  - "libs/*"\n');
    createPackage(args("--kind", "config", "--scope", "@acme", "--dir", "libs/tsconfig", "tsconfig"));
    createPackage(args("--kind", "lib", "--scope", "@acme", "--dir", "libs/demo", "demo"));
    const [cfg] = discoverPackages(root, { under: "libs/" }).filter((p) => p.relDir === "libs/tsconfig");
    expect(inferKind(cfg.relDir, cfg.packageJson)).toBe("config");
    expect(inferKind("libs/tsconfig", null)).toBe("lib");
    expect(inferKind("packages/ts/config/x", null)).toBe("config");
    const results = lintWorkspace(root, { under: "libs/", prefix: ["@acme"] });
    expect(results.map((r) => r.dir)).toEqual(["libs/demo", "libs/tsconfig"]);
    expect(results.flatMap((r) => r.violations)).toEqual([]);
    // 접두사를 안 주면 패키지들의 scope(@acme)에서 추정한다.
    expect(lintWorkspace(root, { under: "libs/" }).flatMap((r) => r.violations)).toEqual([]);
  });

  it("패키지 폴더가 없으면 읽을 수 있는 오류", () => {
    expect(() => discoverPackages(root, { under: "nope/" })).toThrow("패키지 폴더가 없다");
    expect(() => lintWorkspace(root)).toThrow("패키지 폴더가 없다");
  });
});
