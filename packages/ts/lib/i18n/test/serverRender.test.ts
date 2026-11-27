import type { MessageCatalog } from "@agent-console/contracts/i18n";
import { describe, expect, test } from "vitest";

import {
  applyServerCatalog,
  createI18n,
  createServerText,
  fillTemplate,
  setLanguage,
  setSourceLanguage,
  type TextTemplateLike,
} from "@agent-console/i18n";

const bundled = { en: { app: { a: "A" } }, ko: { app: { a: "가" } } };
const catalog = (language: string, text: Record<string, string> = {}): MessageCatalog => ({ language, text, codes: {}, ns: {} });
const t = (template: string, params: TextTemplateLike["params"] = {}): TextTemplateLike => ({ template, params });

// Same cases as the server's render_text_template table (test_agent_console_contracts_v16_1_text.py).
const RULES: [string, TextTemplateLike, string][] = [
  ["string", t("비밀 '{name}'", { name: "api_key" }), "ko 비밀 'api_key'"],
  ["integer", t("{n}개", { n: 3 }), "ko 3개"],
  ["whole float", t("{seconds}초", { seconds: 20.0 }), "ko 20초"],
  ["float", t("{seconds}초", { seconds: 1.5 }), "ko 1.5초"],
  ["bool and null", t("{on} {off} {none}", { on: true, off: false, none: null }), "ko true false "],
  ["missing name", t("{missing} 그대로", { other: "x" }), "ko {missing} 그대로"],
  ["access and positional", t("{a.b} {0} {}"), "ko {a.b} {0} {}"],
  ["double braces", t("{{괄호}} {v}", { v: 1 }), "ko {괄호} 1"],
  ["broken template", t("짝 없는 {"), "ko 짝 없는 {"],
  ["stray close", t("닫힘 }"), "ko 닫힘 }"],
  ["fixed", t("고정 문장"), "ko 고정 문장"],
];

describe("fillTemplate", () => {
  test.each(RULES)("%s", (_name, part, expected) => {
    const values = Object.fromEntries(
      Object.entries(part.params ?? {}).map(([k, v]) => [k, v === null ? "" : String(v)]),
    );
    expect(fillTemplate(part.template, values)).toBe(expected.slice(3));
  });
});

describe("ServerText.render", () => {
  const make = (language = "ko") => {
    const i18n = createI18n({ language, bundled });
    setSourceLanguage(i18n, "ko");
    // The source-language catalog has no entries for source text; the en catalog translates it (must not show).
    const entries = Object.fromEntries(RULES.map(([, part]) => [part.template, `en ${part.template}`]));
    applyServerCatalog(i18n, catalog("en", entries));
    applyServerCatalog(i18n, catalog("ko"));
    return i18n;
  };

  test.each(RULES)("source language shows the value: %s", (_name, part) => {
    const server = createServerText(make());
    expect(server.render("VALUE", [part])).toBe("VALUE");
  });

  test("a translated language fills the translated template with the values", () => {
    const i18n = createI18n({ language: "en", bundled });
    setSourceLanguage(i18n, "ko");
    applyServerCatalog(
      i18n,
      catalog("en", { "{seconds}초 안에 응답이 없었습니다.": "No response within {seconds} seconds.", "있음": "present", "비밀 '{name}': {state}": "Secret '{name}': {state}", "첫 문장.": "First." }),
    );
    const server = createServerText(i18n);
    expect(server.render("x", [t("{seconds}초 안에 응답이 없었습니다.", { seconds: 20 })])).toBe("No response within 20 seconds.");
    expect(server.render("x", [t("첫 문장."), t("{seconds}초 안에 응답이 없었습니다.", { seconds: 1.5 })])).toBe(
      "First. No response within 1.5 seconds.",
    );
    // nested template is translated first
    expect(server.render("x", [t("비밀 '{name}': {state}", { name: "k", state: t("있음") })])).toBe("Secret 'k': present");
  });

  test("one missing template (or nested one) returns the value unchanged", () => {
    const i18n = createI18n({ language: "en", bundled });
    setSourceLanguage(i18n, "ko");
    applyServerCatalog(i18n, catalog("en", { 첫: "First", "{n}개": "{n} items" }));
    const server = createServerText(i18n);
    expect(server.render("원문 값", [t("첫"), t("없는 틀")])).toBe("원문 값");
    expect(server.render("원문 값", [t("{n}개", { n: t("없는 낱말") })])).toBe("원문 값");
  });

  test("an installer-changed template is not a key, so the value stays (R0)", () => {
    const i18n = createI18n({ language: "en", bundled });
    applyServerCatalog(i18n, catalog("en", { "{seconds}초 안에 응답이 없었습니다.": "No response within {seconds} seconds." }));
    const server = createServerText(i18n);
    expect(server.render("설치자 문구 20", [t("설치자 문구 {seconds}", { seconds: 20 })])).toBe("설치자 문구 20");
  });

  test("no parts: same as text(value)", () => {
    const i18n = createI18n({ language: "en", bundled });
    applyServerCatalog(i18n, catalog("en", { 안녕: "Hello" }));
    const server = createServerText(i18n);
    expect(server.render("안녕")).toBe("Hello");
    expect(server.render("안녕", [])).toBe("Hello");
    expect(server.render("몰라", null)).toBe("몰라");
  });

  test("language switch ko -> en -> ko (I-18): the source language never shows English", async () => {
    const fetchCatalog = async (language: string) =>
      language === "en" ? catalog("en", { 제목: "Title", "{n}개": "{n} items" }) : catalog("ko", { "English original": "한국어 번역" });
    const i18n = createI18n({ language: "ko", bundled, sourceLanguage: "ko" });
    await setLanguage(i18n, "ko", { fetchCatalog });
    const server = () => createServerText(i18n);
    expect(server().text("제목")).toBe("제목");
    await setLanguage(i18n, "en", { fetchCatalog });
    expect(server().text("제목")).toBe("Title");
    expect(server().render("3개", [t("{n}개", { n: 3 })])).toBe("3 items");
    await setLanguage(i18n, "ko", { fetchCatalog });
    expect(server().text("제목")).toBe("제목");
    expect(server().render("3개", [t("{n}개", { n: 3 })])).toBe("3개");
    expect(server().text("English original")).toBe("한국어 번역");
  });

  test("without a source language the whole chain is read (old server)", async () => {
    const i18n = createI18n({ language: "en", bundled });
    applyServerCatalog(i18n, catalog("en", { 제목: "Title" }));
    await i18n.changeLanguage("ko");
    expect(createServerText(i18n).text("제목")).toBe("Title");
  });

  test("a user language before the source language also loads the fallback server catalog", async () => {
    const asked: string[] = [];
    const i18n = createI18n({ language: "en", bundled: { ...bundled, fr: { app: { a: "A" } } } });
    await setLanguage(i18n, "fr", {
      sourceLanguage: "ko",
      fetchCatalog: async (language) => {
        asked.push(language);
        return catalog(language, language === "en" ? { 제목: "Title" } : {});
      },
    });
    expect(asked.sort()).toEqual(["en", "fr"]);
    expect(createServerText(i18n).text("제목")).toBe("Title");
  });
});
