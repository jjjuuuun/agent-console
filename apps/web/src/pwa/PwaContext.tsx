import { createContext, useContext, useMemo, useSyncExternalStore, type ReactNode } from "react";
import type { InstallSnapshot, InstallStore } from "./installPrompt";

/** 서비스 워커 새 버전 알림 원천(`virtual:pwa-register`를 감싼 어댑터를 `main.tsx`가 주입한다). */
export interface UpdateSource {
  /** 새 버전이 설치되어 대기 중인가 */
  getSnapshot(): boolean;
  subscribe(listener: () => void): () => void;
  /** 대기 중인 버전을 적용하고 새로고침한다 */
  apply(): void;
}

export interface PwaServices {
  /** 설치 안내 상태. `beforeinstallprompt`는 일찍 올 수 있어 앱 시작 때 만들어 넣는다 */
  install: InstallStore | null;
  update: UpdateSource | null;
}

const PwaContext = createContext<PwaServices>({ install: null, update: null });

/** PWA 서비스(설치 안내·업데이트 알림)를 공급한다. 없으면 해당 기능이 꺼진 것으로 본다. */
export function PwaProvider({ services, children }: { services: PwaServices; children: ReactNode }) {
  return <PwaContext.Provider value={services}>{children}</PwaContext.Provider>;
}

const NEVER = () => false;
const NO_SUBSCRIBE = () => () => {};

export function usePwaUpdate(): { available: boolean; apply: () => void } {
  const source = useContext(PwaContext).update;
  const available = useSyncExternalStore(source?.subscribe ?? NO_SUBSCRIBE, source?.getSnapshot ?? NEVER, NEVER);
  return { available, apply: () => source?.apply() };
}

export interface PwaInstall extends InstallSnapshot {
  install: () => Promise<"accepted" | "dismissed" | "unavailable">;
}

const EMPTY: InstallSnapshot = { standalone: false, canPrompt: false, dismissed: false };

export function usePwaInstall(): PwaInstall {
  const store = useContext(PwaContext).install;
  const snapshot = useSyncExternalStore(store?.subscribe ?? NO_SUBSCRIBE, store?.getSnapshot ?? (() => EMPTY), () => EMPTY);
  return useMemo(() => ({ ...snapshot, install: async () => (store === null ? "unavailable" : store.install()) }), [snapshot, store]);
}
