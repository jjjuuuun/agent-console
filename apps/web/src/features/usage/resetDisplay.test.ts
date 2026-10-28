import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { formatResetClock, formatResetsPhrase, isFarReset } from "./resetDisplay";
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

describe("5.5R.30 레일 글리프 자리", () => {
  const css = readFileSync(join(import.meta.dirname, "usage-indicator.css"), "utf-8");
  it("레일 값의 글리프는 숫자 위에 겹치지 않고(absolute 아님) 옆 자리를 갖는다", () => {
    const mark = /\.usage-ind-rail-mark \{([^}]*)\}/.exec(css)![1]!;
    expect(mark).not.toContain("position: absolute");
    expect(/\.usage-ind-rail-value \{([^}]*)\}/.exec(css)![1]!).toContain("inline-flex");
    expect(/\.usage-ind-rail-item \{ width: min\((\d+)px/.exec(css)![1]).toBe("40");
  });
});

describe("사이드바 초기화 줄(사용자 요청 10/28)", () => {
  const text = { today: (t: string) => `${t}에 초기화`, other: (d: string, t: string) => `(${d}) ${t}에 초기화` };
  const at = (y: number, mo: number, d: number, h: number, mi = 0) => new Date(y, mo - 1, d, h, mi).getTime() / 1000;
  const now = at(2026, 10, 28, 9);
  it("오늘이면 시각만", () => {
    expect(formatResetClock(at(2026, 10, 28, 14, 20), now, text)).toBe("오후 2:20에 초기화");
  });
  it("다른 날이면 요일을 앞에(일주일 이내), 더 멀면 날짜", () => {
    expect(formatResetClock(at(2026, 11, 1, 12), now, text)).toBe("(일요일) 오후 12:00에 초기화");
    expect(formatResetClock(at(2026, 11, 30, 0, 5), now, text)).toBe("(11월 30일) 오전 12:05에 초기화");
  });
  it("기준 일수·로케일은 인자", () => {
    expect(formatResetClock(at(2026, 11, 1, 12), now, text, 2)).toBe("(11월 1일) 오후 12:00에 초기화");
  });
});
