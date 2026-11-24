import { useCallback, useMemo, useState } from "react";
import { readJson, type SafeStorage } from "../../app/storage";
import { useMediaQuery } from "../../lib/useMediaQuery";

/** 접힌 묶음 id 목록을 저장하는 키 */
export const NAV_COLLAPSED_KEY = "settings.nav.collapsed";
/** 좁은 폭 기준을 담은 CSS 사용자 정의 속성(`styles/app.css`) */
export const NARROW_BELOW_VAR = "--app-settings-narrow-below";
const NARROW_BELOW_FALLBACK = 1100;

/** 접힌 묶음 상태. 저장소는 주입한다(깨진 값은 빈 목록). */
export function useCollapsedGroups(storage: SafeStorage): { collapsed: ReadonlySet<string>; toggle: (group: string) => void } {
  const [list, setList] = useState<string[]>(() => {
    const raw = readJson<unknown>(storage, NAV_COLLAPSED_KEY, []);
    return Array.isArray(raw) ? raw.filter((v): v is string => typeof v === "string") : [];
  });
  const toggle = useCallback(
    (group: string) =>
      setList((prev) => {
        const next = prev.includes(group) ? prev.filter((g) => g !== group) : [...prev, group];
        storage.set(NAV_COLLAPSED_KEY, JSON.stringify(next));
        return next;
      }),
    [storage],
  );
  const collapsed = useMemo(() => new Set(list), [list]);
  return { collapsed, toggle };
}

/** CSS 사용자 정의 속성의 px 값(없거나 읽을 수 없으면 `fallback`). */
export function readCssPx(name: string, fallback: number): number {
  if (typeof document === "undefined") return fallback;
  const n = Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name));
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

/** 뷰포트가 CSS 속성이 정한 폭 미만이면 true(좁은 폭: 섹션 목록 대신 드롭다운). */
export function useNarrowViewport(): boolean {
  const below = useMemo(() => readCssPx(NARROW_BELOW_VAR, NARROW_BELOW_FALLBACK), []);
  return useMediaQuery(`(max-width: ${below - 1}px)`);
}
