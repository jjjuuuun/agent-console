import { describe, expect, it } from "vitest";
import { buildStartSteps } from "./startSteps";
import { pickFeatured } from "./useStartGuide";

const pathOf = (role: string) => `/p/${role}`;

describe("buildStartSteps", () => {
  it("단계 순서는 표 순서, 완료는 개수로 계산, 모든 단계가 to 경로를 가진다", () => {
    const steps = buildStartSteps({ counts: { usableTeams: 1, conversations: 0, runs: undefined }, pathOf, isOn: () => true });
    expect(steps.map((s) => [s.id, s.done])).toEqual([["create", true], ["talk", false], ["review", false]]);
    expect(steps.every((s) => typeof s.to === "string" && s.onAction === undefined)).toBe(true);
  });
  it("꺼진 화면으로 가는 단계는 뺀다", () => {
    const steps = buildStartSteps({ counts: { usableTeams: 0, conversations: 0, runs: 0 }, pathOf, isOn: (r) => r !== "runs" });
    expect(steps.map((s) => s.id)).toEqual(["create", "talk"]);
  });
});

describe("pickFeatured", () => {
  it("featured 있는 것만, 작은 값 먼저, 최대 3개", () => {
    const mk = (id: string, featured?: number | null) => ({ id, name: id, ...(featured === undefined ? {} : { featured }) });
    const out = pickFeatured([mk("a", 4), mk("b"), mk("c", 1), mk("d", null), mk("e", 2), mk("f", 3)]);
    expect(out.map((p) => p.id)).toEqual(["c", "e", "f"]);
  });
});
