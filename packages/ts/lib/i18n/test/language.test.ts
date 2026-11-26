import { describe, expect, test } from "vitest";

import { availableLanguages, languageName, matchLanguage, normalizeLanguage, resolveLanguage } from "@agent-console/i18n";

describe("resolveLanguage", () => {
  const available = ["en", "ko", "de"];
  test("saved setting wins", () => {
    expect(resolveLanguage({ preference: "ko", browser: ["en"], available, serverDefault: "de" })).toBe("ko");
  });
  test("browser languages next, matched by primary language", () => {
    expect(resolveLanguage({ preference: null, browser: ["fr-FR", "ko-KR"], available, serverDefault: "de" })).toBe("ko");
  });
  test("server default next", () => {
    expect(resolveLanguage({ browser: ["fr"], available, serverDefault: "de" })).toBe("de");
  });
  test("then en (or the given fallback)", () => {
    expect(resolveLanguage({ browser: ["fr"], available: ["ko"] })).toBe("en");
    expect(resolveLanguage({ browser: [], available: ["ko"], fallback: "ko" })).toBe("ko");
  });
  test("an unavailable saved setting is skipped", () => {
    expect(resolveLanguage({ preference: "ja", browser: ["de"], available })).toBe("de");
  });
});

describe("matching", () => {
  test("exact beats primary", () => {
    expect(matchLanguage("pt-BR", ["pt", "pt-BR"])).toBe("pt-BR");
    expect(matchLanguage("en-US", ["en", "ko"])).toBe("en");
    expect(matchLanguage("fr", ["en"])).toBeUndefined();
  });
  test("normalizes case and underscores", () => {
    expect(normalizeLanguage("zh_hant_tw")).toBe("zh-Hant-TW");
    expect(matchLanguage("EN_us", ["en"])).toBe("en");
  });
  test("availableLanguages unions app and server", () => {
    const info = { languages: [{ code: "de", sources: [], complete: true }, { code: "en", sources: [], complete: true }] };
    expect(availableLanguages(["en", "ko"], info)).toEqual(["en", "ko", "de"]);
    expect(availableLanguages(["en"], null)).toEqual(["en"]);
  });
  test("languageName writes in the given language", () => {
    expect(languageName("ko", "en")).toBe("Korean");
    expect(languageName("ko")).toBe("한국어");
  });
});
