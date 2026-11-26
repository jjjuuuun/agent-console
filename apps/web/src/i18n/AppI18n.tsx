import { createContext, useContext, type ReactNode } from "react";
import { I18nProvider, type Console18n } from "@agent-console/i18n";

const AppI18nContext = createContext<Console18n | null>(null);

/**
 * 앱의 i18n 인스턴스를 하위에 공급한다(`useT` 등 패키지 훅과, 공급자가 있을 때만 번역하는 앱 컴포넌트용).
 * 공급자 밖에서 그려지는 컴포넌트(단독 테스트 등)는 `useOptionalI18n()`이 null이라 기본 문구(한국어)로 남는다.
 */
export function AppI18nProvider({ i18n, children }: { i18n: Console18n; children: ReactNode }) {
  return (
    <AppI18nContext.Provider value={i18n}>
      <I18nProvider i18n={i18n}>{children}</I18nProvider>
    </AppI18nContext.Provider>
  );
}

/** 앱 i18n 인스턴스. 공급자 밖이면 null. */
export function useOptionalI18n(): Console18n | null {
  return useContext(AppI18nContext);
}
