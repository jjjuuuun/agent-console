import { describe, expect, it, vi } from "vitest";
import { createSafeStorage } from "../app/storage";
import { createInstallStore, INSTALL_DISMISSED_KEY, type InstallEnvironment } from "./installPrompt";

function env(standalone = false) {
  const listeners = new Map<string, (e: Event) => void>();
  const environment: InstallEnvironment = {
    addEventListener: (t, l) => void listeners.set(t, l),
    removeEventListener: (t) => void listeners.delete(t),
    isStandalone: () => standalone,
  };
  return { environment, fire: (type: string, event: Event) => listeners.get(type)?.(event) };
}
function promptEvent(outcome: "accepted" | "dismissed") {
  const e = new Event("beforeinstallprompt", { cancelable: true }) as Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: typeof outcome }> };
  e.prompt = vi.fn(async () => {});
  e.userChoice = Promise.resolve({ outcome });
  return e;
}

describe("설치 안내 상태", () => {
  it("이벤트를 받으면 설치할 수 있고, 거부하면 이력이 남아 다시 묻지 않는다", async () => {
    const { environment, fire } = env();
    const storage = createSafeStorage(null);
    const store = createInstallStore(environment, storage);
    expect(store.getSnapshot()).toEqual({ standalone: false, canPrompt: false, dismissed: false });
    const ev = promptEvent("dismissed");
    fire("beforeinstallprompt", ev);
    expect(ev.defaultPrevented).toBe(true);
    expect(store.getSnapshot().canPrompt).toBe(true);
    expect(await store.install()).toBe("dismissed");
    expect(store.getSnapshot()).toEqual({ standalone: false, canPrompt: false, dismissed: true });
    expect(await store.install()).toBe("unavailable");
  });
  it("독립 창이면 standalone, 설치 완료 이벤트도 standalone으로 본다", () => {
    expect(createInstallStore(env(true).environment, createSafeStorage(null)).getSnapshot().standalone).toBe(true);
    const { environment, fire } = env();
    const store = createInstallStore(environment, createSafeStorage(null));
    fire("appinstalled", new Event("appinstalled"));
    expect(store.getSnapshot().standalone).toBe(true);
  });
  it("거부 이력은 저장소에서 복원된다", () => {
    const mem = new Map<string, string>([[INSTALL_DISMISSED_KEY, "1"]]);
    const storage = createSafeStorage({ getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => void mem.set(k, v), removeItem: (k: string) => void mem.delete(k), key: () => null, length: 0 } as unknown as Storage);
    expect(createInstallStore(env().environment, storage).getSnapshot().dismissed).toBe(true);
  });
});
