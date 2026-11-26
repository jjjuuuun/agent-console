import { createI18n, type Console18n, type MissingHandler } from "@agent-console/i18n";
import type { SafeStorage } from "../app/storage";
import { bootBundles, bundledLanguages, loadBundled } from "./bundles";
import { FALLBACK_LANGUAGE, resolveBootLanguage } from "./languageStorage";

export interface CreateAppI18nOptions {
  storage: SafeStorage;
  /** `navigator.languages`(생략하면 브라우저 값) */
  browser?: readonly string[];
  /** 빠진 키·값 처리(테스트는 실패로 만든다) */
  onMissing?: MissingHandler;
}

/**
 * 앱의 i18n 인스턴스. 첫 화면 언어(저장된 언어 → 브라우저 언어 → `en`)로 시작하고, 그 언어의 부팅 묶음은 동기로 들어 있다.
 * 나머지 앱 묶음·라이브러리 묶음은 `setLanguage`가 내려받는다(`loadBundled`).
 */
export function createAppI18n({ storage, browser = browserLanguages(), onMissing }: CreateAppI18nOptions): Console18n {
  const language = resolveBootLanguage({ storage, browser, bundled: bundledLanguages() });
  return createI18n({
    language,
    fallbackLanguage: FALLBACK_LANGUAGE,
    bundled: bootBundles(),
    loadBundled,
    ...(onMissing ? { onMissing } : {}),
  });
}

/** `navigator.languages`(없으면 `navigator.language`, 그것도 없으면 빈 목록). */
export function browserLanguages(): readonly string[] {
  if (typeof navigator === "undefined") return [];
  if (navigator.languages.length > 0) return navigator.languages;
  return navigator.language ? [navigator.language] : [];
}
