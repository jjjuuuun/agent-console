import { describe, expect, it } from "vitest";

import { inHouseClosure, isCovered, isInHouse, matchesPattern, readWorkspacePatterns, tarballName } from "./workspace.mjs";

describe("패턴", () => {
  it("pnpm-workspace.yaml 목록을 읽는다", () => {
    const yaml = 'packages:\n  - "packages/ts/*/*"\n  - apps/web\n  - "!apps/web/legacy"\nlinkWorkspacePackages: true\n';
    expect(readWorkspacePatterns(yaml)).toEqual({ include: ["packages/ts/*/*", "apps/web"], exclude: ["apps/web/legacy"] });
  });
  it("* 는 한 단계, ** 는 여러 단계", () => {
    expect(matchesPattern("packages/ts/*", "packages/ts/ui")).toBe(true);
    expect(matchesPattern("packages/ts/*", "packages/ts/lib/ui")).toBe(false);
    expect(matchesPattern("packages/ts/*/*", "packages/ts/lib/ui")).toBe(true);
    expect(matchesPattern("packages/**", "packages/ts/lib/ui")).toBe(true);
    expect(matchesPattern("apps/web", "apps/web2")).toBe(false);
  });
  it("제외 패턴을 반영한다", () => {
    const p = { include: ["a/*"], exclude: ["a/x"] };
    expect(isCovered(p, "a/y")).toBe(true);
    expect(isCovered(p, "a/x")).toBe(false);
  });
});

describe("사내 의존 닫힘", () => {
  const pkg = (name, deps = {}, dev = {}) => ({ name, version: "0.1.0", packageJson: { dependencies: deps, devDependencies: dev } });
  const ws = [pkg("@agent-console/a", { "@agent-console/b": "^0.1.0", react: "^19" }), pkg("@agent-console/b", {}, { "@agent-console/c": "^0.1.0" }), pkg("@agent-console/c")];
  it("의존되는 쪽이 먼저 오고 시작 패키지는 뺀다", () => {
    expect(inHouseClosure("@agent-console/a", ws)).toEqual({ order: ["@agent-console/c", "@agent-console/b"], missing: [] });
  });
  it("없는 사내 의존을 알린다", () => {
    const r = inHouseClosure("@agent-console/a", [pkg("@agent-console/a", { "@agent-console/zz": "^0.1.0" })]);
    expect(r.missing).toEqual(["@agent-console/zz"]);
  });
  it("순환은 오류", () => {
    const loop = [pkg("@agent-console/a", { "@agent-console/b": "^0.1.0" }), pkg("@agent-console/b", { "@agent-console/a": "^0.1.0" })];
    expect(() => inHouseClosure("@agent-console/a", loop)).toThrow("순환");
  });
});

describe("이름", () => {
  it("tarball 이름은 pnpm pack과 같다", () => {
    expect(tarballName("@agent-console/ui", "0.1.0")).toBe("agent-console-ui-0.1.0.tgz");
    expect(tarballName("plain", "1.0.0")).toBe("plain-1.0.0.tgz");
  });
  it("접두사를 바꿀 수 있다", () => {
    expect(isInHouse("@acme/x", ["@acme/"])).toBe(true);
    expect(isInHouse("@agent-console/x", ["@acme/"])).toBe(false);
  });
});

import { prefixOf, resolvePrefixes } from "./workspace.mjs";

describe("사내 접두사 결정", () => {
  it("scope에서 접두사를 뽑는다", () => {
    expect(prefixOf("@acme/x")).toBe("@acme/");
    expect(prefixOf("plain")).toBeNull();
  });
  it("명시 > 루트 이름 scope > 패키지 scope > 기본값", () => {
    expect(resolvePrefixes({ explicit: ["@a", "@b/"], rootPackageJson: { name: "@r/root" } })).toEqual(["@a/", "@b/"]);
    expect(resolvePrefixes({ rootPackageJson: { name: "@r/root" }, packageNames: ["@p/x"] })).toEqual(["@r/"]);
    expect(resolvePrefixes({ rootPackageJson: { name: "root" }, packageNames: ["@p/x", "@p/y", "z"] })).toEqual(["@p/"]);
    expect(resolvePrefixes({})).toEqual(["@agent-console/"]);
  });
});
