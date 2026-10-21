import type { SafeStorage } from "../app/storage";

/** 브라우저가 주는 설치 안내 이벤트(표준 외 API라 필요한 부분만 정의). */
export interface BeforeInstallPromptEventLike extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export interface InstallEnvironment {
  addEventListener(type: string, listener: (event: Event) => void): void;
  removeEventListener(type: string, listener: (event: Event) => void): void;
  /** 독립 창(`display-mode: standalone`)으로 실행 중인지 */
  isStandalone(): boolean;
}

export interface InstallSnapshot {
  /** 앱으로 설치되어 독립 창에서 실행 중 */
  standalone: boolean;
  /** 브라우저가 설치 이벤트를 줘서 [앱으로 설치]를 누를 수 있다 */
  canPrompt: boolean;
  /** 사용자가 설치 안내를 거부했다(사이드바 버튼은 숨기고 설정 화면에만 남긴다) */
  dismissed: boolean;
}

export const INSTALL_DISMISSED_KEY = "ac.pwa.install.dismissed";

export interface InstallStore {
  getSnapshot(): InstallSnapshot;
  subscribe(listener: () => void): () => void;
  /** 브라우저 설치 창을 연다. 이벤트가 없으면 "unavailable". 거부하면 이력을 저장한다. */
  install(): Promise<"accepted" | "dismissed" | "unavailable">;
  dispose(): void;
}

/**
 * PWA 설치 안내 상태(React 비의존). `beforeinstallprompt`를 붙잡아 두었다가 버튼에서 `prompt()`를 부른다.
 * 이벤트를 주지 않는 브라우저에서는 `canPrompt`가 계속 false이므로 화면이 수동 안내문만 보인다.
 */
export function createInstallStore(env: InstallEnvironment, storage: SafeStorage): InstallStore {
  let deferred: BeforeInstallPromptEventLike | null = null;
  let dismissed = storage.get(INSTALL_DISMISSED_KEY) !== null;
  let installed = false;
  let snapshot: InstallSnapshot = compute();
  const listeners = new Set<() => void>();

  function compute(): InstallSnapshot {
    return { standalone: installed || env.isStandalone(), canPrompt: deferred !== null, dismissed };
  }
  function update() {
    const next = compute();
    if (next.standalone === snapshot.standalone && next.canPrompt === snapshot.canPrompt && next.dismissed === snapshot.dismissed) return;
    snapshot = next;
    listeners.forEach((l) => l());
  }

  const onPrompt = (event: Event) => {
    event.preventDefault(); // 브라우저 기본 미니 안내를 막고 우리 버튼으로 연다
    deferred = event as BeforeInstallPromptEventLike;
    update();
  };
  const onInstalled = () => {
    installed = true;
    deferred = null;
    update();
  };
  env.addEventListener("beforeinstallprompt", onPrompt);
  env.addEventListener("appinstalled", onInstalled);

  return {
    getSnapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    async install() {
      const event = deferred;
      if (event === null) return "unavailable";
      deferred = null; // 이벤트는 한 번만 쓸 수 있다
      update();
      await event.prompt();
      const { outcome } = await event.userChoice;
      if (outcome === "dismissed") {
        dismissed = true;
        storage.set(INSTALL_DISMISSED_KEY, "1");
        update();
      }
      return outcome;
    },
    dispose() {
      env.removeEventListener("beforeinstallprompt", onPrompt);
      env.removeEventListener("appinstalled", onInstalled);
      listeners.clear();
    },
  };
}

/** 브라우저 `window`에서 환경을 만든다. */
export function browserInstallEnvironment(win: Window & typeof globalThis = window): InstallEnvironment {
  return {
    addEventListener: (type, listener) => win.addEventListener(type, listener),
    removeEventListener: (type, listener) => win.removeEventListener(type, listener),
    isStandalone: () =>
      (typeof win.matchMedia === "function" && win.matchMedia("(display-mode: standalone)").matches) ||
      (win.navigator as Navigator & { standalone?: boolean }).standalone === true,
  };
}
