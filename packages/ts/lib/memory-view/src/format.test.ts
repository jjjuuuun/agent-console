import { describe, expect, it } from "vitest";
import { formatBytes, formatRelativeTime, formatSizeDelta, hashSlot, keyErrorText, languageForContentType, utf8Bytes, validateKey } from "./format";
import { defaultMessages, formatMessage, resolveMessages } from "./messages";

const m = resolveMessages();

describe("format", () => {
  it("UTF-8 바이트는 문자 수가 아니다", () => {
    expect(utf8Bytes("abc")).toBe(3);
    expect(utf8Bytes("가나다")).toBe(9);
    expect(utf8Bytes("😀")).toBe(4);
  });
  it("크기 표기", () => {
    expect(formatBytes(512, m)).toBe("512 B");
    expect(formatBytes(1229, m)).toBe("1.2 KiB");
    expect(formatBytes(1024, m)).toBe("1 KiB");
    expect(formatBytes(64 * 1024, m)).toBe("64 KiB");
    expect(formatBytes(5 * 1024 * 1024, m)).toBe("5 MiB");
    expect(formatSizeDelta(40)).toBe("+40 B");
    expect(formatSizeDelta(-12)).toBe("\u221212 B");
    expect(formatSizeDelta(0)).toBe("+0 B");
  });
  it("상대 시각", () => {
    const now = 10_000_000;
    expect(formatRelativeTime(now - 5, now, m)).toBe("방금");
    expect(formatRelativeTime(now - 180, now, m)).toBe("3분 전");
    expect(formatRelativeTime(now - 7200, now, m)).toBe("2시간 전");
    expect(formatRelativeTime(now - 2 * 86_400, now, m)).toBe("2일 전");
    expect(formatRelativeTime(now - 40 * 86_400, now, m)).toMatch(/^\d\d\/\d\d \d\d:\d\d$/);
    expect(formatRelativeTime(null, now, m)).toBe("–");
  });
  it("키 규칙", () => {
    expect(validateKey("")).toBe("empty");
    expect(validateKey("a//b")).toBe("emptySegment");
    expect(validateKey("/a")).toBe("edgeSlash");
    expect(validateKey("a/")).toBe("edgeSlash");
    expect(validateKey("a/./b")).toBe("dotSegment");
    expect(validateKey("a/../b")).toBe("dotSegment");
    expect(validateKey("a\u0007b")).toBe("control");
    expect(validateKey("가".repeat(256))).toBeNull();
    expect(validateKey("가".repeat(257))).toBe("tooLong");
    expect(validateKey("결정/api-버전")).toBeNull();
    expect(keyErrorText("tooLong", "x".repeat(300), m)).toBe("300/256자");
  });
  it("본문 형식 → 편집기 언어(모르면 text)", () => {
    expect(languageForContentType("text/markdown")).toBe("markdown");
    expect(languageForContentType("text/html; charset=utf-8")).toBe("html");
    expect(languageForContentType("application/json")).toBe("json");
    expect(languageForContentType("application/ld+json")).toBe("json");
    expect(languageForContentType("text/x-unknown")).toBe("text");
    expect(languageForContentType(undefined)).toBe("text");
  });
  it("hashSlot은 1..n", () => {
    for (const s of ["a", "b", "에이전트", ""]) {
      const v = hashSlot(s, 8);
      expect(v).toBeGreaterThanOrEqual(1);
      expect(v).toBeLessThanOrEqual(8);
    }
  });
  it("문구 틀", () => {
    expect(formatMessage("{n}개 {x}", { n: 3 })).toBe("3개 {x}");
    expect(Object.keys(defaultMessages).length).toBeGreaterThan(100);
    expect(resolveMessages({ "time.now": "now" })["time.now"]).toBe("now");
  });
});
