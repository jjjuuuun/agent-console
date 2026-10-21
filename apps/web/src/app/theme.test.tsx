import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { createFakeClients } from "../testing/fakes";
import { buildAppRoutes, preloadScreens } from "../shell/routes";
import { AppRoot, readTheme, THEME_STORAGE_KEY } from "./AppRoot";
import { createAppQueryClient } from "./queries";
import { createSafeStorage } from "./storage";
import { applyThemeColor, THEME_COLORS } from "./themeColor";

beforeAll(preloadScreens, 120_000);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-theme");
});

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return createSafeStorage({
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  } as unknown as Storage);
}

function stubOs(initialLight: boolean) {
  let light = initialLight;
  const listeners = new Set<() => void>();
  const mm = (query: string) => ({
    get matches() {
      return query.includes("light") && light;
    },
    media: query,
    addEventListener: (_: string, l: () => void) => listeners.add(l),
    removeEventListener: (_: string, l: () => void) => listeners.delete(l),
  });
  vi.stubGlobal("matchMedia", mm);
  window.matchMedia = mm as unknown as typeof window.matchMedia;
  return {
    set(next: boolean) {
      light = next;
      listeners.forEach((l) => l());
    },
  };
}

function mount(storage: ReturnType<typeof memoryStorage>) {
  const { clients } = createFakeClients();
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: ["/settings"] });
  return render(<AppRoot createClients={async () => clients} router={router} storage={storage} queryClient={createAppQueryClient({ retry: false })} />);
}

const toggle = () => screen.findByRole("button", { name: /^테마: / });

describe("readTheme", () => {
  it("저장값이 없거나 알 수 없으면 system", () => {
    expect(readTheme(memoryStorage())).toBe("system");
    expect(readTheme(memoryStorage({ [THEME_STORAGE_KEY]: "neon" }))).toBe("system");
    expect(readTheme(memoryStorage({ [THEME_STORAGE_KEY]: "light" }))).toBe("light");
  });
});

describe("테마 흐름", () => {
  it("저장값 없음: data-theme 없이 시작하고 툴팁이 현재와 다음 상태를 말한다", async () => {
    stubOs(true);
    mount(memoryStorage());
    expect((await toggle()).getAttribute("aria-label")).toBe("테마: 시스템(누르면 라이트)");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("선택 후 복원, 시스템으로 되돌리기(저장값 system), OS 변경은 즉시 반영", { timeout: 60_000 }, async () => {
    const os = stubOs(false);
    const storage = memoryStorage();
    const first = mount(storage);
    fireEvent.click(await toggle());
    await waitFor(() => expect(document.documentElement.getAttribute("data-theme")).toBe("light"));
    expect(storage.get(THEME_STORAGE_KEY)).toBe("light");
    fireEvent.click(await toggle());
    await waitFor(() => expect(document.documentElement.getAttribute("data-theme")).toBe("dark"));
    // 새로고침: 같은 저장소로 다시 마운트하면 직접 고른 값이 복원된다
    first.unmount();
    document.documentElement.removeAttribute("data-theme");
    mount(storage);
    await waitFor(() => expect(document.documentElement.getAttribute("data-theme")).toBe("dark"));
    expect((await toggle()).getAttribute("aria-label")).toBe("테마: 다크(누르면 시스템)");
    // 다크 -> 시스템
    fireEvent.click(await toggle());
    await waitFor(() => expect(document.documentElement.hasAttribute("data-theme")).toBe(false));
    expect(storage.get(THEME_STORAGE_KEY)).toBe("system");
    // OS 변경: 속성이 없으므로 CSS가 따르고, theme-color 메타는 각자 색을 유지한다
    os.set(true);
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });
});

describe("theme-color", () => {
  it("직접 고르면 두 메타가 같은 색, 시스템이면 각자 색", () => {
    document.head.insertAdjacentHTML(
      "beforeend",
      '<meta name="theme-color" id="tc-d" media="(prefers-color-scheme: dark)" content="x"><meta name="theme-color" id="tc-l" media="(prefers-color-scheme: light)" content="x">',
    );
    const d = document.getElementById("tc-d")!;
    const l = document.getElementById("tc-l")!;
    applyThemeColor(document, "light");
    expect([d.getAttribute("content"), l.getAttribute("content")]).toEqual([THEME_COLORS.light, THEME_COLORS.light]);
    applyThemeColor(document, "system");
    expect([d.getAttribute("content"), l.getAttribute("content")]).toEqual([THEME_COLORS.dark, THEME_COLORS.light]);
    d.remove();
    l.remove();
  });

  it("index.html의 메타 값과 렌더 전 스크립트 색이 THEME_COLORS와 같다", () => {
    const html = readFileSync(join(process.cwd(), "apps/web/index.html"), "utf8");
    expect(html).toContain(`content="${THEME_COLORS.dark}" media="(prefers-color-scheme: dark)"`);
    expect(html).toContain(`content="${THEME_COLORS.light}" media="(prefers-color-scheme: light)"`);
    expect(html).toContain(`"light" ? "${THEME_COLORS.light}" : "${THEME_COLORS.dark}"`);
    expect(html).toContain("agent-console.theme");
  });
});
