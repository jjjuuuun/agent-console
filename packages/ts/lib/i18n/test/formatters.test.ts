import { describe, expect, test } from "vitest";

import { createI18n, defaultFormatters, koreanParticles, particleFor } from "@agent-console/i18n";

const t = (lng: string, template: string, values: Record<string, unknown>) => {
  const i18n = createI18n({ language: lng, bundled: { [lng]: { ns: { m: template } } } });
  return i18n.t("m", { ns: "ns", replace: values });
};

describe("particles", () => {
  test.each([
    ["팀", "particle.object", "팀을"],
    ["에이전트", "particle.object", "에이전트를"],
    ["팀", "particle.subject", "팀이"],
    ["에이전트", "particle.topic", "에이전트는"],
    ["팀", "particle.and", "팀과"],
    ["서울", "particle.direction", "서울로"],
    ["팀", "particle.direction", "팀으로"],
    ["abc", "particle.object", "abc을(를)"],
    ["", "particle.direction", "(으)로"],
  ])("%s %s -> %s", (word, format, expected) => {
    expect(t("ko", `{word, ${format}}`, { word })).toBe(expected);
  });

  test(".only gives the particle alone, outside quotes", () => {
    expect(t("ko", "‘{label}’{label, particle.object.only}", { label: "팀" })).toBe("‘팀’을");
    expect(t("ko", "‘{label}’{label, particle.subject.only}", { label: "역할" })).toBe("‘역할’이");
    expect(t("ko", "{label, particle.direction.only}", { label: "x" })).toBe("(으)로");
  });

  test("rules are data: a custom table adds formats", () => {
    expect(particleFor("책", koreanParticles.object!)).toBe("을");
    const i18n = createI18n({
      language: "ko",
      bundled: { ko: { ns: { m: "{w, particle.x}" } } },
      formatters: { "particle.x": (v) => `${String(v)}!` },
    });
    expect(i18n.t("m", { ns: "ns", replace: { w: "a" } })).toBe("a!");
  });
});

describe("Intl formats follow the language", () => {
  const when = new Date(2026, 10, 26, 14, 3, 7);
  test("time and datetime-full use 24-hour time", () => {
    expect(t("en", "{v, time}", { v: when })).toBe("14:03:07");
    expect(t("ko", "{v, time}", { v: when })).toBe("14:03:07");
    expect(t("en", "{v, datetime-full}", { v: when })).toContain("14:03:07");
  });
  test("datetime adds the year only for other years", () => {
    expect(t("en", "{v, datetime}", { v: new Date(2001, 0, 2, 3, 4) })).toContain("2001");
    expect(t("en", "{v, datetime}", { v: new Date(new Date().getFullYear(), 0, 2, 3, 4) })).not.toMatch(/20\d\d/);
  });
  test("numbers, percent, compact", () => {
    expect(t("en", "{v, number}", { v: 12345 })).toBe("12,345");
    expect(t("en", "{v, percent}", { v: 0.42 })).toBe("42%");
    expect(t("en", "{v, number-compact}", { v: 12000 })).toBe("12K");
    expect(t("ko", "{v, number-compact}", { v: 12000 })).toBe("1.2만");
    expect(t("en", "{v, number(maximumFractionDigits: 1)}", { v: 1.26 })).toBe("1.3");
  });
  test("bytes and currency", () => {
    expect(t("en", "{v, bytes(unit: megabyte)}", { v: 1.5 })).toBe("1.5MB");
    expect(t("en", "{v, currency(currency: USD)}", { v: 1.2 })).toBe("$1.20");
    expect(t("en", "{v, currency}", { v: 1234.5 })).toBe("1,234.5");
  });
  test("list", () => {
    expect(t("en", "{v, list}", { v: ["A", "B", "C"] })).toBe("A, B, & C");
  });
  test("relative picks the unit", () => {
    const now = new Date(2026, 10, 26, 12, 0, 0);
    const rel = (ms: number) => defaultFormatters.relative!(new Date(now.getTime() + ms), "en", { now });
    expect(rel(-3000)).toBe("now");
    expect(rel(-3 * 60_000)).toBe("3 min. ago");
    expect(rel(-2 * 3_600_000)).toBe("2 hr. ago");
    expect(rel(-2 * 86_400_000)).toBe("2 days ago");
    expect(rel(-30 * 86_400_000)).toBe(defaultFormatters.date!(new Date(now.getTime() - 30 * 86_400_000), "en", {}));
    expect(defaultFormatters.relative!(new Date(now.getTime() - 3 * 60_000), "ko", { now })).toBe("3분 전");
  });
  test("duration", () => {
    expect(defaultFormatters.duration!(1200, "en", {})).toBe("1.2s");
    expect(defaultFormatters.duration!(3_720_000, "en", {})).toMatch(/1\s?h(r|our)?s?\.?,?\s?2\s?m/);
  });
  test("bad input comes back as text", () => {
    expect(t("en", "{v, number}", { v: "abc" })).toBe("abc");
    expect(t("en", "{v, time}", { v: "not a date" })).toBe("not a date");
  });
});
