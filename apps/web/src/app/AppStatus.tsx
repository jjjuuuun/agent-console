import { createContext, useContext, type ReactNode } from "react";

/** 앱 전체 상태(셸의 전역 배너가 읽는다). 값은 AppRoot가 정하고, 셸은 표시만 한다. */
export interface AppStatus {
  /** 서버가 토큰을 거부했다(401/403) */
  authRejected: boolean;
  /** 새로고침(테스트 주입 가능) */
  reload: () => void;
}

const AppStatusContext = createContext<AppStatus>({ authRejected: false, reload: () => {} });

export function AppStatusProvider({ value, children }: { value: AppStatus; children: ReactNode }) {
  return <AppStatusContext.Provider value={value}>{children}</AppStatusContext.Provider>;
}

export function useAppStatus(): AppStatus {
  return useContext(AppStatusContext);
}
