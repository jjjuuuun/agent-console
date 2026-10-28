import { describe, expect, it } from "vitest";
import { formatInterval } from "./formatInterval";

const units = { hour: (n: number) => `${n}시간`, minute: (n: number) => `${n}분`, second: (n: number) => `${n}초` };

describe("formatInterval", () => {
  it("0인 단위는 뺀다", () => {
    expect(formatInterval(3600, units)).toBe("1시간");
    expect(formatInterval(5400, units)).toBe("1시간 30분");
    expect(formatInterval(90, units)).toBe("1분 30초");
    expect(formatInterval(45, units)).toBe("45초");
  });
});

describe("formatInterval 경계(QA 10/28)", () => {
  it("0·음수·소수는 0초 또는 반올림, 단위는 부르는 쪽 틀을 쓴다", () => {
    expect(formatInterval(0, units)).toBe("0초");
    expect(formatInterval(-5, units)).toBe("0초");
    expect(formatInterval(59.6, units)).toBe("1분");
    expect(formatInterval(86_400, units)).toBe("24시간");
    expect(formatInterval(60, { hour: (n) => `${n}h`, minute: (n) => `${n}m`, second: (n) => `${n}s` })).toBe("1m");
  });
});
