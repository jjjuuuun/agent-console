import { describe, expect, it } from "vitest";
import { formatResetsPhrase, isFarReset } from "./resetDisplay";
import { RESET_DATE_AFTER_SECONDS } from "./usageConfig";

const rel = (r: string) => `까지 ${r}`;
const on = (d: string) => `날짜 ${d}`;

describe("먼 미래 resets_at 표시", () => {
  const now = 1_800_000_000;
  it("기준 이하는 남은 시간, 넘으면 날짜(기준값은 설정 데이터)", () => {
    expect(isFarReset(now + RESET_DATE_AFTER_SECONDS, now)).toBe(false);
    expect(isFarReset(now + RESET_DATE_AFTER_SECONDS + 1, now)).toBe(true);
    expect(formatResetsPhrase(now + 3 * 86400, now, rel, on)).toEqual({ text: "까지 3일", far: false });
    const far = formatResetsPhrase(now + 45 * 86400, now, rel, on);
    expect(far.far).toBe(true);
    expect(far.text.startsWith("날짜 ")).toBe(true);
  });
  it("기준을 인자로 바꿀 수 있다", () => {
    expect(formatResetsPhrase(now + 2 * 86400, now, rel, on, 86400).far).toBe(true);
  });
});
