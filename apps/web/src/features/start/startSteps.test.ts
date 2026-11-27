import { describe, expect, it } from "vitest";
import { koT } from "../../testing/koText";
import { createStartMessages } from "./messages";
import { buildStartSteps } from "./startSteps";

const text = createStartMessages(koT("start")).steps;

const pathOf = (role: string) => `/p/${role}`;

describe("buildStartSteps", () => {
  it("단계 순서는 표 순서, 완료는 개수로 계산, 모든 단계가 to 경로를 가진다", () => {
    const steps = buildStartSteps({ counts: { usableTeams: 1, conversations: 0, runs: undefined }, pathOf, isOn: () => true, text });
    expect(steps.map((s) => [s.id, s.done])).toEqual([["create", true], ["talk", false], ["review", false]]);
    expect(steps.every((s) => typeof s.to === "string" && s.onAction === undefined)).toBe(true);
  });
  it("꺼진 화면으로 가는 단계는 뺀다", () => {
    const steps = buildStartSteps({ counts: { usableTeams: 0, conversations: 0, runs: 0 }, pathOf, isOn: (r) => r !== "runs", text });
    expect(steps.map((s) => s.id)).toEqual(["create", "talk"]);
  });
});
