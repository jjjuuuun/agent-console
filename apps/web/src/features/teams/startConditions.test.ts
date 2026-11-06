import { describe, expect, it } from "vitest";
import { START_CONDITIONS, startConditionsMet, type TeamOverview } from "./teamsLogic";

const node = (id: string) => ({ id, type: "t", position: { x: 0, y: 0 } });
const overview = (over: Partial<TeamOverview>): TeamOverview => ({ entries: [], exits: [], asks: [], declared: new Map(), ...over });

describe("5.7R.39 시작 조건(안내 띠 숨김)", () => {
  it("조건은 데이터 목록이고, 모두 채워야 충족이다", () => {
    expect(START_CONDITIONS.length).toBeGreaterThan(0);
    expect(startConditionsMet(overview({}))).toBe(false);
    expect(startConditionsMet(overview({ entries: [node("a")] }))).toBe(false);
    expect(startConditionsMet(overview({ exits: [node("a")] }))).toBe(false);
    expect(startConditionsMet(overview({ entries: [node("a")], exits: [node("b")] }))).toBe(true);
  });
});
