import { createContext, useContext, useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";

export type ThemeChoice = "dark" | "light" | "system";

/** 3상태 순환 순서(시스템 -> 라이트 -> 다크). 순환 버튼은 모두 이 상수를 쓴다. */
export const THEME_CYCLE: readonly ThemeChoice[] = ["system", "light", "dark"];

/** 순환에서 `theme` 다음 상태. */
export function nextTheme(theme: ThemeChoice): ThemeChoice {
  return THEME_CYCLE[(THEME_CYCLE.indexOf(theme) + 1) % THEME_CYCLE.length] ?? "system";
}

/** 실제로 칠해지는 색 구성. "system"이면 OS 선호. */
export type ResolvedTheme = "dark" | "light";

const LIGHT_QUERY = "(prefers-color-scheme: light)";

function subscribeSystem(onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
  const mql = window.matchMedia(LIGHT_QUERY);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}

function systemIsLight(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(LIGHT_QUERY).matches;
}

export interface ThemeContextValue {
  theme: ThemeChoice;
  /** 실제 적용된 색 구성. "system"이면 OS 선호를 따라 바뀐다 */
  resolved: ResolvedTheme;
  /** 사용자가 테마를 바꾸려 할 때 호출. 저장은 앱이 한다. */
  setTheme: (theme: ThemeChoice) => void;
}

const ThemeContext = createContext<ThemeContextValue>({ theme: "system", resolved: "dark", setTheme: () => {} });

export interface ThemeProviderProps {
  theme: ThemeChoice;
  onThemeChange: (theme: ThemeChoice) => void;
  /** 속성을 적용할 요소. 기본은 문서 루트(<html>). 테스트·미리보기에서 주입한다. */
  target?: HTMLElement;
  children?: ReactNode;
}

/** `data-theme`를 적용한다("system"이면 속성 제거 → prefers-color-scheme). 저장·복원은 하지 않는다. */
export function ThemeProvider({ theme, onThemeChange, target, children }: ThemeProviderProps) {
  useEffect(() => {
    const el = target ?? document.documentElement;
    if (theme === "system") el.removeAttribute("data-theme");
    else el.setAttribute("data-theme", theme);
  }, [theme, target]);
  const systemLight = useSyncExternalStore(subscribeSystem, systemIsLight, () => false);
  const resolved: ResolvedTheme = theme === "system" ? (systemLight ? "light" : "dark") : theme;
  const value = useMemo(() => ({ theme, resolved, setTheme: onThemeChange }), [theme, resolved, onThemeChange]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}

/** 해석된 CSS 변수 값(xterm 테마처럼 var()를 못 읽는 곳에 넘길 때). 이름은 `--ac-bg` 형태. */
export function getResolvedTokens(names: string[], element: Element = document.documentElement): Record<string, string> {
  const style = getComputedStyle(element);
  const out: Record<string, string> = {};
  for (const n of names) out[n] = style.getPropertyValue(n).trim();
  return out;
}
