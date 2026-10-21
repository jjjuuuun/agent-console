import { useCallback, useEffect, useState } from "react";
import type { SafeStorage } from "../app/storage";

export const SIDEBAR_COLLAPSED_KEY = "ac.sidebar.collapsed";
/** 이 폭 미만이면 처음부터 접히고, 펼치면 본문 위로 겹치는 드로어가 된다. */
export const SIDEBAR_NARROW_QUERY = "(max-width: 1279px)";

function matches(query: string): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(query).matches;
}

export interface SidebarState {
  collapsed: boolean;
  /** 좁은 화면에서 펼쳐져 본문을 덮는 상태 */
  drawer: boolean;
  setCollapsed: (collapsed: boolean) => void;
  toggle: () => void;
}

/**
 * 사이드바 접힘 상태. 사용자가 정한 값은 저장소에 남기고(실패해도 동작), 정한 적이 없으면 화면 폭이 정한다.
 * @param narrowQuery 좁은 화면 판정 미디어 쿼리(테스트 주입)
 */
export function useSidebarState(storage: SafeStorage, narrowQuery: string = SIDEBAR_NARROW_QUERY): SidebarState {
  const [narrow, setNarrow] = useState(() => matches(narrowQuery));
  const [stored, setStored] = useState<boolean | null>(() => {
    const raw = storage.get(SIDEBAR_COLLAPSED_KEY);
    return raw === "1" ? true : raw === "0" ? false : null;
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(narrowQuery);
    const onChange = () => setNarrow(mq.matches);
    onChange();
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, [narrowQuery]);

  const collapsed = stored ?? narrow;
  const setCollapsed = useCallback(
    (next: boolean) => {
      setStored(next);
      storage.set(SIDEBAR_COLLAPSED_KEY, next ? "1" : "0");
    },
    [storage],
  );
  const toggle = useCallback(() => setCollapsed(!collapsed), [collapsed, setCollapsed]);
  return { collapsed, drawer: narrow && !collapsed, setCollapsed, toggle };
}
