import { useEffect } from "react";
import { useTheme, type ResolvedTheme } from "@agent-console/ui";

/** `<meta name="theme-color">` 색. `index.html` 렌더 전 스크립트의 값과 같아야 한다(테스트가 비교). */
export const THEME_COLORS: Readonly<Record<ResolvedTheme, string>> = { dark: "#14161d", light: "#f5f4f0" };

/**
 * 메타 두 개(`media`로 OS 선호를 구분)에 색을 적용한다.
 * 직접 고른 값이면 두 메타를 모두 그 색으로, 시스템이면 각자의 원래 색으로 돌린다.
 */
export function applyThemeColor(doc: Document, choice: "system" | ResolvedTheme): void {
  const metas = doc.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]');
  metas.forEach((meta) => {
    const own: ResolvedTheme = meta.getAttribute("media")?.includes("light") === true ? "light" : "dark";
    meta.setAttribute("content", THEME_COLORS[choice === "system" ? own : choice]);
  });
}

/** 선택이 바뀔 때 `theme-color`를 맞춘다(화면을 그리지 않는다). */
export function ThemeColorSync() {
  const { theme } = useTheme();
  useEffect(() => applyThemeColor(document, theme), [theme]);
  return null;
}
