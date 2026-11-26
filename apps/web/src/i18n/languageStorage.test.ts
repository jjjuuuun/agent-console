import { describe, expect, it } from "vitest";
import { createSafeStorage } from "../app/storage";
import { LANGUAGE_STORAGE_KEY, resolveBootLanguage } from "./languageStorage";

const memory = (initial: Record<string, string> = {}) => {
  const map = new Map(Object.entries(initial));
  return createSafeStorage({
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    key: (i: number) => [...map.keys()][i] ?? null,
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
  } as Storage);
};

describe("첫 화면 언어(저장된 언어 → 브라우저 언어 → en)", () => {
  const bundled = ["en", "ko"];
  it("저장된 언어가 앱 묶음에 있으면 그것(지역 코드는 주 언어로)", () => {
    expect(resolveBootLanguage({ storage: memory({ [LANGUAGE_STORAGE_KEY]: "en" }), browser: ["ko-KR"], bundled })).toBe("en");
    expect(resolveBootLanguage({ storage: memory({ [LANGUAGE_STORAGE_KEY]: "ko-KR" }), browser: ["en"], bundled })).toBe("ko");
  });
  it("저장값이 없으면 브라우저 언어 중 앱 묶음에 있는 첫 언어", () => {
    expect(resolveBootLanguage({ storage: memory(), browser: ["ko-KR"], bundled })).toBe("ko");
    expect(resolveBootLanguage({ storage: memory(), browser: ["en-US"], bundled })).toBe("en");
    expect(resolveBootLanguage({ storage: memory(), browser: ["fr", "ko"], bundled })).toBe("ko");
  });
  it("브라우저 언어가 모두 묶음에 없으면 en", () => {
    expect(resolveBootLanguage({ storage: memory(), browser: ["fr"], bundled })).toBe("en");
    expect(resolveBootLanguage({ storage: memory(), browser: [], bundled })).toBe("en");
  });
  it("저장된 언어가 앱 묶음에 없으면(사용자 폴더 언어) 대체 언어로 시작한다", () => {
    expect(resolveBootLanguage({ storage: memory({ [LANGUAGE_STORAGE_KEY]: "de" }), browser: ["ko-KR"], bundled })).toBe("en");
  });
  it("언어 목록은 인자다(묶음이 하나뿐이면 그 언어)", () => {
    expect(resolveBootLanguage({ storage: memory(), browser: ["ko"], bundled: ["xx-test"] })).toBe("en");
  });
});
