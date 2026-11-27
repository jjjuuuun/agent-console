import { describe, expect, it } from "vitest";
import { languageChoices } from "./languageChoices";

describe("languageChoices", () => {
  it("자동이 맨 앞이고 언어는 코드순이다", () => {
    const rows = languageChoices(["ko", "en"], null, null);
    expect(rows.map((r) => r.code)).toEqual([null, "en", "ko"]);
  });
  it("저장된 값이 현재이고, 없으면(null) 자동이 현재다", () => {
    expect(languageChoices(["ko", "en"], null, "ko").filter((r) => r.current).map((r) => r.code)).toEqual(["ko"]);
    expect(languageChoices(["ko", "en"], null, null).filter((r) => r.current).map((r) => r.code)).toEqual([null]);
  });
  it("서버 목록에만 있는 언어도 더하고, 일부만 번역된 언어를 표시한다", () => {
    const info = { default_language: "en", fallback_language: "en", languages: [{ code: "de", name: "Deutsch", complete: false, sources: ["x"] }] };
    const rows = languageChoices(["en"], info as never, undefined);
    expect(rows.map((r) => r.code)).toEqual([null, "de", "en"]);
    expect(rows.find((r) => r.code === "de")?.partial).toBe(true);
  });
});
