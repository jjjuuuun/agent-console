import { describe, expect, it } from "vitest";
import { discoveredCount, lineStateOf, modelSources } from "./catalogView";

// 모델 id는 전부 임의 값이다.
describe("catalogView", () => {
  it("계정 출처(discovered) 항목만 센다: 둘 다인 항목은 센다, 출처 모름·설정만은 세지 않는다", () => {
    expect(discoveredCount(undefined)).toBe(0);
    expect(discoveredCount([{ id: "a", sources: ["config"] }, { id: "b", sources: ["config", "discovered"] }, { id: "c", sources: ["discovered"] }, { id: "d" }])).toBe(2);
    expect(modelSources({})).toEqual([]);
  });

  it("진행 중이면 fetching, 응답 없음·옛 서버(discovery null)는 줄 없음, 나머지는 서버 상태 그대로", () => {
    const base = { backend_id: "b", models: [] };
    expect(lineStateOf(undefined, false)).toBeNull();
    expect(lineStateOf({ ...base, discovery: null }, false)).toBeNull();
    expect(lineStateOf({ ...base, discovery: null }, true)).toBe("fetching");
    for (const state of ["ok", "stale", "failed", "disabled", "unsupported"] as const) {
      expect(lineStateOf({ ...base, discovery: { state } }, false)).toBe(state);
    }
  });
});
