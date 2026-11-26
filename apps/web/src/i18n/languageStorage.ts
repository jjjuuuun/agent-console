import { matchLanguage } from "@agent-console/i18n";
import type { SafeStorage } from "../app/storage";

/** 이 브라우저가 마지막으로 정한 실제 화면 언어를 기억하는 저장소 키(`index.html` 인라인 스크립트도 같은 키를 읽는다). */
export const LANGUAGE_STORAGE_KEY = "agent-console.language";

/** 앱 묶음에도 서버 묶음에도 없을 때의 마지막 언어(design §I18N I-8). */
export const FALLBACK_LANGUAGE = "en";

/** 저장된 언어 코드. 없거나 비었으면 undefined. */
export function readStoredLanguage(storage: SafeStorage): string | undefined {
  const raw = storage.get(LANGUAGE_STORAGE_KEY)?.trim();
  return raw === undefined || raw === "" ? undefined : raw;
}

/** 정해진 실제 언어를 기억한다(자동으로 정했어도 실제 언어 코드를 쓴다). */
export function writeStoredLanguage(storage: SafeStorage, language: string): void {
  storage.set(LANGUAGE_STORAGE_KEY, language);
}

export interface BootLanguageInput {
  storage: SafeStorage;
  /** `navigator.languages` */
  browser: readonly string[];
  /** 앱이 묶어 둔 언어(서버 언어는 아직 모른다) */
  bundled: readonly string[];
}

/**
 * 서버에 닿기 전 첫 화면의 언어(screen-i18n §4.1 단계 A).
 * 저장된 언어가 앱 묶음에 있으면 그것, 저장된 언어가 있지만 앱 묶음에 없으면(사용자 폴더 언어) 대체 언어,
 * 저장된 값이 없으면 브라우저 언어 중 앱 묶음에 있는 첫 언어, 없으면 대체 언어.
 */
export function resolveBootLanguage({ storage, browser, bundled }: BootLanguageInput): string {
  const stored = readStoredLanguage(storage);
  if (stored !== undefined) return matchLanguage(stored, bundled) ?? matchLanguage(FALLBACK_LANGUAGE, bundled) ?? FALLBACK_LANGUAGE;
  for (const code of browser) {
    const hit = matchLanguage(code, bundled);
    if (hit !== undefined) return hit;
  }
  return matchLanguage(FALLBACK_LANGUAGE, bundled) ?? FALLBACK_LANGUAGE;
}
