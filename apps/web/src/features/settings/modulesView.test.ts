import { describe, expect, it } from "vitest";
import type { ModuleInfo } from "@agent-console/contracts";
import { countModules, groupModules, showsReasonCollapsed } from "./modulesView";

// 임의의 가짜 모듈(이름·종류는 이 테스트 안의 값이다)
const mod = (id: string, kind: string, status: string, extra: Partial<ModuleInfo> = {}): ModuleInfo => ({ id, kind, version: "1", status, web_roles: [], ...extra });
const list = [
  mod("a-1", "kx", "active"),
  mod("a-2", "kx", "failed", { reason: "boom" }),
  mod("b-1", "ky", "disabled"),
  mod("a-3", "kx", "disabled"),
  mod("b-2", "ky", "unsatisfied"),
  mod("c-1", "kz", "weird"),
];

describe("모듈 목록 보기 계산", () => {
  it("개수: 문제는 꺼짐을 포함하지 않고, 모르는 상태는 전체와 문제에만 센다", () => {
    const c = countModules(list);
    expect(c).toMatchObject({ total: 6, active: 1, disabled: 2, problems: 3, hasFailed: true });
    expect(c.byStatus).toMatchObject({ active: 1, disabled: 2, unsatisfied: 1, failed: 1, conflict: 0 });
  });
  it("그룹 순서는 처음 나온 kind 순이고 그룹 안은 문제 -> 꺼짐 -> 켜짐", () => {
    const groups = groupModules(list, "all", "");
    expect(groups.map((g) => g.kind)).toEqual(["kx", "ky", "kz"]);
    expect(groups[0]?.modules.map((m) => m.id)).toEqual(["a-2", "a-3", "a-1"]);
    expect(groups[1]?.modules.map((m) => m.id)).toEqual(["b-2", "b-1"]);
  });
  it("상태 필터와 검색은 결과가 없는 그룹을 뺀다", () => {
    expect(groupModules(list, "failed", "").map((g) => g.kind)).toEqual(["kx"]);
    expect(groupModules(list, "all", "b-").map((g) => g.kind)).toEqual(["ky"]);
    expect(groupModules(list, "conflict", "")).toEqual([]);
  });
  it("접힌 상태의 이유 줄은 이유가 있는 문제 행만", () => {
    expect(list.map(showsReasonCollapsed)).toEqual([false, true, false, false, false, false]);
  });
});
