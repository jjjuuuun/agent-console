import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { THEME_CYCLE, ThemeProvider, nextTheme, useTheme } from "./theme";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** `prefers-color-scheme: light` 질의를 흉내 낸다. `setLight`가 변경 이벤트를 낸다. */
function stubMatchMedia(initialLight: boolean) {
  let light = initialLight;
  const listeners = new Set<() => void>();
  vi.stubGlobal("matchMedia", (query: string) => ({
    get matches() {
      return query.includes("light") && light;
    },
    media: query,
    addEventListener: (_: string, l: () => void) => listeners.add(l),
    removeEventListener: (_: string, l: () => void) => listeners.delete(l),
  }));
  window.matchMedia = globalThis.matchMedia;
  return {
    setLight(next: boolean) {
      light = next;
      act(() => listeners.forEach((l) => l()));
    },
  };
}

function Probe() {
  const { theme, resolved } = useTheme();
  return <p>{`${theme}/${resolved}`}</p>;
}

describe("테마 기본값과 순환", () => {
  it("컨텍스트 기본값은 system이다", () => {
    render(<Probe />);
    expect(screen.getByText("system/dark")).toBeTruthy();
  });
  it("순환은 시스템 -> 라이트 -> 다크 -> 시스템", () => {
    expect(THEME_CYCLE).toEqual(["system", "light", "dark"]);
    expect(nextTheme("system")).toBe("light");
    expect(nextTheme("light")).toBe("dark");
    expect(nextTheme("dark")).toBe("system");
  });
});

describe("OS 변경 반영", () => {
  it("system이면 OS 선호가 바뀔 때 resolved가 즉시 따라가고, 직접 고르면 고정된다", () => {
    const os = stubMatchMedia(false);
    const target = document.createElement("div");
    const { rerender } = render(
      <ThemeProvider theme="system" onThemeChange={() => {}} target={target}>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByText("system/dark")).toBeTruthy();
    expect(target.hasAttribute("data-theme")).toBe(false);
    os.setLight(true);
    expect(screen.getByText("system/light")).toBeTruthy();
    rerender(
      <ThemeProvider theme="dark" onThemeChange={() => {}} target={target}>
        <Probe />
      </ThemeProvider>,
    );
    os.setLight(false);
    os.setLight(true);
    expect(screen.getByText("dark/dark")).toBeTruthy();
    expect(target.getAttribute("data-theme")).toBe("dark");
  });
});
