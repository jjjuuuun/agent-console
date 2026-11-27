import type { I18nInfo } from "@agent-console/contracts/i18n";
import { availableLanguages, languageName, matchLanguage } from "@agent-console/i18n";

/** 언어 고르기 목록의 한 줄(빠른 이동 등 목록 모양 화면용). `code`가 null이면 "자동"이다. */
export interface LanguageChoice {
  code: string | null;
  /** 그 언어 자신의 이름(`Intl.DisplayNames`, 자동이면 빈 문자열 — 호출 쪽이 문구를 붙인다) */
  name: string;
  /** 지금 설정된 값인가 */
  current: boolean;
  /** 일부만 번역됨 */
  partial: boolean;
}

const byCode = new Intl.Collator("en", { numeric: true });

/**
 * 언어 선택지를 만든다: 자동 + (앱 묶음 ∪ 서버 목록)을 코드순으로(언어를 바꿔도 줄이 움직이지 않는다).
 * @param bundled 앱이 묶어 둔 언어
 * @param info 서버 언어 목록(없으면 null)
 * @param preference 설정 문서의 `ui.language`(null = 자동, undefined = 아직 모름 → 자동으로 본다)
 */
export function languageChoices(bundled: readonly string[], info: I18nInfo | null, preference: string | null | undefined): LanguageChoice[] {
  const available = availableLanguages(bundled, info);
  const byServer = new Map((info?.languages ?? []).map((l) => [l.code, l]));
  const saved = typeof preference === "string" ? (matchLanguage(preference, available) ?? preference) : null;
  const rows: LanguageChoice[] = [...available].sort(byCode.compare).map((code) => ({
    code,
    name: languageName(code),
    current: saved === code,
    partial: byServer.get(code)?.complete === false,
  }));
  return [{ code: null, name: "", current: saved === null, partial: false }, ...rows];
}
