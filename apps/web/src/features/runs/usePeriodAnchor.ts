import { useCallback, useEffect, useState } from "react";

/** 기준 시각이 낡았는가(순수). `now - anchor >= intervalMs`. */
export function isAnchorStale(anchorMs: number, nowMs: number, intervalMs: number): boolean {
  return nowMs - anchorMs >= intervalMs;
}

export interface PeriodAnchorOptions {
  /** 이 간격마다, 그리고 창이 다시 보일 때 이 간격이 지났으면 기준을 다시 잡는다(ms). 0 이하이면 자동 갱신 없음 */
  intervalMs: number;
  /** 현재 시각(ms). 테스트에서 가짜 시계를 주입한다. 기본 `Date.now` */
  now?: () => number;
}

/**
 * 기간 하한 계산에 쓰는 기준 시각(epoch ms). 시각마다 바뀌면 질의 키가 바뀌어 페이지가 처음으로 돌아가므로
 * 화면을 열 때, 간격이 지났을 때(타이머·창 포커스), `refresh()`를 부를 때만 새로 잡는다.
 */
export function usePeriodAnchor({ intervalMs, now = Date.now }: PeriodAnchorOptions): { anchorMs: number; refresh: () => void } {
  const [anchorMs, setAnchorMs] = useState(() => now());
  const refresh = useCallback(() => setAnchorMs(now()), [now]);

  useEffect(() => {
    if (intervalMs <= 0) return undefined;
    const tick = () => setAnchorMs((prev) => (isAnchorStale(prev, now(), intervalMs) ? now() : prev));
    const onVisible = () => {
      if (document.visibilityState === "visible") tick();
    };
    const timer = setInterval(tick, intervalMs);
    window.addEventListener("focus", tick);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", tick);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [intervalMs, now]);

  return { anchorMs, refresh };
}
