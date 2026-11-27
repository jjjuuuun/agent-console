import { createContext, useContext } from "react";
import type { I18nInfo } from "@agent-console/contracts/i18n";
import { languageName, useT } from "@agent-console/i18n";
import type { LanguageController, LanguageState } from "./languageController";

/** 언어 고르기 화면이 읽는 값. 서버 언어 목록 상태와 앱이 묶어 둔 언어를 함께 준다. */
export interface LanguageContextValue {
  state: LanguageState;
  /** 서버 언어 목록: `loading` 응답 전, `ready` 받음, `unavailable` 서버에 이 기능이 없거나 실패 */
  infoStatus: "loading" | "ready" | "unavailable";
  info: I18nInfo | null;
  bundled: readonly string[];
  /** 브라우저 언어 */
  browser: readonly string[];
  select: LanguageController["select"];
  retrySave: LanguageController["retrySave"];
}

export const LanguageContext = createContext<LanguageContextValue | null>(null);

/** 언어 상태를 읽는다. 공급자 밖이면 null(설정 화면이 서버 없이 쓰일 때를 위해 오류로 만들지 않는다). */
export function useLanguage(): LanguageContextValue | null {
  return useContext(LanguageContext);
}

/** 사용자가 언어를 바꾼 뒤 새 언어 문구로 한 번 알린다(토스트 없음, §3-8). 부팅 때 자동으로 바뀐 것은 알리지 않는다. */
export function LanguageAnnouncer({ announcement }: { announcement: LanguageState["announcement"] }) {
  const t = useT("settings");
  return (
    <div role="status" aria-live="polite" className="ac-sr-only" data-testid="language-announcer">
      {announcement === null ? "" : t("language.changed", { name: languageName(announcement.language) })}
    </div>
  );
}
