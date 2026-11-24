import { createContext, useContext, type ReactNode } from "react";
import { appSessionStorage, appStorage, type SafeStorage } from "./storage";

const StorageContext = createContext<SafeStorage>(appStorage);

/** 화면 상태 저장소(localStorage 래퍼)를 하위에 공급한다. 테스트는 메모리 저장소를 넣는다. */
export function StorageProvider({ storage, children }: { storage: SafeStorage; children: ReactNode }) {
  return <StorageContext.Provider value={storage}>{children}</StorageContext.Provider>;
}

export function useStorage(): SafeStorage {
  return useContext(StorageContext);
}

const SessionStorageContext = createContext<SafeStorage>(appSessionStorage);

/** 탭 세션 범위 저장소(sessionStorage 래퍼)를 하위에 공급한다. 테스트는 메모리 저장소를 넣는다. */
export function SessionStorageProvider({ storage, children }: { storage: SafeStorage; children: ReactNode }) {
  return <SessionStorageContext.Provider value={storage}>{children}</SessionStorageContext.Provider>;
}

export function useSessionStorage(): SafeStorage {
  return useContext(SessionStorageContext);
}
