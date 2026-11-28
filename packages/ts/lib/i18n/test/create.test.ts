import type { MessageCatalog } from "@agent-console/contracts/i18n";
import { describe, expect, test, vi } from "vitest";

import { applyServerCatalog, createI18n, createServerText, setLanguage } from "@agent-console/i18n";
import { createTestI18n, throwOnMissing } from "@agent-console/i18n/testing";

const bundled = {
  en: { app: { hello: "Hello {name}", only_en: "English only", issues_one: "{count} issue", issues_other: "{count} issues" } },
  ko: { app: { hello: "{name}님, 안녕하세요", issues_other: "{count}건" } },
};

const catalog = (language: string, over: Partial<MessageCatalog> = {}): MessageCatalog => ({
  language,
  text: {},
  codes: {},
  ns: {},
  ...over,
});

describe("createI18n", () => {
  test("fills {name} and plural forms", () => {
    const i18n = createI18n({ language: "en", bundled });
    expect(i18n.t("hello", { ns: "app", replace: { name: "Ann" } })).toBe("Hello Ann");
    expect(i18n.t("issues", { ns: "app", count: 1, replace: { count: 1 } })).toBe("1 issue");
    expect(i18n.t("issues", { ns: "app", count: 3, replace: { count: 3 } })).toBe("3 issues");
  });

  test("a missing key falls back along the chain (ko -> en)", () => {
    const i18n = createI18n({ language: "ko", bundled });
    expect(i18n.t("only_en", { ns: "app" })).toBe("English only");
  });

  test("the chain uses fallbackLanguage first, then en", () => {
    const i18n = createI18n({
      language: "de",
      fallbackLanguage: "ko",
      bundled: { ...bundled, de: { app: {} } },
    });
    expect(i18n.t("hello", { ns: "app", replace: { name: "Jo" } })).toBe("Jo님, 안녕하세요");
    expect(i18n.t("only_en", { ns: "app" })).toBe("English only");
  });

  test("regional language falls to the primary language", () => {
    const i18n = createI18n({ language: "en-US", bundled });
    expect(i18n.t("only_en", { ns: "app" })).toBe("English only");
  });

  test("the server catalog overrides app messages and adds languages", () => {
    const i18n = createI18n({ language: "ko", bundled });
    applyServerCatalog(i18n, catalog("ko", { ns: { app: { hello: "서버 {name}" } } }));
    expect(i18n.t("hello", { ns: "app", replace: { name: "A" } })).toBe("서버 A");
    expect(i18n.t("only_en", { ns: "app" })).toBe("English only");
    applyServerCatalog(i18n, catalog("de", { ns: { app: { hello: "Hallo {name}" } } }));
    void i18n.changeLanguage("de");
    expect(i18n.t("hello", { ns: "app", replace: { name: "A" } })).toBe("Hallo A");
  });

  test("missing keys and values reach onMissing; tests throw", () => {
    const seen = vi.fn();
    const i18n = createI18n({ language: "en", bundled, onMissing: seen });
    i18n.t("nope", { ns: "app" });
    expect(seen).toHaveBeenCalledWith(expect.objectContaining({ kind: "key", key: "nope", namespace: "app" }));
    i18n.t("hello", { ns: "app" });
    expect(seen).toHaveBeenCalledWith(expect.objectContaining({ kind: "interpolation" }));
    const strict = createTestI18n({ bundled });
    expect(() => strict.t("nope", { ns: "app" })).toThrow(/missing/);
    expect(() => throwOnMissing({ kind: "key", language: "ko", namespace: "a", key: "b" })).toThrow();
    expect(strict.language).toBe("ko");
  });
});

describe("createServerText", () => {
  const make = () => {
    const i18n = createI18n({ language: "ko", bundled });
    applyServerCatalog(
      i18n,
      catalog("ko", {
        text: { "Max turns.per run": "턴 수: 실행당", "Tool: {x}": "도구: {x}" },
        codes: { "project.folder_taken": "‘{path}’은 이미 등록됨", "run.count": "{count}건 실패" },
      }),
    );
    applyServerCatalog(i18n, catalog("en", { text: { Only: "Only!" } }));
    return createServerText(i18n);
  };

  test("original strings are keys, dots and colons included; unknown stays", () => {
    const s = make();
    expect(s.text("Max turns.per run")).toBe("턴 수: 실행당");
    expect(s.text("Tool: {x}")).toBe("도구: {x}");
    expect(s.text("Unknown text")).toBe("Unknown text");
  });
  test("falls back to the fallback language's text", () => {
    expect(make().text("Only")).toBe("Only!");
  });
  test("issue codes fill details; no template returns the fallback", () => {
    const s = make();
    expect(s.issue("project.folder_taken", { path: "/a" }, "raw")).toBe("‘/a’은 이미 등록됨");
    expect(s.issue("run.count", { count: 4 }, "raw")).toBe("4건 실패");
    expect(s.issue("unknown.code", { a: 1 }, "raw message")).toBe("raw message");
    expect(s.issue("project.folder_taken", null, "raw")).toContain("{path}");
  });
  test("a details key named like an i18next option cannot break the lookup", () => {
    const s = make();
    expect(s.issue("project.folder_taken", { path: "/a", lng: "xx", ns: "y", defaultValue: "z" }, "raw")).toBe("‘/a’은 이미 등록됨");
  });
});

describe("setLanguage", () => {
  test("loads lazy app bundle, then server catalog over it, then switches", async () => {
    const i18n = createI18n({
      language: "en",
      bundled: { en: bundled.en },
      loadBundled: async (language) => (language === "ko" ? bundled.ko : undefined),
    });
    const result = await setLanguage(i18n, "ko", {
      fetchCatalog: async (language) => catalog(language, { ns: { app: { hello: "서버 {name}" } } }),
    });
    expect(result).toEqual({ language: "ko", server: "loaded" });
    expect(i18n.language).toBe("ko");
    expect(i18n.t("hello", { ns: "app", replace: { name: "A" } })).toBe("서버 A");
    expect(i18n.t("issues", { ns: "app", count: 2, replace: { count: 2 } })).toBe("2건");
  });

  test("loads the lazy app bundles of the fallback chain too, so a key missing in the new language shows the fallback text", async () => {
    const loads: string[] = [];
    const i18n = createI18n({
      language: "ko",
      fallbackLanguage: "en",
      bundled: { ko: bundled.ko },
      loadBundled: async (language) => {
        loads.push(language);
        return language === "en" ? bundled.en : language === "ko" ? bundled.ko : language === "de" ? { app: { other: "nur de" } } : undefined;
      },
    });
    await setLanguage(i18n, "de");
    expect(loads.sort()).toEqual(["de", "en"]);
    expect(i18n.t("hello", { ns: "app", replace: { name: "A" } })).toBe(bundled.en.app.hello.replace("{name}", "A"));
    expect(i18n.t("other", { ns: "app" })).toBe("nur de");
    // A language given in `bundled` may be a boot subset, so it is loaded once; nothing is fetched twice.
    await setLanguage(i18n, "ko");
    await setLanguage(i18n, "de");
    await setLanguage(i18n, "ko");
    expect(loads.sort()).toEqual(["de", "en", "ko"]);
  });

  test("a failing server still switches with app messages only", async () => {
    const i18n = createI18n({ language: "en", bundled });
    const result = await setLanguage(i18n, "ko", {
      fetchCatalog: async () => {
        throw new Error("down");
      },
    });
    expect(result.server).toBe("failed");
    expect(i18n.t("hello", { ns: "app", replace: { name: "A" } })).toBe("A님, 안녕하세요");
  });

  test("a slow server times out", async () => {
    const i18n = createI18n({ language: "en", bundled });
    const result = await setLanguage(i18n, "ko", {
      timeoutMs: 20,
      fetchCatalog: () => new Promise(() => undefined),
    });
    expect(result.server).toBe("failed");
    expect(i18n.language).toBe("ko");
  });

  test("no fetch = skipped; null = missing", async () => {
    const i18n = createI18n({ language: "en", bundled });
    expect((await setLanguage(i18n, "ko")).server).toBe("skipped");
    expect((await setLanguage(i18n, "en", { fetchCatalog: async () => null })).server).toBe("missing");
  });
});
