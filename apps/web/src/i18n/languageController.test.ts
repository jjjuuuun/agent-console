import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { I18nInfo, MessageCatalog } from "@agent-console/contracts/i18n";
import { createI18n } from "@agent-console/i18n";
import { createSafeStorage } from "../app/storage";
import { createLanguageController, type LanguageControllerDeps } from "./languageController";
import { LANGUAGE_STORAGE_KEY } from "./languageStorage";

const bundles = { en: { app: { hi: "Hello" } }, ko: { app: { hi: "안녕" } } };
const info = (codes: string[], def = "en"): I18nInfo => ({
  languages: codes.map((code) => ({ code, sources: [], complete: true })),
  default_language: def,
  fallback_language: "en",
});

function setup(overrides: Partial<LanguageControllerDeps> = {}, start = "ko") {
  const store = new Map<string, string>();
  const storage = createSafeStorage({
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    key: (i: number) => [...store.keys()][i] ?? null,
    get length() {
      return store.size;
    },
  } as Storage);
  const i18n = createI18n({ language: start, bundled: bundles });
  const docLang: string[] = [];
  const controller = createLanguageController({
    i18n,
    storage,
    browser: () => ["ko-KR"],
    bundled: ["en", "ko"],
    setDocumentLanguage: (l) => docLang.push(l),
    ...overrides,
  });
  return { controller, i18n, store, docLang };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("언어 컨트롤러", () => {
  it("고르면 한 번에 바꾸고(문구·html lang·저장소) 저장한다. 선택 표시는 즉시, 화면 언어는 준비 뒤", async () => {
    const save = vi.fn(async () => undefined);
    const { controller, i18n, store, docLang } = setup({ save });
    controller.sync({ preference: "ko", info: null });
    await vi.advanceTimersByTimeAsync(0);
    controller.select("en");
    expect(controller.getState().pending).toBe("en");
    expect(i18n.t("hi", { ns: "app" })).toBe("안녕"); // 아직 이전 언어(섞이지 않음)
    await vi.advanceTimersByTimeAsync(250);
    expect(i18n.language).toBe("en");
    expect(i18n.t("hi", { ns: "app" })).toBe("Hello");
    expect(docLang).toContain("en");
    expect(store.get(LANGUAGE_STORAGE_KEY)).toBe("en");
    expect(save).toHaveBeenCalledWith("en");
    const state = controller.getState();
    expect(state).toMatchObject({ language: "en", pending: undefined, preference: "en", saveFailed: false });
    expect(state.announcement).toMatchObject({ language: "en" });
  });

  it("250ms 안의 연타는 마지막 선택만 처리한다(en → ko → en)", async () => {
    const save = vi.fn(async () => undefined);
    const { controller, i18n } = setup({ save }, "en");
    controller.sync({ preference: "en", info: null });
    await vi.advanceTimersByTimeAsync(0);
    controller.select("ko");
    await vi.advanceTimersByTimeAsync(100);
    controller.select("en"); // 현재 값과 같지만 pending(ko)과 다르므로 마지막 선택이 된다
    await vi.advanceTimersByTimeAsync(300);
    expect(i18n.language).toBe("en");
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("en");
  });

  it("낡은 응답이 늦게 와도 마지막 선택이 이긴다", async () => {
    const slow = new Promise<MessageCatalog | null>((resolve) => setTimeout(() => resolve(null), 1000));
    const fetchCatalog = vi.fn((language: string) => (language === "ko" ? slow : Promise.resolve(null)));
    const { controller, i18n } = setup({ fetchCatalog, save: async () => undefined }, "en");
    controller.sync({ preference: "en", info: null });
    await vi.advanceTimersByTimeAsync(0);
    controller.select("ko");
    await vi.advanceTimersByTimeAsync(260); // ko 적용 시작(서버 묶음 대기 중)
    controller.select("en");
    await vi.advanceTimersByTimeAsync(260);
    await vi.advanceTimersByTimeAsync(2000);
    expect(i18n.language).toBe("en");
    expect(controller.getState().pending).toBeUndefined();
  });

  it("같은 값이면 아무 일도 없다", async () => {
    const save = vi.fn(async () => undefined);
    const { controller } = setup({ save });
    controller.sync({ preference: "ko", info: null });
    await vi.advanceTimersByTimeAsync(0);
    controller.select("ko");
    await vi.advanceTimersByTimeAsync(500);
    expect(save).not.toHaveBeenCalled();
    expect(controller.getState().pending).toBeUndefined();
  });

  it("자동(null)은 브라우저 언어 → 서버 기본 → en으로 푼다", async () => {
    const { controller, i18n } = setup({ browser: () => ["fr", "en-US"] }, "ko");
    controller.sync({ preference: "ko", info: null });
    await vi.advanceTimersByTimeAsync(0);
    controller.select(null);
    await vi.advanceTimersByTimeAsync(300);
    expect(i18n.language).toBe("en");
    expect(controller.getState().preference).toBeNull();
  });

  it("저장이 실패해도 화면은 새 언어이고 saveFailed + 다시 시도가 된다", async () => {
    let fail = true;
    const save = vi.fn(async () => {
      if (fail) throw new Error("500");
    });
    const { controller, i18n } = setup({ save });
    controller.sync({ preference: "ko", info: null });
    await vi.advanceTimersByTimeAsync(0);
    controller.select("en");
    await vi.advanceTimersByTimeAsync(300);
    expect(i18n.language).toBe("en");
    expect(controller.getState().saveFailed).toBe(true);
    fail = false;
    controller.retrySave();
    await vi.advanceTimersByTimeAsync(0);
    expect(controller.getState().saveFailed).toBe(false);
    expect(save).toHaveBeenCalledTimes(2);
  });

  it("서버 묶음이 실패하면 앱 묶음만 바뀌고 serverTextFailed", async () => {
    const { controller, i18n } = setup({ fetchCatalog: () => Promise.reject(new Error("down")), save: async () => undefined });
    controller.sync({ preference: "ko", info: null });
    await vi.advanceTimersByTimeAsync(0);
    controller.select("en");
    await vi.advanceTimersByTimeAsync(300);
    expect(i18n.language).toBe("en");
    expect(controller.getState().serverTextFailed).toBe(true);
  });

  it("서버 묶음이 5초 안에 안 오면 앱 묶음만 바꾼다", async () => {
    const hang = () => new Promise<MessageCatalog | null>(() => undefined);
    const { controller, i18n } = setup({ fetchCatalog: hang, save: async () => undefined });
    controller.sync({ preference: "ko", info: null });
    await vi.advanceTimersByTimeAsync(5100);
    expect(i18n.language).toBe("ko");
    controller.select("en");
    await vi.advanceTimersByTimeAsync(250 + 5100);
    expect(i18n.language).toBe("en");
    expect(controller.getState().serverTextFailed).toBe(true);
  });

  it("첫 맞춤(sync): 설정값이 있으면 그 언어로 조용히 바꾼다(알림·저장 없음)", async () => {
    const save = vi.fn(async () => undefined);
    const { controller, i18n, store } = setup({ save }, "ko");
    controller.sync({ preference: "en", info: null });
    await vi.advanceTimersByTimeAsync(0);
    expect(i18n.language).toBe("en");
    expect(store.get(LANGUAGE_STORAGE_KEY)).toBe("en");
    expect(save).not.toHaveBeenCalled();
    expect(controller.getState().announcement).toBeNull();
  });

  it("서버가 더한 언어(앱 묶음 없음)도 고를 수 있다. 서버 묶음이 문구를 준다", async () => {
    const catalog: MessageCatalog = { language: "de", text: {}, codes: {}, ns: { app: { hi: "Hallo" } } };
    const { controller, i18n } = setup({ fetchCatalog: async () => catalog, save: async () => undefined });
    controller.sync({ preference: "ko", info: info(["de", "en", "ko"]) });
    await vi.advanceTimersByTimeAsync(0);
    controller.select("de");
    await vi.advanceTimersByTimeAsync(300);
    expect(i18n.language).toBe("de");
    expect(i18n.t("hi", { ns: "app" })).toBe("Hallo");
  });

  it("저장된 언어를 쓸 수 없으면(목록에 없음) 자동으로 푼다", async () => {
    const { controller, i18n } = setup({ browser: () => ["en"] }, "ko");
    controller.sync({ preference: "zz", info: null });
    await vi.advanceTimersByTimeAsync(0);
    expect(i18n.language).toBe("en");
    expect(controller.getState().preference).toBe("zz");
  });

  it("고르는 중에는 sync가 선택을 덮지 않는다", async () => {
    const { controller, i18n } = setup({ save: async () => undefined }, "ko");
    controller.sync({ preference: "ko", info: null });
    await vi.advanceTimersByTimeAsync(0);
    controller.select("en");
    controller.sync({ preference: "ko", info: info(["en", "ko"]) });
    await vi.advanceTimersByTimeAsync(300);
    expect(i18n.language).toBe("en");
  });
});
