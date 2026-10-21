import { describe, expect, it } from "vitest";

import { PORTABILITY_ENV, formatResultTable, planPackAll, planPortability, rewriteForPortability } from "./plans.mjs";

const ws = [
  { name: "@agent-console/ui", version: "0.1.0", packageJson: { name: "@agent-console/ui", scripts: { build: "x", test: "y" }, dependencies: { "@agent-console/contracts": "^0.4.0" }, peerDependencies: { "@agent-console/tsconfig": "^0.1.0", react: "^19" } } },
  { name: "@agent-console/contracts", version: "0.4.0", packageJson: {} },
  { name: "@agent-console/tsconfig", version: "0.1.0", packageJson: {} },
];

describe("planPackAll", () => {
  it("빌드 후 pack", () => {
    const steps = planPackAll({ outDir: "/o" });
    expect(steps.map((s) => s.label)).toEqual(["build", "pack"]);
    expect(steps[1].args).toEqual(["-r", "--filter", "./packages/**", "pack", "--pack-destination", "/o"]);
    expect(planPackAll({ filter: "./libs/*" })[0].args).toContain("./libs/*");
  });
});

describe("planPortability", () => {
  const plan = planPortability({ pkg: ws[0], workspace: ws, npmDir: "/d/npm/" });
  it("사내 의존을 tarball file: 경로로 바꾸고 overrides에도 둔다", () => {
    expect(plan.rewritten.dependencies["@agent-console/contracts"]).toBe("file:/d/npm/agent-console-contracts-0.4.0.tgz");
    expect(plan.rewritten.overrides["@agent-console/tsconfig"]).toBe("file:/d/npm/agent-console-tsconfig-0.1.0.tgz");
  });
  it("사내 peer는 devDependencies로 옮기고 외부 peer는 남긴다", () => {
    expect(plan.rewritten.peerDependencies).toEqual({ react: "^19" });
    expect(plan.rewritten.devDependencies["@agent-console/tsconfig"]).toContain("file:");
  });
  it("있는 스크립트만 설치 뒤 순서대로 돌린다", () => {
    expect(plan.steps.map((s) => s.label)).toEqual(["install", "build", "test"]);
  });
  it("워크스페이스에 없는 사내 의존을 missing으로 알린다", () => {
    const r = planPortability({ pkg: ws[0], workspace: [ws[0]], npmDir: "/d" });
    expect(r.missing).toEqual(["@agent-console/contracts", "@agent-console/tsconfig"]);
  });
  it("원본 package.json은 바꾸지 않는다", () => {
    rewriteForPortability(ws[0].packageJson, { "@agent-console/contracts": "/x.tgz" });
    expect(ws[0].packageJson.dependencies["@agent-console/contracts"]).toBe("^0.4.0");
  });
});

describe("formatResultTable", () => {
  it("통과·실패 수를 요약한다", () => {
    const text = formatResultTable([{ name: "a", ok: true }, { name: "bb", ok: false, failedStep: "test" }]);
    expect(text).toContain("1/2개 실패");
    expect(text).toMatch(/bb\s+실패\s+test/);
  });
});

describe("다른 scope(@acme)", () => {
  const acme = [
    { name: "@acme/ui", version: "0.1.0", packageJson: { dependencies: { "@acme/core": "^0.1.0" }, devDependencies: { "@agent-console/x": "^0.1.0" } } },
    { name: "@acme/core", version: "0.1.0", packageJson: {} },
  ];
  it("prefixes를 넘기면 @acme 의존이 tarball로 바뀌고 그 밖은 그대로", () => {
    const plan = planPortability({ pkg: acme[0], workspace: acme, npmDir: "/n", prefixes: ["@acme/"] });
    expect(plan.rewritten.dependencies["@acme/core"]).toBe("file:/n/acme-core-0.1.0.tgz");
    expect(plan.rewritten.devDependencies["@agent-console/x"]).toBe("^0.1.0");
    expect(plan.missing).toEqual([]);
  });
});

describe("PORTABILITY_ENV", () => {
  it("저장소 밖 복사본 검사는 시간 단언을 건너뛰는 환경변수를 설정한다", () => {
    expect(PORTABILITY_ENV).toEqual({ AGENT_CONSOLE_SKIP_PERF: "1" });
    expect(Object.isFrozen(PORTABILITY_ENV)).toBe(true);
  });
});
