import { describe, expect, it } from "vitest";
import type { ModuleInfo } from "@agent-console/contracts";
import { isProblemStatus, modulesSignature, moduleAffects, problemModules, resolveRequires, worstSeverity } from "./resolve";

// 임의의 가짜 모듈: 이름은 테스트 안에서 만든 값이며 실제 서버 모듈과 무관하다.
const mod = (id: string, status: string, roles: string[] = [], extra: Partial<ModuleInfo> = {}): ModuleInfo => ({ id, kind: "k-any", version: "0.0.1", status, web_roles: roles, ...extra });

describe("requires 판정", () => {
  it("빈 requires는 항상 만족한다", () => {
    expect(resolveRequires([], [])).toEqual({ satisfied: true, unmet: [] });
  });
  it("id로도 역할로도 찾는다", () => {
    const list = [mod("m-1", "active", ["role-a"])];
    expect(resolveRequires(["m-1"], list).satisfied).toBe(true);
    expect(resolveRequires(["role-a"], list).satisfied).toBe(true);
    expect(resolveRequires(["m-1", "role-a"], list).satisfied).toBe(true);
  });
  it("모든 항목이 만족해야 한다(AND)", () => {
    const list = [mod("m-1", "active", ["role-a"]), mod("m-2", "disabled", ["role-b"])];
    const r = resolveRequires(["role-a", "role-b"], list);
    expect(r.satisfied).toBe(false);
    expect(r.unmet.map((u) => u.require)).toEqual(["role-b"]);
  });
  it("같은 역할을 가진 모듈 중 하나만 켜져 있어도 만족한다", () => {
    const list = [mod("m-1", "disabled", ["role-a"]), mod("m-2", "active", ["role-a"])];
    expect(resolveRequires(["role-a"], list).satisfied).toBe(true);
  });
  it("꺼진 모듈의 역할은 만족시키지 못한다(웹은 active만 본다)", () => {
    expect(resolveRequires(["role-a"], [mod("m-1", "failed", ["role-a"])]).satisfied).toBe(false);
  });
  it("목록에 없는 항목은 missing이고 일치 모듈이 없다", () => {
    const r = resolveRequires(["x-none"], [mod("m-1", "active")]);
    expect(r.unmet[0]).toMatchObject({ require: "x-none", severity: "missing", matches: [] });
  });
  it("심각도: missing > failed > conflict > unsatisfied > disabled, 모르는 상태는 unsatisfied", () => {
    const list = [mod("a", "disabled", ["ra"]), mod("b", "unsatisfied", ["rb"]), mod("c", "conflict", ["rc"]), mod("d", "failed", ["rd"]), mod("e", "weird", ["re"])];
    const sev = (reqs: string[]) => worstSeverity(resolveRequires(reqs, list).unmet);
    expect(sev(["ra"])).toBe("disabled");
    expect(sev(["ra", "rb"])).toBe("unsatisfied");
    expect(sev(["rb", "rc"])).toBe("conflict");
    expect(sev(["rc", "rd"])).toBe("failed");
    expect(sev(["re"])).toBe("unsatisfied");
    expect(sev(["rd", "nothing"])).toBe("missing");
    expect(sev([])).toBeUndefined();
  });
  it("역할만 일치하면 by=role, id가 일치하면 by=module", () => {
    const list = [mod("m-1", "disabled", ["r-1"])];
    expect(resolveRequires(["m-1"], list).unmet[0]?.by).toBe("module");
    expect(resolveRequires(["r-1"], list).unmet[0]?.by).toBe("role");
  });
});

describe("모듈 목록 도구", () => {
  it("문제는 unsatisfied·failed·conflict와 모르는 상태이고 disabled는 제외한다", () => {
    expect(["active", "disabled", "unsatisfied", "failed", "conflict", "weird"].map(isProblemStatus)).toEqual([false, false, true, true, true, true]);
    expect(problemModules([mod("a", "disabled"), mod("b", "failed")]).map((m) => m.id)).toEqual(["b"]);
  });
  it("서명은 순서와 무관하고 상태 변화에 반응한다", () => {
    const a = [mod("x", "active"), mod("y", "failed")];
    expect(modulesSignature(a)).toBe(modulesSignature([...a].reverse()));
    expect(modulesSignature(a)).not.toBe(modulesSignature([mod("x", "active"), mod("y", "active")]));
  });
  it("모듈이 영향을 주는 requires를 찾는다", () => {
    const m = mod("m-1", "active", ["r-1"]);
    expect(moduleAffects(m, ["r-1"])).toBe(true);
    expect(moduleAffects(m, ["m-1"])).toBe(true);
    expect(moduleAffects(m, ["other"])).toBe(false);
  });
});
